"""The /routes endpoints:

submitting a track, reading back the route built from it, its profile, and
the conditions along it.
"""

from collections.abc import Iterator
from datetime import datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from goodtohike.conditions import WeatherSource, get_route_forecasts
from goodtohike.db import RouteRecord, record_to_route, route_to_record
from goodtohike.elevation import ElevationFiller
from goodtohike.elevation_profile import build_profile
from goodtohike.gpx import parse_gpx
from goodtohike.ingest import build_route

router = APIRouter(tags=["routes"])


class RouteSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source: str
    point_count: int
    length_m: float
    created_at: datetime


class ProfilePointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    distance_m: float
    elevation_m: float
    grade_percent: float | None


class RouteProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    spacing_m: float
    length_m: float
    gain_m: float
    loss_m: float
    points: list[ProfilePointResponse]


class ForecastPeriodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    start_time: datetime
    end_time: datetime
    is_daytime: bool
    temperature_c: float
    precipitation_chance_percent: float | None
    wind_speed: str
    wind_direction: str
    short_forecast: str
    detailed_forecast: str


class ForecastResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    updated_at: datetime
    elevation_m: float | None
    periods: list[ForecastPeriodResponse]


class LocationForecastResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    distance_m: float
    lat: float
    lon: float
    elevation_m: float
    is_high_point: bool
    forecast: ForecastResponse | None


class RouteConditions(BaseModel):
    # A list of places rather than one forecast, and a field of its own so
    # snow, streamflow and closures can sit beside it later.
    weather: list[LocationForecastResponse]


def get_elevation_filler(request: Request) -> ElevationFiller:
    return request.app.state.elevation_filler


def get_weather_source(request: Request) -> WeatherSource:
    return request.app.state.weather_source


def get_session(request: Request) -> Iterator[Session]:
    """A database session for one request, closed once the response is sent."""
    # Keep loaded values after commit, so building the response does not
    # reload the row, points and all.
    with Session(request.app.state.engine, expire_on_commit=False) as session:
        yield session


@router.post("/routes", status_code=201)
def create_route(
    request: Request,
    response: Response,
    file: Annotated[UploadFile, File()],
    elevation_filler: Annotated[ElevationFiller, Depends(get_elevation_filler)],
    session: Annotated[Session, Depends(get_session)],
    name: Annotated[str | None, Form()] = None,
) -> RouteSummary:
    track = parse_gpx(file.file.read())
    route = build_route(track, elevation_filler, name)

    record = route_to_record(route)
    session.add(record)
    session.commit()

    response.headers["Location"] = str(request.url_for("get_route", route_id=record.id))
    return RouteSummary.model_validate(record)


@router.get("/routes/{route_id}")
def get_route(
    route_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> RouteSummary:
    record = session.get(RouteRecord, route_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No route has id {route_id}.")
    return RouteSummary.model_validate(record)


@router.get("/routes/{route_id}/profile")
def get_route_profile(
    route_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> RouteProfile:
    record = session.get(RouteRecord, route_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No route has id {route_id}.")
    # Reading the points loads the deferred column, inside this request's
    # session.
    profile = build_profile(record_to_route(record).points)
    return RouteProfile.model_validate(profile)


@router.get("/routes/{route_id}/conditions")
def get_route_conditions(
    route_id: int,
    session: Annotated[Session, Depends(get_session)],
    weather: Annotated[WeatherSource, Depends(get_weather_source)],
) -> RouteConditions:
    record = session.get(RouteRecord, route_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No route has id {route_id}.")
    forecasts = get_route_forecasts(record_to_route(record).points, weather)
    return RouteConditions(
        weather=[LocationForecastResponse.model_validate(f) for f in forecasts]
    )
