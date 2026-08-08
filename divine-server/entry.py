import uvicorn

from app.config import settings_store
from app.main import app


def main() -> None:
    settings = settings_store.load()
    uvicorn.run(
        app,
        host=settings.get("host", "127.0.0.1"),
        port=int(settings.get("port", 8000)),
        reload=False,
    )


if __name__ == "__main__":
    main()
