from collections.abc import Sequence
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from httpx2 import Response

from goodtohike.api.routes import get_elevation_filler
from goodtohike.gpx import NO_POINTS, NOT_DECODABLE, NOT_GPX, ROUTE_NOT_TRACK
from goodtohike.route import Point, RawPoint

SAMPLES = Path(__file__).parents[2] / "samples"
SYNTHETIC = SAMPLES / "synthetic"
MULTI_TRACK = SAMPLES / "hikingguy" / "elevation_added" / "multi_track"

GPX_CONTENT_TYPE = "application/gpx+xml"

# Written out rather than imported, so a typo in the source cannot also be
# the thing the test expects.
PROBLEM_CONTENT_TYPE = "application/problem+json"
PROBLEM_DOCS = "https://github.com/RonZapp/GoodToHike/blob/main/docs/problems.md"
RFC_9457_FIELDS = {"type", "title", "status", "detail", "instance"}

# If this text ever reaches a response, internals are leaking to callers.
INTERNAL_MESSAGE = "internal detail from /srv/goodtohike that must not leak"


class BrokenFiller:
    """Fails the way a bug would, with a message no caller should ever see."""

    def fill(self, points: Sequence[RawPoint]) -> list[Point]:
        raise RuntimeError(INTERNAL_MESSAGE)


def gpx(body: str) -> bytes:
    """A minimal GPX 1.1 document wrapped around ``body``."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<gpx version="1.1" creator="test" '
        'xmlns="http://www.topografix.com/GPX/1/1">'
        f"{body}</gpx>"
    ).encode()


def upload(client: TestClient, content: bytes) -> Response:
    return client.post(
        "/v1/routes",
        files={"file": ("upload.gpx", content, GPX_CONTENT_TYPE)},
    )


def assert_problem(
    response: Response, status: int, slug: str | None, instance: str = "/v1/routes"
) -> dict:
    """Check the parts every problem response shares, and return its body.

    A ``slug`` of None expects ``about:blank``, the type for a problem that
    means no more than its status code.
    """
    assert response.status_code == status
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    body = response.json()
    assert set(body) == RFC_9457_FIELDS
    assert body["type"] == (f"{PROBLEM_DOCS}#{slug}" if slug else "about:blank")
    assert body["status"] == status
    assert body["instance"] == instance
    return body


@pytest.mark.parametrize(
    "filename",
    [
        "drive-mid-track.gpx",
        "drive-between-segments.gpx",
        "walk-with-annotation-track.gpx",
    ],
)
def test_broken_track_is_a_track_gap_problem(client: TestClient, filename):
    response = upload(client, (SYNTHETIC / filename).read_bytes())

    body = assert_problem(response, 422, "track-gap")
    assert body["title"] == "Track is not one continuous walk"
    assert "km" in body["detail"]


def test_real_file_with_feature_tracks_is_a_track_gap_problem(client: TestClient):
    # The trail plus hazard zones stored as extra tracks.
    response = upload(client, (MULTI_TRACK / "lost-coast-trail.gpx").read_bytes())

    body = assert_problem(response, 422, "track-gap")
    assert "do not join up" in body["detail"]


def test_track_without_elevation_is_a_no_elevation_problem(client: TestClient):
    content = gpx(
        "<trk><trkseg>"
        '<trkpt lat="45.0" lon="-121.0"/>'
        '<trkpt lat="45.0006" lon="-121.0"/>'
        "</trkseg></trk>"
    )

    response = upload(client, content)

    body = assert_problem(response, 422, "no-elevation")
    assert body["title"] == "Track has no elevation"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"\xff\xfe\x00not utf-8", NOT_DECODABLE),
        (b"this is not xml", NOT_GPX),
        (
            gpx(
                "<rte>"
                '<rtept lat="45.0" lon="-121.0"/>'
                '<rtept lat="45.1" lon="-121.0"/>'
                "</rte>"
            ),
            ROUTE_NOT_TRACK,
        ),
        (gpx("<trk><trkseg></trkseg></trk>"), NO_POINTS),
    ],
    ids=["not-utf-8", "not-gpx", "route-not-track", "no-points"],
)
def test_unusable_file_is_an_invalid_gpx_problem(
    client: TestClient, content: bytes, message: str
):
    response = upload(client, content)

    body = assert_problem(response, 422, "invalid-gpx")
    # The uploader-facing message from goodtohike.gpx reaches them unchanged.
    assert body["detail"] == message


# Errors raised by FastAPI and Starlette rather than by GoodToHike


def test_missing_file_is_an_invalid_request_problem(client: TestClient):
    response = client.post("/v1/routes")

    body = assert_problem(response, 422, "invalid-request")
    assert body["title"] == "Request is not valid"
    assert body["detail"] == "body.file: Field required"


def test_invalid_request_describes_every_error(app: FastAPI):
    @app.get("/needs-two")
    def needs_two(first: int, second: int) -> None: ...

    response = TestClient(app).get("/needs-two")

    body = assert_problem(response, 422, "invalid-request", instance="/needs-two")
    assert body["detail"] == (
        "query.first: Field required; query.second: Field required"
    )


def test_unknown_path_is_a_not_found_problem(client: TestClient):
    response = client.get("/v1/nowhere")

    body = assert_problem(response, 404, None, instance="/v1/nowhere")
    assert body["title"] == "Not Found"


def test_wrong_method_is_a_problem_that_keeps_the_allow_header(client: TestClient):
    response = client.get("/v1/routes")

    body = assert_problem(response, 405, None)
    assert body["title"] == "Method Not Allowed"
    assert response.headers["allow"] == "POST"


def test_http_exception_raised_by_an_endpoint_keeps_its_detail(app: FastAPI):
    @app.get("/conflict")
    def conflict() -> None:
        raise HTTPException(status_code=409, detail="That route already exists.")

    response = TestClient(app).get("/conflict")

    body = assert_problem(response, 409, None, instance="/conflict")
    assert body["title"] == "Conflict"
    assert body["detail"] == "That route already exists."


def test_unexpected_error_is_a_generic_500_problem(app: FastAPI):
    app.dependency_overrides[get_elevation_filler] = lambda: BrokenFiller()
    # By default TestClient re-raises server errors into the test. Turning that
    # off shows the response a real caller would receive.
    client = TestClient(app, raise_server_exceptions=False)

    response = upload(client, (SYNTHETIC / "one-clean-walk.gpx").read_bytes())

    body = assert_problem(response, 500, None)
    assert body["title"] == "Internal Server Error"
    assert INTERNAL_MESSAGE not in response.text
