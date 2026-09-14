"""The GoodToHike HTTP application."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import httpx2
from fastapi import APIRouter, FastAPI
from sqlalchemy import Engine, create_engine

from goodtohike.api.problems import add_problem_handlers
from goodtohike.api.routes import router as routes_router
from goodtohike.api.water_sources import router as water_sources_router
from goodtohike.clients.epqs import EpqsClient
from goodtohike.clients.nws import NwsClient, NwsWeather
from goodtohike.db import Base
from goodtohike.elevation import (
    ElevationFiller,
    HybridFill,
    InterpolateOnly,
    LookUpEveryPoint,
    LookUpGaps,
)
from goodtohike.http import make_http_client
from goodtohike.settings import DEFAULT_ELEVATION_FILL, Settings

V1_PREFIX = "/v1"

# How missing elevation is filled, chosen by name when the app starts.
ELEVATION_FILLERS: dict[str, Callable[[httpx2.Client], ElevationFiller]] = {
    "hybrid": lambda http: HybridFill(fetch=EpqsClient(http).get_elevations),
    "interpolate": lambda http: InterpolateOnly(),
    "lookup-gaps": lambda http: LookUpGaps(fetch=EpqsClient(http).get_elevations),
    "lookup-every-point": lambda http: LookUpEveryPoint(
        fetch=EpqsClient(http).get_elevations
    ),
}

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


def get_app(
    title: str,
    version: str,
    engine: Engine,
    elevation_fill: str = DEFAULT_ELEVATION_FILL,
) -> FastAPI:
    """Build the application.

    Raises ValueError when ``elevation_fill`` names no strategy in
    ``ELEVATION_FILLERS``, so a mistyped setting stops the app starting rather
    than surfacing on the first upload.
    """
    try:
        make_elevation_filler = ELEVATION_FILLERS[elevation_fill]
    except KeyError:
        raise ValueError(
            f"unknown elevation fill {elevation_fill!r}, expected one of: "
            + ", ".join(ELEVATION_FILLERS)
        ) from None

    app = FastAPI(title=title, version=version, lifespan=lifespan)
    app.state.engine = engine
    add_problem_handlers(app)

    # Every versioned router hangs off this one, so a /v2 can sit beside it
    # without touching v1.
    v1 = APIRouter(prefix=V1_PREFIX)
    v1.include_router(meta_router)
    v1.include_router(routes_router)
    v1.include_router(water_sources_router)
    app.include_router(v1)
    # One pooled HTTP client for every upstream service, closed on shutdown.
    app.state.http = make_http_client()
    app.state.elevation_filler = make_elevation_filler(app.state.http)
    app.state.weather_source = NwsWeather(NwsClient(app.state.http))
    return app


settings = Settings()
app = get_app(
    title="GoodToHike",
    version="0.1.0",
    engine=create_engine(settings.database_url),
    elevation_fill=settings.elevation_fill,
)
