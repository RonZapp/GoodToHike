"""Uploading a track with no elevation through the app's default elevation fill,
against the real USGS elevation service. Run with ``uv run pytest -m network``.
"""

import re
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from goodtohike.api.app import get_app
from goodtohike.clients.epqs import EpqsClient
from goodtohike.gpx import parse_gpx
from goodtohike.http import make_http_client

pytestmark = pytest.mark.network

# About 21 km, so a whole-track lookup at the default spacing is around a
# hundred requests: enough to exercise batching, few enough to stay quick.
ENCHANTED_VALLEY = (
    Path(__file__).parents[2]
    / "samples"
    / "hikingguy"
    / "elevation_added"
    / "enchanted-valley.gpx"
)


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    app = get_app(title="GoodToHike", version="test", engine=engine)
    with TestClient(app) as client:
        yield client


def test_upload_without_elevation_is_filled_from_the_elevation_service(
    client: TestClient,
):
    raw = ENCHANTED_VALLEY.read_bytes()
    without_elevation = re.sub(rb"<ele>[^<]*</ele>", b"", raw)
    assert parse_gpx(without_elevation).points[0][2] is None

    started = time.perf_counter()
    created = client.post(
        "/v1/routes",
        files={"file": ("valley.gpx", without_elevation, "application/gpx+xml")},
    )
    elapsed_s = time.perf_counter() - started

    assert created.status_code == 201, created.text
    profile = client.get(f"{created.headers['location']}/profile").json()

    # The track's first point is always looked up, so it has to match the
    # service asked directly. The file's own elevation is not a reference: it
    # was generated, and differs from 3DEP by about 20 m.
    lat, lon, _ = parse_gpx(raw).points[0]
    with make_http_client() as http:
        direct = EpqsClient(http).get_elevation(lat, lon)
    assert profile["points"][0]["elevation_m"] == pytest.approx(direct, abs=0.01)

    # The Enchanted Valley trail runs from about 200 m up to about 700 m.
    elevations = [point["elevation_m"] for point in profile["points"]]
    assert 100 < min(elevations) < max(elevations) < 1_000
    assert profile["gain_m"] > 300
    # Under 10 s when the service is quiet. A slow day can take far longer,
    # so this is reported rather than asserted.
    print(f"upload with lookups took {elapsed_s:.1f} s")
