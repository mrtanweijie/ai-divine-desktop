import json
import logging
import runpy
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _run_bundled_script() -> bool:
    if len(sys.argv) < 3 or sys.argv[1] != "--run-script":
        return False
    script = Path(sys.argv[2])
    runpy.run_path(str(script), run_name="__main__")
    return True


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
