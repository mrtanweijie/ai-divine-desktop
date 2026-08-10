import uvicorn

from app.config import settings_store


def main() -> None:
    settings = settings_store.load()
    uvicorn.run(
        "app.main:app",
        host=settings.get("host", "127.0.0.1"),
        port=int(settings.get("port", 8019)),
        reload=False,
    )


if __name__ == "__main__":
    main()
