"""Error responses in the RFC 9457 problem details format."""

import logging
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from goodtohike.clients.epqs import ElevationServiceError, NoElevationDataError
from goodtohike.elevation import NoElevationError
from goodtohike.gaps import TrackGapError
from goodtohike.gpx import GpxError

PROBLEM_CONTENT_TYPE = "application/problem+json"
PROBLEM_TYPE_BASE = "https://github.com/RonZapp/GoodToHike/blob/main/docs/problems.md#"

# The type RFC 9457 reserves for a problem that means no more than its status
# code. Its title should be that status code's standard phrase.
NO_SPECIFIC_TYPE = "about:blank"

# Deliberately fixed. An unexpected error's own message can expose internals
# such as file paths or queries, so it goes to the server log, not the caller.
UNEXPECTED_ERROR_DETAIL = "The server hit an unexpected error handling this request."

# Fixed for the same reason. An elevation service error can carry part of the
# upstream response, which is for the server log, not the caller.
ELEVATION_SERVICE_DETAIL = (
    "The elevation service failed to answer, so elevation for this track could "
    "not be looked up. Try again later."
)

logger = logging.getLogger(__name__)


def problem(
    request: Request,
    status: int,
    slug: str | None,
    title: str,
    detail: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Build a problem details response.

    ``slug`` names one of GoodToHike's documented problem types. None means the
    status code already says everything, and the type becomes ``about:blank``.
    """
    problem_type = PROBLEM_TYPE_BASE + slug if slug else NO_SPECIFIC_TYPE
    return JSONResponse(
        status_code=status,
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers,
        content={
            "type": problem_type,
            "title": title,
            "status": status,
            "detail": detail,
            "instance": request.url.path,
        },
    )


async def handle_track_gap(request: Request, exc: Exception) -> JSONResponse:
    return problem(
        request,
        status=422,
        slug="track-gap",
        title="Track is not one continuous walk",
        detail=str(exc),
    )


async def handle_no_elevation(request: Request, exc: Exception) -> JSONResponse:
    return problem(
        request,
        status=422,
        slug="no-elevation",
        title="Track has no elevation",
        detail=str(exc),
    )


async def handle_outside_elevation_coverage(
    request: Request, exc: Exception
) -> JSONResponse:
    assert isinstance(exc, NoElevationDataError)
    # Built from the coordinates rather than str(exc), which quotes the elevation
    # service's own wording, meaningless to an uploader.
    return problem(
        request,
        status=422,
        slug="outside-elevation-coverage",
        title="Track is outside elevation coverage",
        detail=(
            f"No elevation data exists at {exc.lat}, {exc.lon}, so elevation "
            "could not be looked up for this track. Lookups cover the United "
            "States. Upload a track that carries its own elevation."
        ),
    )


async def handle_elevation_service_error(
    request: Request, exc: Exception
) -> JSONResponse:
    # Unlike the catch-all 500, nothing re-raises a handled error, so this is
    # the only place it can reach the server log.
    logger.error("elevation service failed", exc_info=exc)
    return problem(
        request,
        status=502,
        slug="elevation-service-failed",
        title="Elevation service failed",
        detail=ELEVATION_SERVICE_DETAIL,
    )


async def handle_gpx_error(request: Request, exc: Exception) -> JSONResponse:
    return problem(
        request,
        status=422,
        slug="invalid-gpx",
        title="The GPX could not be processed",
        detail=str(exc),
    )


def _describe_validation_error(error: Mapping[str, Any]) -> str:
    """One validation error as ``location: message``."""
    location = ".".join(str(part) for part in error["loc"])
    return f"{location}: {error['msg']}"


async def handle_invalid_request(request: Request, exc: Exception) -> JSONResponse:
    # add_exception_handler only promises an Exception. The assert narrows the
    # type for pyright, the same way Starlette's own default handlers do.
    assert isinstance(exc, RequestValidationError)
    return problem(
        request,
        status=422,
        slug="invalid-request",
        title="Request is not valid",
        detail="; ".join(_describe_validation_error(e) for e in exc.errors()),
    )


async def handle_http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    return problem(
        request,
        status=exc.status_code,
        slug=None,
        title=HTTPStatus(exc.status_code).phrase,
        detail=str(exc.detail),
        # A 405 must say which methods are allowed, and it says so in a header.
        headers=exc.headers,
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # Starlette re-raises the exception after sending this response, so the
    # server still logs the real error.
    return problem(
        request,
        status=500,
        slug=None,
        title=HTTPStatus.INTERNAL_SERVER_ERROR.phrase,
        detail=UNEXPECTED_ERROR_DETAIL,
    )


def add_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(TrackGapError, handle_track_gap)
    app.add_exception_handler(NoElevationError, handle_no_elevation)
    # Starlette picks the handler for the most specific class in an error's
    # MRO, so the subclass gets its own handler whatever the order here.
    app.add_exception_handler(NoElevationDataError, handle_outside_elevation_coverage)
    app.add_exception_handler(ElevationServiceError, handle_elevation_service_error)
    app.add_exception_handler(GpxError, handle_gpx_error)
    app.add_exception_handler(RequestValidationError, handle_invalid_request)
    # Starlette's class rather than FastAPI's subclass of it, because the
    # router raises Starlette's for unknown paths and wrong methods.
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
