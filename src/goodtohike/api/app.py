"""The GoodToHike HTTP application."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from sqlalchemy import Engine, create_engine

from goodtohike.api.problems import add_problem_handlers
from goodtohike.api.routes import router as routes_router
from goodtohike.clients.nws import NwsClient, NwsWeather
from goodtohike.db import Base
from goodtohike.elevation import InterpolateOnly
from goodtohike.http import make_http_client

V1_PREFIX = "/v1"

DEFAULT_DATABASE_URL = "sqlite:///goodtohike.db"

meta_router = APIRouter(tags=["meta"])


@meta_router.get("/health")
def get_health() -> dict[str, str]:
    return {"status": "ok"}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create missing tables on startup, and release connections on shutdown."""
    engine: Engine = app.state.engine
    Base.metadata.create_all(engine)
    yield
    app.state.http.close()
    engine.dispose()


def get_app(title: str, version: str, engine: Engine) -> FastAPI:
    app = FastAPI(title=title, version=version, lifespan=lifespan)
    app.state.engine = engine
    add_problem_handlers(app)

    # Every versioned router hangs off this one, so a /v2 can sit beside it
    # without touching v1.
    v1 = APIRouter(prefix=V1_PREFIX)
    v1.include_router(meta_router)
    v1.include_router(routes_router)
    app.include_router(v1)
    app.state.elevation_filler = InterpolateOnly()
    # One pooled HTTP client for every upstream service, closed on shutdown.
    app.state.http = make_http_client()
    app.state.weather_source = NwsWeather(NwsClient(app.state.http))
    return app


app = get_app(
    title="GoodToHike",
    version="0.1.0",
    engine=create_engine(
        os.environ.get("GOODTOHIKE_DATABASE_URL", DEFAULT_DATABASE_URL)
    ),
)
