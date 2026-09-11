"""The GoodToHike HTTP application."""

from fastapi import APIRouter, FastAPI

meta_router = APIRouter(tags=["meta"])


@meta_router.get("/health")
def get_health() -> dict[str, str]:
    return {"status": "ok"}


def get_app(title: str, version: str) -> FastAPI:
    app = FastAPI(title=title, version=version)
    app.include_router(meta_router, prefix="/v1")
    return app


app = get_app(title="GoodToHike", version="0.1.0")
