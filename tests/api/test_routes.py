from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response

from goodtohike.api.routes import get_elevation_filler
from goodtohike.route import Point, RawPoint

SAMPLES = Path(__file__).parents[2] / "samples"
SYNTHETIC = SAMPLES / "synthetic"
HIKINGGUY = SAMPLES / "hikingguy" / "elevation_added"

GPX_CONTENT_TYPE = "application/gpx+xml"

# Nothing real is this high, so a point carrying it came from the fake.
FAKE_ELEVATION_M = 9_999.0


class CountingFiller:
    """Counts its calls and returns every point at one made-up elevation."""

    def __init__(self) -> None:
        self.calls = 0

    def fill(self, points: Sequence[RawPoint]) -> list[Point]:
        self.calls += 1
        return [(lat, lon, FAKE_ELEVATION_M) for lat, lon, _ in points]


def upload(client: TestClient, path: Path, **form: str) -> Response:
    return client.post(
        "/v1/routes",
        files={"file": (path.name, path.read_bytes(), GPX_CONTENT_TYPE)},
        data=form,
    )


def test_upload_returns_201_with_a_summary(client: TestClient):
    response = upload(client, SYNTHETIC / "one-clean-walk.gpx")

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Clean Walk"
    assert body["source"] == "gpx"
    assert body["point_count"] == 24
    # 23 hops of 0.0006 degrees due north, about 66.79 m each.
    assert body["length_m"] == pytest.approx(1_536.2, abs=0.1)


def test_upload_prefers_the_submitted_name(client: TestClient):
    response = upload(client, SYNTHETIC / "one-clean-walk.gpx", name="Test Walk")

    assert response.status_code == 201
    assert response.json()["name"] == "Test Walk"


def test_upload_uses_the_injected_elevation_filler(app: FastAPI, client: TestClient):
    filler = CountingFiller()
    app.dependency_overrides[get_elevation_filler] = lambda: filler

    response = upload(client, SYNTHETIC / "one-clean-walk.gpx")

    assert response.status_code == 201
    assert filler.calls == 1


def test_upload_accepts_a_real_track(client: TestClient):
    response = upload(client, HIKINGGUY / "lost-coast-trail.gpx")

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Lost Coast Trail Guide"
    # The Lost Coast Trail is about 40 km. A wide band, because the exact figure
    # moves whenever the gap thresholds are tuned.
    assert 35_000 < body["length_m"] < 45_000


def test_uploaded_route_can_be_fetched_from_its_location(client: TestClient):
    created = upload(client, SYNTHETIC / "one-clean-walk.gpx")

    fetched = client.get(created.headers["location"])

    assert fetched.status_code == 200
    assert fetched.json() == created.json()


def test_each_upload_gets_its_own_id(client: TestClient):
    first = upload(client, SYNTHETIC / "one-clean-walk.gpx").json()
    second = upload(client, SYNTHETIC / "one-clean-walk.gpx").json()

    assert first["id"] != second["id"]


def test_created_at_carries_a_utc_offset(client: TestClient):
    body = upload(client, SYNTHETIC / "one-clean-walk.gpx").json()

    created_at = datetime.fromisoformat(body["created_at"])

    assert created_at.utcoffset() == timedelta(0)


def test_unknown_route_is_a_404_problem(client: TestClient):
    response = client.get("/v1/routes/999")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["status"] == 404
