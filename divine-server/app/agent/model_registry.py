"""模型仓库 + 硬件检测：根据用户电脑配置推荐可运行的本地模型。

职责：
1. 检测硬件配置（RAM、GPU、CPU）
2. 维护内置模型仓库
3. 推荐适合当前硬件的模型
4. 模型下载/安装/卸载
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Hugging Face 镜像源（国内用户使用）
HF_MIRROR = os.environ.get("HF_MIRROR", "https://hf-mirror.com")
HF_DIRECT = "https://huggingface.co"


@dataclass
class HardwareInfo:
    """硬件配置信息。"""
    ram_total_gb: float = 0.0
    ram_available_gb: float = 0.0
    cpu_cores: int = 0
    has_gpu: bool = False
    gpu_name: str = ""
    gpu_memory_gb: float = 0.0
    platform: str = ""  # "darwin", "linux", "windows"
    arch: str = ""  # "arm64", "x86_64"


@dataclass
class ModelEntry:
    """模型仓库条目。"""
    id: str
    name: str
    description: str
    size_gb: float  # 模型文件大小
    required_ram_gb: float  # 最低内存要求
    quantization: str  # "Q4_K_M", "Q8_0", etc.
    download_url: str
    filename: str  # 下载后的文件名
    recommended: bool = False  # 是否推荐
    tags: list[str] = field(default_factory=list)  # 标签：["small", "fast", "vision"]


# 内置模型仓库
MODEL_REGISTRY: list[ModelEntry] = [
    # Qwen2.5 系列 - 轻量级，适合意图分类
    ModelEntry(
        id="qwen2.5-0.5b-instruct-q4km",
        name="Qwen2.5-0.5B-Instruct",
        description="超轻量模型，适合意图分类和简单对话，速度快",
        size_gb=0.4,
        required_ram_gb=1.0,
        quantization="Q4_K_M",
        download_url="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf",
        filename="qwen2.5-0.5b-instruct-q4_k_m.gguf",
        recommended=True,
        tags=["small", "fast", "intent"],
    ),
    ModelEntry(
        id="qwen2.5-1.5b-instruct-q4km",
        name="Qwen2.5-1.5B-Instruct",
        description="轻量模型，适合意图分类和日常对话",
        size_gb=1.0,
        required_ram_gb=2.0,
        quantization="Q4_K_M",
        download_url="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
        filename="qwen2.5-1.5b-instruct-q4_k_m.gguf",
        recommended=True,
        tags=["small", "balanced", "intent"],
    ),
    ModelEntry(
        id="qwen2.5-3b-instruct-q4km",
        name="Qwen2.5-3B-Instruct",
        description="中等模型，适合代码辅助和复杂对话",
        size_gb=2.0,
        required_ram_gb=4.0,
        quantization="Q4_K_M",
        download_url="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf",
        filename="qwen2.5-3b-instruct-q4_k_m.gguf",
        tags=["medium", "code"],
    ),
    # Phi-3 系列 - 微软出品，质量高
    ModelEntry(
        id="phi-3-mini-4k-q4km",
        name="Phi-3-Mini-4K",
        description="微软小模型，4K上下文，适合快速推理",
        size_gb=2.2,
        required_ram_gb=4.0,
        quantization="Q4_K_M",
        download_url="https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-GGUF/resolve/main/phi-3-mini-4k-instruct-q4_k_m.gguf",
        filename="phi-3-mini-4k-instruct-q4_k_m.gguf",
        tags=["medium", "fast"],
    ),
    # Gemma 2 系列 - Google 出品
    ModelEntry(
        id="gemma-2-2b-it-q4km",
        name="Gemma 2 2B",
        description="Google 轻量模型，适合多语言任务",
        size_gb=1.6,
        required_ram_gb=3.0,
        quantization="Q4_K_M",
        download_url="https://huggingface.co/google/gemma-2-2b-it-GGUF/resolve/main/gemma-2-2b-it-q4_k_m.gguf",
        filename="gemma-2-2b-it-q4_k_m.gguf",
        tags=["small", "multilingual"],
    ),
]


def detect_hardware() -> HardwareInfo:
    """检测当前硬件配置。"""
    info = HardwareInfo()
    info.platform = platform.system().lower()
    info.arch = platform.machine().lower()
    info.cpu_cores = os.cpu_count() or 4

    # 检测内存
    try:
        if info.platform == "darwin":
            # macOS: 使用 sysctl
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                ram_bytes = int(result.stdout.strip())
                info.ram_total_gb = ram_bytes / (1024 ** 3)

            # 可用内存
            result = subprocess.run(
                ["vm_stat"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                # 简单估算：总内存的 70% 可用
                info.ram_available_gb = info.ram_total_gb * 0.7

        elif info.platform == "linux":
            # Linux: 使用 /proc/meminfo
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        info.ram_total_gb = kb / (1024 ** 2)
                    elif line.startswith("MemAvailable:"):
                        kb = int(line.split()[1])
                        info.ram_available_gb = kb / (1024 ** 2)

        elif info.platform == "windows":
            # Windows: 使用 wmic
            result = subprocess.run(
                ["wmic", "OS", "get", "TotalVisibleMemorySize", "/Value"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.startswith("TotalVisibleMemorySize="):
                        kb = int(line.split("=")[1])
                        info.ram_total_gb = kb / (1024 ** 2)
                        info.ram_available_gb = info.ram_total_gb * 0.7
    except Exception as e:
        logger.warning("检测内存失败: %s", e)
        # 默认值
        info.ram_total_gb = 8.0
        info.ram_available_gb = 5.6

    # 检测 GPU
    try:
        if info.platform == "darwin":
            # macOS: 检查是否有 Metal 支持（Apple Silicon）
            if "arm" in info.arch:
                info.has_gpu = True
                info.gpu_name = "Apple Silicon (Metal)"
                # 统一内存，GPU 可用内存 ≈ 总内存
                info.gpu_memory_gb = info.ram_total_gb
            else:
                # Intel Mac 可能有独立显卡
                result = subprocess.run(
                    ["system_profiler", "SPDisplaysDataType"],
                    capture_output=True, text=True, timeout=5,
                )
                if "Chipset Model" in result.stdout:
                    info.has_gpu = True
                    info.gpu_name = "Intel GPU"
                    info.gpu_memory_gb = 1.0  # 估算

        elif info.platform == "linux":
            # Linux: 检查 NVIDIA GPU
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(", ")
                info.has_gpu = True
                info.gpu_name = parts[0]
                # 解析显存
                mem_str = parts[1] if len(parts) > 1 else "0MiB"
                mem_mb = int(mem_str.replace("MiB", "").replace("MB", ""))
                info.gpu_memory_gb = mem_mb / 1024

        elif info.platform == "windows":
            # Windows: 检查 NVIDIA GPU
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(", ")
                info.has_gpu = True
                info.gpu_name = parts[0]
                mem_str = parts[1] if len(parts) > 1 else "0MiB"
                mem_mb = int(mem_str.replace("MiB", "").replace("MB", ""))
                info.gpu_memory_gb = mem_mb / 1024
    except Exception as e:
        logger.warning("检测 GPU 失败: %s", e)

    return info


def get_recommended_models(hardware: HardwareInfo | None = None) -> list[ModelEntry]:
    """根据硬件配置推荐可运行的模型。"""
    if hardware is None:
        hardware = detect_hardware()

    available_ram = hardware.ram_available_gb
    if hardware.has_gpu:
        # 有 GPU 时，可用内存 = max(可用RAM, GPU显存)
        available_ram = max(available_ram, hardware.gpu_memory_gb)

    recommended = []
    for model in MODEL_REGISTRY:
        if model.required_ram_gb <= available_ram:
            # 标记推荐
            model.recommended = model.size_gb <= available_ram * 0.3  # 模型不超过可用内存的 30%
            recommended.append(model)
        else:
            model.recommended = False

    # 按大小排序，小模型优先
    recommended.sort(key=lambda m: m.size_gb)
    return recommended


def get_installed_models(models_dir: Path) -> list[dict[str, Any]]:
    """获取已安装的模型列表。"""
    installed = []
    if not models_dir.exists():
        return installed

    for file in models_dir.glob("*.gguf"):
        # 查找对应的仓库条目
        registry_entry = None
        for model in MODEL_REGISTRY:
            if model.filename == file.name:
                registry_entry = model
                break

        installed.append({
            "id": registry_entry.id if registry_entry else file.stem,
            "name": registry_entry.name if registry_entry else file.stem,
            "filename": file.name,
            "path": str(file),
            "size_gb": file.stat().st_size / (1024 ** 3),
            "enabled": False,  # 需要外部设置
            "registry_id": registry_entry.id if registry_entry else None,
        })

    return installed


def download_model(
    model_id: str,
    models_dir: Path,
    progress_callback: Any = None,
) -> Path | None:
    """下载模型文件（优先使用镜像源）。

    Args:
        model_id: 模型 ID
        models_dir: 模型存储目录
        progress_callback: 进度回调函数 (downloaded_bytes, total_bytes) -> None

    Returns:
        下载后的文件路径，失败返回 None
    """
    # 查找模型
    model = None
    for entry in MODEL_REGISTRY:
        if entry.id == model_id:
            model = entry
            break

    if model is None:
        logger.error("模型不存在: %s", model_id)
        return None

    models_dir.mkdir(parents=True, exist_ok=True)
    target_path = models_dir / model.filename

    # 检查是否已下载
    if target_path.exists():
        logger.info("模型已存在: %s", target_path)
        return target_path

    # 构建 URL 列表：优先镜像源，回退到官方源
    urls_to_try = []

    # 1. 镜像源（优先）
    if model.download_url.startswith(HF_DIRECT):
        mirror_url = model.download_url.replace(HF_DIRECT, HF_MIRROR)
        urls_to_try.append(("镜像源", mirror_url))
    else:
        urls_to_try.append(("镜像源", f"{HF_MIRROR}/{model.download_url}"))

    # 2. 官方源（回退）
    urls_to_try.append(("官方源", model.download_url))

    for source_name, url in urls_to_try:
        logger.info("尝试从 %s 下载模型: %s", source_name, url)
        try:
            response = requests.get(
                url,
                stream=True,
                timeout=(10, 60),  # (connect timeout, read timeout)
                allow_redirects=True,
            )
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0

            with open(target_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total_size)

            logger.info(
                "模型下载完成 (%s): %s (%.1f GB)",
                source_name,
                target_path,
                downloaded / (1024 ** 3),
            )
            return target_path

        except requests.exceptions.ConnectionError as e:
            logger.warning("%s 连接失败: %s", source_name, e)
            if target_path.exists():
                target_path.unlink()
            continue
        except requests.exceptions.Timeout as e:
            logger.warning("%s 下载超时: %s", source_name, e)
            if target_path.exists():
                target_path.unlink()
            continue
        except Exception as e:
            logger.warning("%s 下载失败: %s", source_name, e)
            if target_path.exists():
                target_path.unlink()
            continue

    logger.error("所有下载源均失败，模型: %s", model_id)
    return None


def delete_model(model_id: str, models_dir: Path) -> bool:
    """删除已安装的模型。"""
    for model in MODEL_REGISTRY:
        if model.id == model_id:
            target_path = models_dir / model.filename
            if target_path.exists():
                target_path.unlink()
                logger.info("模型已删除: %s", target_path)
                return True
            break

    # 尝试按文件名删除
    for file in models_dir.glob("*.gguf"):
        if file.stem == model_id:
            file.unlink()
            logger.info("模型已删除: %s", file)
            return True

    return False
