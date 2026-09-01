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

from ...config import DEFAULT_LOCAL_LLM_PORT, DEFAULT_LOCAL_LLM_THRESHOLD

from .model_registry import (
    MODEL_REGISTRY,
    ModelEntry,
    delete_model,
    download_custom_model,
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

# 本地模型虚拟条目 id（聊天模型切换用）
LOCAL_MODEL_ID = "local"

# 常见 GGUF 量化后缀（自定义模型命名用）
_KNOWN_QUANTS = (
    "q2_k", "q3_k_m", "q4_k_s", "q4_k_m", "q4_0", "q5_k_m",
    "q5_0", "q6_k", "q8_0", "fp16", "bf16", "f16",
)


def custom_model_display_name(filename: str) -> str:
    """自定义模型的可读名称：同家族归到推荐模型名并标注量化。

    如 qwen2.5-0.5b-instruct-q2_k.gguf → "Qwen2.5-0.5B-Instruct (Q2_K)"
    """
    stem = Path(filename).stem
    quant: str | None = None
    base = stem
    for q in _KNOWN_QUANTS:
        if stem.endswith(f"-{q}"):
            quant = q
            base = stem[: -(len(q) + 1)]
            break
    for model in MODEL_REGISTRY:
        if model.filename.startswith(f"{base}-") or model.id.startswith(base):
            suffix = f" ({quant.upper()})" if quant else " (自定义)"
            return f"{model.name}{suffix}"
    return stem


def local_model_entry(
    port: int = DEFAULT_LOCAL_LLM_PORT, model_name: str = "本地模型"
) -> dict[str, Any]:
    """本地模型虚拟条目：llama-server 运行时由 settings API 动态注入模型列表。

    model_name 传当前运行的模型名（如 Qwen2.5-0.5B-Instruct），
    模型切换器分组下即显示具体模型名。不持久化到 settings["models"]。
    """
    return {
        "id": LOCAL_MODEL_ID,
        "name": model_name,
        "provider": "local",
        "model": model_name,
        "base_url": f"http://127.0.0.1:{port}/v1",
        "api_key": "local",
        "active": False,
        "tool_mode": "auto",
        "custom_models": "",
        "vendor": "local",
    }

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

    def __init__(self, data_dir: str, port: int = DEFAULT_LOCAL_LLM_PORT) -> None:
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

    def _effective_active_model_id(self) -> str | None:
        """当前运行模型 id（内存态 → 设置持久化 → 询问 llama-server 兜底）。"""
        model_id = self.active_model_id
        if model_id is None:
            try:
                from ...config import settings_store

                model_id = settings_store.load().get("local_llm_model") or None
            except Exception:
                model_id = None
        if model_id is None:
            model_id = self._query_loaded_model_id()
            if model_id:
                self._persist_active_model(model_id)
        return model_id

    def active_model_name(self) -> str | None:
        """当前运行模型的可展示名称（来自模型仓库，找不到则用 id）。"""
        model_id = self._effective_active_model_id()
        if not model_id:
            return None
        for model in MODEL_REGISTRY:
            if model.id == model_id:
                return model.name
        return model_id

    def _query_loaded_model_id(self) -> str | None:
        """通过 llama-server /v1/models 获取当前加载的模型 id。"""
        try:
            r = requests.get(
                f"http://127.0.0.1:{self.port}/v1/models", timeout=2.0
            )
            r.raise_for_status()
            models = r.json().get("models") or []
            if not models:
                return None
            path = str(
                models[0].get("model") or models[0].get("name") or ""
            )
            installed = get_installed_models(self.models_dir)
            target = Path(path).expanduser().resolve()
            for m in installed:
                if m.get("path") and Path(m["path"]).resolve() == target:
                    return m.get("registry_id") or m.get("id")
            # 按文件名兜底
            filename = target.name
            for m in installed:
                if m.get("filename") == filename:
                    return m.get("registry_id") or m.get("id")
        except Exception as e:  # noqa: BLE001
            logger.warning("查询 llama-server 模型失败: %s", e)
        return None

    def _persist_active_model(self, model_id: str) -> None:
        """记录当前运行模型到设置，sidecar 重启后仍能识别模型名。"""
        try:
            from ...config import settings_store

            settings = settings_store.load()
            if settings.get("local_llm_model") != model_id:
                settings["local_llm_model"] = model_id
                settings_store.save(settings)
        except Exception:  # noqa: BLE001
            pass

    def _read_stderr(self, proc: subprocess.Popen | None) -> str:
        """读取子进程错误输出（进程退出后调用）。"""
        if proc is None or not proc.stderr:
            return ""
        try:
            return proc.stderr.read().decode("utf-8", errors="replace").strip()
        except Exception:
            return ""

    def _port_pids(self) -> list[int]:
        """返回占用本端口的进程 PID（用于释放孤儿 llama-server）。"""
        try:
            r = subprocess.run(
                ["lsof", "-ti", f"tcp:{self.port}"],
                capture_output=True, text=True, timeout=3,
            )
            pids = [
                int(line.strip())
                for line in r.stdout.splitlines()
                if line.strip().isdigit()
            ]
            return pids
        except Exception:  # noqa: BLE001
            return []

    def _free_orphan_port(self, wait_s: float = 5.0) -> None:
        """终止占用端口但未被本 manager 托管的进程（孤儿 llama-server）。"""
        for pid in self._port_pids():
            if self.process and self.process.pid == pid:
                continue
            try:
                os.kill(pid, signal.SIGTERM)
                logger.info("终止孤儿 llama-server pid=%s", pid)
            except ProcessLookupError:
                pass
            except Exception as e:  # noqa: BLE001
                logger.warning("终止孤儿进程失败 pid=%s: %s", pid, e)
        # 等待端口释放，避免新进程绑定失败
        deadline = time.time() + wait_s
        while time.time() < deadline:
            if not self._port_pids():
                return
            time.sleep(0.2)
        logger.warning("端口 %d 在 %ss 内未释放", self.port, wait_s)

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

        # 释放端口上未托管的孤儿 llama-server（避免绑定失败/误判就绪）
        self._free_orphan_port()

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
                self._persist_active_model(model_id)
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
                if self.active_model_id:
                    self._persist_active_model(self.active_model_id)
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
        """停止 llama-server 子进程（含未托管的孤儿进程）。"""
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
        # 顺带释放端口上的孤儿进程
        self._free_orphan_port(wait_s=3.0)

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

        # 注意：不拼上一条 AI 回复做上下文——动作词（如"已截图保存到…"）会
        # 污染分类，导致后续消息被误判。意图只看用户当前消息。
        user_prompt = text

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

    def organize(self, text: str, timeout: float = 30.0) -> str | None:
        """用本地模型把长文本整理成结构化版本（输入侧预整理）。

        返回整理文本；本地不可用/失败/校验不过返回 None（调用方降级原样上云）。
        设计与规则见 docs/preprocess-feature-design.md。

        输出校验（三关，任一不过即丢弃，宁可不整理）：
        1. 必须以「[本地整理版]」开头（对齐格式契约，防跑题/拒绝整理）
        2. 长度不得超过原文 80%（防废话整理）
        3. 可打印字符占比 >= 0.9（防乱码）
        """
        if not self.is_ready():
            return None

        system_prompt = (
            "你是文本整理助手。把用户输入整理成结构清晰的版本：\n"
            "1. 按主题分段，每段用「### 标题」+ 要点列表\n"
            "2. 保留所有关键事实、数字、名称、约束条件，不改写原意\n"
            "3. 删除重复、客套、无关内容\n"
            "4. 不添加原文没有的信息，不判断对错\n"
            "5. 保留所有链接、路径、专有名词，原样不改写；表格/CSV 等结构化内容保持原格式\n"
            "6. 尽量简洁：每个要点一句话，同类内容合并，不要逐条复述原文\n"
            "7. 输出以「[本地整理版]」开头；无法整理时只输出「无法整理」\n"
            "示例：\n"
            "输入：明天下午3点和客户开会，讨论项目延期，需要准备进度报告。\n"
            "输出：\n"
            "[本地整理版]\n"
            "\n"
            "### 会议安排\n"
            "- 明天下午 3 点与客户开会，议题为项目延期\n"
            "- 需要准备：进度报告"
        )
        # 输出 token 上限：按输入长度缩放但保底 1024——1.5B 对某些内容
        # （逐条展开式）输出很长，上限太低会截断导致整段整理被丢弃
        max_tokens = min(max(len(text), 1024), 2048)
        payload = {
            "model": "local",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        try:
            r = requests.post(
                f"http://127.0.0.1:{self.port}/v1/chat/completions",
                json=payload,
                timeout=timeout,
            )
            r.raise_for_status()
            choice = r.json()["choices"][0]
            if choice.get("finish_reason") == "length":
                logger.warning(
                    "本地整理输出被截断（finish_reason=length），丢弃走云端"
                )
                return None
            content = str(choice["message"]["content"] or "").strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            # 三关校验
            # ① 格式契约：以「[本地整理版]」开头，或以「###」标题直接开头
            #   （小模型常见表现：内容格式正确但漏掉前缀标记，此时仍视为合格）
            if not (
                content.startswith("[本地整理版]")
                or content.startswith("### ")
            ):
                logger.info(
                    "本地整理输出未按格式契约，丢弃走云端: %r", content[:80]
                )
                return None
            # ② 废话整理检测：输出显著长于原文（>1.5x+200 字符）且无结构化
            #    标题 → 丢弃。不设压缩率硬门槛：密集内容的重构输出（加
            #    ### 标题/要点化）可能与原文等长甚至更长，只要带结构即视为有效
            if "### " not in content and len(content) > int(len(text) * 1.5) + 200:
                logger.info(
                    "本地整理输出疑似废话整理（%.0f 字 vs 原文 %d 字且无标题），丢弃走云端",
                    len(content),
                    len(text),
                )
                return None
            if content:
                printable = sum(
                    1 for ch in content if ch.isprintable() or ch in "\r\n\t"
                )
                if printable / len(content) < 0.9:
                    logger.info("本地整理输出疑似乱码，丢弃走云端")
                    return None
            return content
        except Exception as e:  # noqa: BLE001
            logger.warning("本地整理失败: %s", e)
            return None

    def get_status(self) -> dict[str, Any]:
        """获取本地模型状态。"""
        installed = get_installed_models(self.models_dir)
        
        # 读取设置（mode / threshold 等）
        try:
            from ...config import settings_store

            settings = settings_store.load()
        except Exception:
            settings = {}
        enabled = bool(settings.get("local_llm_enabled", False))
        mode = settings.get("local_llm_mode", "keyword")
        threshold = settings.get(
            "local_llm_threshold", DEFAULT_LOCAL_LLM_THRESHOLD
        )
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
        installed_by_id = {
            m["registry_id"]: m for m in installed if m.get("registry_id")
        }
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
        # 推荐列表 = 仓库推荐 + 用户自定义安装的模型（无 registry_id）
        custom_installed = [m for m in installed if not m.get("registry_id")]
        recommended_list = [
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
                "incomplete": bool(installed_by_id.get(m.id, {}).get("incomplete")),
            }
            for m in recommended
        ]
        # 自定义安装的模型单独分组展示（不与推荐列表混排，避免同家族重复观感）
        custom_list = [
            {
                "id": cm["id"],
                "name": custom_model_display_name(cm["filename"]),
                "description": "用户自定义安装的模型",
                "size_gb": cm["size_gb"],
                "required_ram_gb": max(round(cm["size_gb"] * 1.3, 1), 2.0),
                "quantization": "自定义",
                "recommended": False,
                "tags": ["custom"],
                "installed": True,
                "incomplete": bool(cm.get("incomplete")),
            }
            for cm in custom_installed
        ]
        return {
            "enabled": enabled,
            "mode": mode,
            "threshold": threshold,
            "running": running,
            "llama_server_running": running,
            "active_model": self._effective_active_model_id() if running else None,
            "last_error": self.last_error,
            "port": self.port,
            "binary": binary,
            "llama_server_installed": binary is not None,
            "pid": self.process.pid if self.process and self.process.poll() is None else None,
            "hardware": hw_info,
            "installed_models": installed,
            "recommended_models": recommended_list,
            "custom_models": custom_list,
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

    def install_custom_model(
        self,
        url: str,
        name: str | None = None,
        progress_key: str | None = None,
    ) -> tuple[bool, str]:
        """安装自定义模型。返回 (ok, message)。

        若 URL/文件名命中了推荐仓库的模型，走仓库下载（镜像源 + 统一文件名），
        等同点击推荐列表的"一键安装"，装完即推荐列表中的同一条目，不重复。
        """
        key = progress_key or f"custom-{int(time.time())}"

        def _progress(downloaded: int, total: int) -> None:
            self._download_progress[key] = {
                "downloaded": downloaded,
                "total": total,
                "percent": (downloaded / total * 100) if total > 0 else 0,
            }

        filename = (name or "").strip() or str(url).split("/")[-1].split("?")[0].strip()
        # 匹配推荐仓库：优先按文件名，URL 兜底
        registry_model = None
        for model in MODEL_REGISTRY:
            if model.filename == filename or (
                str(model.download_url).rstrip("/") == str(url).rstrip("/")
            ):
                registry_model = model
                break
        try:
            if registry_model is not None:
                logger.info(
                    "自定义安装命中推荐仓库: %s → %s", url[:80], registry_model.id
                )
                path = download_model(registry_model.id, self.models_dir, _progress)
            else:
                path = download_custom_model(url, self.models_dir, name, _progress)
        finally:
            self._download_progress.pop(key, None)
        if path is None:
            return False, "下载失败，请检查 URL 与网络"
        return True, str(path)

    def register_local_model(self, path: str) -> tuple[bool, str]:
        """注册本地 .gguf 文件（复制到模型目录）。返回 (ok, message)。"""
        src = Path(path).expanduser()
        if not src.is_file() or src.suffix.lower() != ".gguf":
            return False, "文件不存在或不是 .gguf 格式"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        dest = self.models_dir / src.name
        # 源文件已在模型目录内 → 直接视为已注册
        if src.resolve() == dest.resolve():
            return True, str(dest)
        try:
            shutil.copy2(src, dest)
        except Exception as e:  # noqa: BLE001
            logger.warning("注册本地模型失败: %s", e)
            return False, f"复制失败: {e}"
        return True, str(dest)


def get_manager(
    data_dir: str | None = None, port: int = DEFAULT_LOCAL_LLM_PORT
) -> LocalLLMManager:
    """获取全局单例。"""
    global _manager
    if _manager is None:
        from ...config import data_root

        _manager = LocalLLMManager(
            data_dir=data_dir or str(data_root()),
            port=port,
        )
    return _manager
