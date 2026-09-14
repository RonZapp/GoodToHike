"""The GoodToHike HTTP application."""

from fastapi import APIRouter, FastAPI

from goodtohike.api.routes import router as routes_router
from goodtohike.elevation import InterpolateOnly

V1_PREFIX = "/v1"

meta_router = APIRouter(tags=["meta"])


@meta_router.get("/health")
def get_health() -> dict[str, str]:
    return {"status": "ok"}


def get_app(title: str, version: str) -> FastAPI:
    app = FastAPI(title=title, version=version)

    # Even though its not necessary, adding specific v1 router to simulate
    # usage of versioned routers for concept practice.
    v1 = APIRouter(prefix=V1_PREFIX)
    v1.include_router(meta_router)
    v1.include_router(routes_router)
    app.include_router(v1)
    app.state.elevation_filler = InterpolateOnly()
    return app


app = get_app(title="GoodToHike", version="0.1.0")
