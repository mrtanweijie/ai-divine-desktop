import json
import logging
import os
import runpy
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _run_bundled_script() -> bool:
    if len(sys.argv) < 3 or sys.argv[1] != "--run-script":
        return False
    script = Path(sys.argv[2])
    if not script.exists():
        bundle_root = Path(
            getattr(sys, "_MEIPASS", Path(sys.argv[0]).resolve().parent)
        )
        candidate = bundle_root / script
        if candidate.exists():
            script = candidate
    runpy.run_path(str(script), run_name="__main__")
    return True


def _prepend_library_path(env_name: str, candidates: list[str]) -> None:
    existing = os.environ.get(env_name)
    merged = [path for path in candidates if path and Path(path).exists()]
    if existing:
        merged.append(existing)
    if merged:
        os.environ[env_name] = os.pathsep.join(merged)


def _prepare_library_path() -> None:
    bundle_root = Path(
        getattr(sys, "_MEIPASS", Path(sys.argv[0]).resolve().parent)
    )
    bundled_libs = bundle_root / "weasyprint_libs"
    if sys.platform == "darwin":
        candidates = [str(bundled_libs), "/opt/homebrew/lib", "/usr/local/lib"]
        _prepend_library_path("DYLD_FALLBACK_LIBRARY_PATH", candidates)
    elif sys.platform == "win32":
        candidates = [
            str(bundled_libs),
            r"C:\Program Files\GTK3-Runtime Win64\bin",
            r"C:\msys64\mingw64\bin",
        ]
        _prepend_library_path("PATH", candidates)
    else:
        candidates = [
            str(bundled_libs),
            "/usr/lib/x86_64-linux-gnu",
            "/usr/lib/aarch64-linux-gnu",
            "/usr/lib",
        ]
        _prepend_library_path("LD_LIBRARY_PATH", candidates)


def _setup_logging() -> None:
    from app.config import data_root

    root_dir = data_root()
    root_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.handlers = []
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    file_handler = RotatingFileHandler(
        root_dir / "divine-server.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


def main() -> None:
    _prepare_library_path()
    if _run_bundled_script():
        return
    import uvicorn

    from app.config import data_root, settings_store
    from app.main import app

    _setup_logging()
    settings = settings_store.load()
    logging.getLogger("divine").info(
        "server starting host=%s port=%s data_dir=%s",
        settings.get("host"),
        settings.get("port"),
        data_root(),
    )
    uvicorn.run(
        app,
        host=settings.get("host", "127.0.0.1"),
        port=int(settings.get("port", 8019)),
        reload=False,
        log_config=None,
    )


if __name__ == "__main__":
    main()
