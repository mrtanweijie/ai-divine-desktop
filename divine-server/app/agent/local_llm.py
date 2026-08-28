"""本地 LLM 管理器：llama-server 进程管理 + 意图分类。

职责：
1. 启动/停止 llama-server 子进程
2. 健康检查
3. 调用本地模型做意图分类
4. 模型下载/安装/卸载
5. 降级策略：本地不可用时返回 None，调用方走云端

不负责：
- 云端调用（由 orchestrator 处理）
- 工具执行（由 execution 处理）
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

import requests

from .model_registry import (
    MODEL_REGISTRY,
    ModelEntry,
    delete_model,
    download_model,
    get_installed_models,
)

# 这些可能在打包环境导入失败，做惰性导入
try:
    from .model_registry import detect_hardware, get_recommended_models
except Exception:
    detect_hardware = None  # type: ignore[assignment]
    get_recommended_models = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# 意图分类白名单 + 中文/别名 → 规范标签归一化
_VALID_INTENTS = {
    "open_app", "screenshot", "lock_screen", "search_file",
    "terminal", "project", "memory", "generation", "question", "other",
}
_INTENT_ALIASES = {
    "打开应用": "open_app", "打开": "open_app", "启动应用": "open_app",
    "截图": "screenshot", "截屏": "screenshot", "屏幕截图": "screenshot",
    "锁屏": "lock_screen", "锁定屏幕": "lock_screen",
    "找文件": "search_file", "搜索文件": "search_file", "查找文件": "search_file",
    "文件搜索": "search_file",
    "终端": "terminal", "命令行": "terminal",
    "项目": "project", "工程": "project",
    "记忆": "memory", "记住": "memory",
    "生成": "generation", "创作": "generation",
    "问题": "question", "提问": "question", "查询": "question",
    "查询天气": "question", "问候": "question", "打招呼": "question",
    "聊天": "question", "闲聊": "question", "寒暄": "question",
    "计算": "question", "数学": "question",
}

# 全局单例
_manager: LocalLLMManager | None = None


class LocalLLMManager:
    """llama-server 进程管理 + 意图分类。"""

    def __init__(self, data_dir: str, port: int = 8016) -> None:
        self.data_dir = Path(data_dir)
        self.models_dir = self.data_dir / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.port = port
        self.process: subprocess.Popen | None = None
        self.active_model_id: str | None = None  # 当前正在运行的模型 id
        self.last_error: str | None = None  # 最近一次启动失败的原因
        self._pending_model_id: str | None = None
        self._lock = threading.Lock()
        self._classifier_cache: dict[str, Any] = {}
        self._download_progress: dict[str, dict[str, Any]] = {}

    def _find_binary(self) -> str | None:
        """查找 llama-server 二进制文件。"""
        binary_name = "llama-server"
        if os.name == "nt":
            binary_name = "llama-server.exe"

        # 1. 用户数据目录（已部署）
        user_binary = self.models_dir.parent / "llama" / binary_name
        if user_binary.exists():
            return str(user_binary)

        # 2. PyInstaller 打包后（首次运行自动部署）
        import sys
        if getattr(sys, 'frozen', False):
            bundle_dir = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else Path(sys.executable).parent
            bundle_binary = bundle_dir / "llama" / binary_name
            if bundle_binary.exists():
                # 部署到用户数据目录
                self._deploy_llama(bundle_dir / "llama")
                return str(user_binary)

        # 3. 开发环境：bin/darwin-arm64/llama/
        server_dir = Path(__file__).parent.parent.parent
        dev_binary = server_dir / "bin" / "darwin-arm64" / "llama" / binary_name
        if dev_binary.exists():
            return str(dev_binary)

        # 4. 检查 PATH
        found = shutil.which(binary_name)
        if found:
            return found

        return None

    def _deploy_llama(self, source_dir: Path) -> None:
        """将 llama-server 从打包目录部署到用户数据目录。"""
        import shutil
        dest_dir = self.models_dir.parent / "llama"
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # 复制所有文件
            for item in source_dir.iterdir():
                if item.is_file():
                    dest = dest_dir / item.name
                    shutil.copy2(item, dest)
                    os.chmod(dest, 0o755)  # 设置可执行权限
                    logger.info("部署 llama 文件: %s -> %s", item, dest)
        except Exception as e:
            logger.error("部署 llama-server 失败: %s", e)

    def is_ready(self) -> bool:
        """检查 llama-server 是否就绪。"""
        try:
            r = requests.get(
                f"http://127.0.0.1:{self.port}/health",
                timeout=0.5,
            )
            return r.status_code == 200
        except Exception:
            return False

    def _read_stderr(self, proc: subprocess.Popen | None) -> str:
        """读取子进程错误输出（进程退出后调用）。"""
        if proc is None or not proc.stderr:
            return ""
        try:
            return proc.stderr.read().decode("utf-8", errors="replace").strip()
        except Exception:
            return ""

    def start(
        self,
        model_id: str,
        model_path: str,
        ctx_size: int = 4096,
        wait_s: float = 3.0,
    ) -> tuple[bool, str]:
        """启动 llama-server 子进程。

        非阻塞：等待 ``wait_s`` 秒做快速就绪/崩溃检测，若进程已就绪或仍在
        后台启动中则立即返回成功；若进程在窗口内崩溃（如缺失动态库），返回
        失败并带上真实错误信息。

        返回: (ok, error)
            - ok=True, error=""  : 已就绪或正在后台启动
            - ok=False, error=...: 启动失败（二进制/模型缺失或立即崩溃）
        """
        # 已运行则先停止（注意不能在持有 _lock 时调 stop()，Lock 不可重入）
        with self._lock:
            running_proc = self.process if self.process and self.process.poll() is None else None
        if running_proc is not None:
            self.stop()

        with self._lock:
            self.last_error = None
            binary = self._find_binary()
            if not binary:
                logger.error("llama-server 二进制文件未找到")
                return False, "llama-server 二进制文件未找到"

            if not Path(model_path).exists():
                logger.error("模型文件不存在: %s", model_path)
                return False, f"模型文件不存在: {model_path}"

            # 设置动态库路径
            import sys
            env = os.environ.copy()
            binary_dir = Path(binary).parent

            # macOS rpath
            if sys.platform == "darwin":
                env["DYLD_LIBRARY_PATH"] = str(binary_dir)
                env["DYLD_FALLBACK_LIBRARY_PATH"] = str(binary_dir)

            cmd = [
                binary,
                "-m", model_path,
                "--host", "127.0.0.1",
                "--port", str(self.port),
                "--ctx-size", str(ctx_size),
                "--threads", str(min(os.cpu_count() or 4, 8)),
            ]

            logger.info("启动 llama-server: %s", " ".join(cmd))

            try:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    preexec_fn=os.setsid if os.name != "nt" else None,
                    env=env,
                )
            except Exception as e:
                logger.error("启动 llama-server 失败: %s", e)
                self.process = None
                return False, f"启动 llama-server 失败: {e}"

        # 快速检测：窗口内崩溃（缺动态库等）立刻返回真实错误
        deadline = time.time() + wait_s
        while time.time() < deadline:
            proc = self.process
            if proc is None or proc.poll() is not None:
                stderr = self._read_stderr(proc)
                code = proc.returncode if proc is not None else "?"
                self.last_error = stderr or f"llama-server 已退出 (code={code})"
                with self._lock:
                    self.process = None
                logger.error(
                    "llama-server 启动失败 (code=%s), stderr: %s",
                    code,
                    self.last_error[:500],
                )
                return False, self.last_error[:500]
            if self.is_ready():
                self.active_model_id = model_id
                logger.info("llama-server 就绪，端口 %d", self.port)
                return True, ""
            time.sleep(0.2)

        # 仍在启动中 → 后台线程继续等待
        self._pending_model_id = model_id
        threading.Thread(
            target=self._wait_ready, daemon=True
        ).start()
        return True, ""

    def _wait_ready(self) -> None:
        """后台等待 llama-server 就绪（最多 60 秒）。"""
        proc = self.process
        for _ in range(120):
            time.sleep(0.5)
            if self.is_ready():
                self.active_model_id = getattr(self, "_pending_model_id", None)
                logger.info("llama-server 就绪，端口 %d", self.port)
                return

        # 读取错误输出（进程可能已退出，也可能仍在运行）
        with self._lock:
            if proc and proc.poll() is not None:
                stderr = self._read_stderr(proc)
                self.last_error = stderr or f"llama-server 已退出 (code={proc.returncode})"
                logger.error(
                    "llama-server 已退出 (code=%s), stderr: %s",
                    proc.returncode,
                    self.last_error[:500],
                )
            else:
                self.last_error = f"llama-server 启动超时（{int(120 * 0.5)}s）"
                logger.error("llama-server 启动超时")
        # 注意：不要在持有 _lock 时调用 stop()（Lock 不可重入，会死锁）。
        # 仅当 self.process 仍是本线程等待的进程时才停止，避免误杀新的进程。
        with self._lock:
            should_stop = self.process is proc
        if should_stop:
            self.stop()

    def stop(self) -> None:
        """停止 llama-server 子进程。"""
        with self._lock:
            if self.process:
                try:
                    if os.name != "nt":
                        os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                    else:
                        self.process.terminate()
                    self.process.wait(timeout=5)
                except Exception:
                    try:
                        self.process.kill()
                    except Exception:
                        pass
                self.process = None
                self.active_model_id = None
                logger.info("llama-server 已停止")

    def classify(self, text: str, context: str = "") -> dict[str, Any] | None:
        """调用本地模型做意图分类。

        返回: {"intent": "...", "confidence": 0.x} 或 None（失败时）
        """
        if not self.is_ready():
            return None

        system_prompt = (
            "你是意图分类器。根据用户输入判断意图类别。\n"
            "类别：open_app(打开应用/文件夹), screenshot(截图), "
            "lock_screen(锁屏), search_file(找文件), terminal(终端命令), "
            "project(项目), memory(记忆), generation(生成内容), "
            "question(提问/计算/闲聊/问候), other(其他).\n"
            "规则：问候、提问、计算、闲聊、求助一律是 question；"
            "只有明确要求打开应用、截图、锁屏、找文件时才返回对应类别。\n"
            "示例：\n"
            "「帮我打开计算器」→ open_app\n"
            "「截个图」→ screenshot\n"
            "「锁屏」→ lock_screen\n"
            "「帮我找文件」→ search_file\n"
            "「1+1=？」→ question\n"
            "「你好」→ question\n"
            "「今天天气怎么样」→ question\n"
            '只输出 JSON：{"intent":"类别","confidence":0.0}'
        )

        user_prompt = text
        if context:
            user_prompt = f"[上下文] {context[-200:]}\n[输入] {text}"

        payload = {
            "model": "local",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
            "max_tokens": 32,
        }

        try:
            r = requests.post(
                f"http://127.0.0.1:{self.port}/v1/chat/completions",
                json=payload,
                timeout=5.0,
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"].strip()

            # 清理 JSON 格式
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            data = json.loads(content)
            intent = data.get("intent")
            # 归一化：模型可能返回中文标签或未知标签，统一映射到白名单，
            # 未知标签按 other 处理（不参与本地短路，走云端）
            intent = _INTENT_ALIASES.get(intent, intent)
            if intent not in _VALID_INTENTS:
                intent = "other"
            return {
                "intent": intent,
                "confidence": float(data.get("confidence", 0.0)),
            }
        except Exception as e:
            logger.warning("本地模型分类失败: %s", e)
            return None

    def summarize(
        self,
        text: str,
        budget: int = 400,
        lang: str = "简体中文",
        previous: str = "",
        timeout: float = 30.0,
    ) -> str | None:
        """用本地模型把对话压缩为要点摘要（压缩提示词，省云 token）。

        返回摘要文本；本地模型不可用或失败返回 None（调用方回退云端）。
        """
        if not self.is_ready():
            return None

        system_prompt = (
            "你是对话摘要助手。把用户与 AI 助手的对话压缩为要点摘要。\n"
            "必须保留：用户透露的偏好、身份、个人信息，已做出的决定和选择，"
            "正在进行的任务及其进度，关键事实、数字、约束条件，"
            "用户明确要求记住的内容。\n"
            "忽略：寒暄、临时指令、工具执行细节、重复内容。\n"
            "如果提供了已有摘要，请与新内容合并、去重并保持连贯。\n"
            f"输出 {lang} 摘要，不超过 {budget} 个 token，不要客套话和列表编号。"
        )
        parts: list[str] = []
        if previous:
            parts.append(f"已有摘要：\n{previous}\n")
        parts.append(f"新增对话：\n{text}\n")
        parts.append("请输出合并后的摘要。")

        payload = {
            "model": "local",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "\n".join(parts)},
            ],
            "temperature": 0.3,
            "max_tokens": max(int(budget) * 2, 128),
        }
        try:
            r = requests.post(
                f"http://127.0.0.1:{self.port}/v1/chat/completions",
                json=payload,
                timeout=timeout,
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            return content or None
        except Exception as e:
            logger.warning("本地模型摘要失败: %s", e)
            return None

    def get_status(self) -> dict[str, Any]:
        """获取本地模型状态。"""
        installed = get_installed_models(self.models_dir)
        
        # 读取设置（mode / threshold 等）
        try:
            from ..config import settings_store

            settings = settings_store.load()
        except Exception:
            settings = {}
        enabled = bool(settings.get("local_llm_enabled", False))
        mode = settings.get("local_llm_mode", "keyword")
        threshold = settings.get("local_llm_threshold", 0.75)
        running = self.is_ready()
        
        # 安全调用 detect_hardware（打包环境可能失败）
        try:
            hardware = detect_hardware() if detect_hardware else None
        except Exception as e:
            logger.warning("detect_hardware 失败: %s", e)
            hardware = None
        
        # 安全调用 get_recommended_models
        try:
            recommended = get_recommended_models(hardware) if get_recommended_models and hardware else []
        except Exception as e:
            logger.warning("get_recommended_models 失败: %s", e)
            recommended = []

        # 标记已安装的模型
        installed_ids = {m["registry_id"] for m in installed if m.get("registry_id")}
        for model in recommended:
            model.recommended = model.id in installed_ids or model.recommended

        hw_info = (
            {
                "ram_total_gb": hardware.ram_total_gb,
                "ram_available_gb": hardware.ram_available_gb,
                "cpu_cores": hardware.cpu_cores,
                "has_gpu": hardware.has_gpu,
                "gpu_name": hardware.gpu_name,
                "gpu_memory_gb": hardware.gpu_memory_gb,
                "platform": hardware.platform,
                "arch": hardware.arch,
            }
            if hardware
            else {}
        )

        binary = self._find_binary()
        return {
            "enabled": enabled,
            "mode": mode,
            "threshold": threshold,
            "running": running,
            "llama_server_running": running,
            "active_model": self.active_model_id if running else None,
            "last_error": self.last_error,
            "port": self.port,
            "binary": binary,
            "llama_server_installed": binary is not None,
            "pid": self.process.pid if self.process and self.process.poll() is None else None,
            "hardware": hw_info,
            "installed_models": installed,
            "recommended_models": [
                {
                    "id": m.id,
                    "name": m.name,
                    "description": m.description,
                    "size_gb": m.size_gb,
                    "required_ram_gb": m.required_ram_gb,
                    "quantization": m.quantization,
                    "recommended": m.recommended,
                    "tags": m.tags,
                    "installed": m.id in installed_ids,
                }
                for m in recommended
            ],
            "download_progress": self._download_progress,
        }

    def install_model(
        self,
        model_id: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> bool:
        """安装模型（下载）。"""
        def _progress(downloaded: int, total: int) -> None:
            self._download_progress[model_id] = {
                "downloaded": downloaded,
                "total": total,
                "percent": (downloaded / total * 100) if total > 0 else 0,
            }
            if progress_callback:
                progress_callback(downloaded, total)

        result = download_model(model_id, self.models_dir, _progress)
        # 清理进度
        self._download_progress.pop(model_id, None)
        return result is not None

    def uninstall_model(self, model_id: str) -> bool:
        """卸载模型（删除文件）。"""
        return delete_model(model_id, self.models_dir)


def get_manager(data_dir: str | None = None, port: int = 8016) -> LocalLLMManager:
    """获取全局单例。"""
    global _manager
    if _manager is None:
        from ..config import data_root

        _manager = LocalLLMManager(
            data_dir=data_dir or str(data_root()),
            port=port,
        )
    return _manager
