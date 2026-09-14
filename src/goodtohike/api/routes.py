"""The /routes endpoints:

submitting a track and reading back the route built from it.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from goodtohike.elevation import ElevationFiller
from goodtohike.geometry import get_cumulative_m
from goodtohike.gpx import parse_gpx
from goodtohike.ingest import build_route

router = APIRouter(tags=["routes"])


class RouteSummary(BaseModel):
    name: str
    source: str
    point_count: int
    length_m: float


def get_elevation_filler(request: Request) -> ElevationFiller:
    return request.app.state.elevation_filler


def get_session(request: Request) -> Iterator[Session]:
    """A database session for one request, closed once the response is sent."""
    with Session(request.app.state.engine) as session:
        yield session


@router.post("/routes", status_code=201)
def create_route(
    file: Annotated[UploadFile, File()],
    elevation_filler: Annotated[ElevationFiller, Depends(get_elevation_filler)],
    name: Annotated[str | None, Form()] = None,
) -> RouteSummary:
    raw = file.file.read()
    track = parse_gpx(raw)
    route = build_route(track, elevation_filler, name)
    return RouteSummary(
        name=route.name,
        source=track.source,
        point_count=len(route.points),
        length_m=get_cumulative_m(route.points)[-1],
    )
