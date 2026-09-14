import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response

from goodtohike.api.routes import get_elevation_filler, get_weather_source
from goodtohike.conditions import (
    Forecast,
    ForecastPeriod,
    GridCell,
    NoWeatherCoverageError,
)
from goodtohike.elevation import HybridFill
from goodtohike.elevation_profile import MAX_PROFILE_POINTS, PROFILE_SPACING_M
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


class OneCellWeather:
    """Puts everywhere in one cell with a one-period forecast, and counts requests."""

    def __init__(self, covered: bool = True) -> None:
        self.covered = covered
        self.forecast_requests = 0

    def get_cell(self, lat: float, lon: float) -> GridCell:
        if not self.covered:
            raise NoWeatherCoverageError(lat, lon)
        return GridCell(office="TST", x=1, y=2)

    def get_forecast(self, cell: GridCell) -> Forecast:
        self.forecast_requests += 1
        start = datetime(2026, 9, 14, 13, tzinfo=UTC)
        return Forecast(
            updated_at=start,
            elevation_m=1_500.0,
            periods=[
                ForecastPeriod(
                    name="Today",
                    start_time=start,
                    end_time=start + timedelta(hours=12),
                    is_daytime=True,
                    temperature_c=9.0,
                    precipitation_chance_percent=None,
                    wind_speed="7 to 17 km/h",
                    wind_direction="WNW",
                    short_forecast="Mostly Sunny",
                    detailed_forecast="Mostly sunny, with a high near 9.",
                )
            ],
        )


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


def test_upload_without_elevation_is_filled_by_lookups(
    app: FastAPI, client: TestClient
):
    asked: list[tuple[float, float]] = []

    def fetch(coordinates: Sequence[tuple[float, float]]) -> list[float]:
        asked.extend(coordinates)
        return [FAKE_ELEVATION_M] * len(coordinates)

    app.dependency_overrides[get_elevation_filler] = lambda: HybridFill(fetch=fetch)
    without_elevation = re.sub(
        rb"<ele>[^<]*</ele>", b"", (SYNTHETIC / "one-clean-walk.gpx").read_bytes()
    )

    created = client.post(
        "/v1/routes",
        files={"file": ("walk.gpx", without_elevation, GPX_CONTENT_TYPE)},
    )

    assert created.status_code == 201
    assert asked
    profile = client.get(f"{created.headers['location']}/profile").json()
    assert {point["elevation_m"] for point in profile["points"]} == {FAKE_ELEVATION_M}


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


def test_profile_of_an_uploaded_route(client: TestClient):
    created = upload(client, SYNTHETIC / "one-clean-walk.gpx")

    response = client.get(f"{created.headers['location']}/profile")

    assert response.status_code == 200
    body = response.json()
    assert body["spacing_m"] == PROFILE_SPACING_M
    assert body["length_m"] == pytest.approx(created.json()["length_m"])
    first, last = body["points"][0], body["points"][-1]
    assert first["distance_m"] == 0.0
    assert first["grade_percent"] is None
    assert last["distance_m"] == pytest.approx(body["length_m"])


def test_profile_of_a_real_track_is_spread_out(client: TestClient):
    created = upload(client, HIKINGGUY / "lost-coast-trail.gpx")

    body = client.get(f"{created.headers['location']}/profile").json()

    points = body["points"]
    assert len(points) <= MAX_PROFILE_POINTS
    # About 40 km at 50 m spacing, so hundreds of points, not the whole track.
    assert 600 < len(points) < created.json()["point_count"]
    distances = [point["distance_m"] for point in points]
    assert distances == sorted(distances)
    assert body["gain_m"] > 0
    assert body["loss_m"] > 0


def test_profile_of_unknown_route_is_a_404_problem(client: TestClient):
    response = client.get("/v1/routes/999/profile")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["status"] == 404


def test_conditions_forecast_the_start_end_and_high_point(
    app: FastAPI, client: TestClient
):
    weather = OneCellWeather()
    app.dependency_overrides[get_weather_source] = lambda: weather
    created = upload(client, HIKINGGUY / "lost-coast-trail.gpx")

    response = client.get(f"{created.headers['location']}/conditions")

    assert response.status_code == 200
    locations = response.json()["weather"]
    assert locations[0]["distance_m"] == 0.0
    assert locations[-1]["distance_m"] == pytest.approx(created.json()["length_m"])
    assert sum(location["is_high_point"] for location in locations) == 1
    # Every location is in the one cell, so one forecast serves them all.
    assert weather.forecast_requests == 1
    period = locations[0]["forecast"]["periods"][0]
    assert period["temperature_c"] == 9.0
    assert period["precipitation_chance_percent"] is None
    assert datetime.fromisoformat(period["start_time"]).utcoffset() == timedelta(0)


def test_conditions_outside_coverage_have_no_forecast(app: FastAPI, client: TestClient):
    app.dependency_overrides[get_weather_source] = lambda: OneCellWeather(covered=False)
    created = upload(client, SYNTHETIC / "one-clean-walk.gpx")

    response = client.get(f"{created.headers['location']}/conditions")

    assert response.status_code == 200
    assert [location["forecast"] for location in response.json()["weather"]] == [
        None,
        None,
    ]


def test_conditions_of_unknown_route_is_a_404_problem(client: TestClient):
    response = client.get("/v1/routes/999/conditions")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
