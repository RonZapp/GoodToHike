"""The National Weather Service itself, over the network. Run with
``uv run pytest -m network``.

The mocked tests in test_nws.py assert what the service was seen doing; these
check it still does.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from goodtohike.clients.nws import NwsClient, NwsWeather
from goodtohike.conditions import NoWeatherCoverageError, get_route_forecasts
from goodtohike.elevation import InterpolateOnly
from goodtohike.gpx import parse_gpx
from goodtohike.http import make_http_client
from goodtohike.ingest import build_route

pytestmark = pytest.mark.network

TIMBERLINE = (
    Path(__file__).parents[2]
    / "samples"
    / "hikingguy"
    / "elevation_added"
    / "timberline-trail.gpx"
)


@pytest.fixture
def weather() -> Iterator[NwsWeather]:
    with make_http_client() as http:
        yield NwsWeather(NwsClient(http))


def test_a_real_track_point_finds_its_cell(weather):
    # Exactly as the file records it, six decimal places. Unrounded, /points
    # answers with a redirect rather than a cell.
    lat, lon, _ = parse_gpx(TIMBERLINE.read_bytes()).points[0]

    cell = weather.get_cell(lat, lon)

    # Timberline Lodge on Mount Hood, forecast by the Portland office.
    assert cell.office == "PQR"


def test_open_ocean_has_no_weather_coverage(weather):
    with pytest.raises(NoWeatherCoverageError):
        weather.get_cell(40.0, -130.0)


def test_a_real_route_gets_metric_forecasts(weather):
    route = build_route(parse_gpx(TIMBERLINE.read_bytes()), InterpolateOnly())

    located = get_route_forecasts(route.points, weather)

    assert len(located) >= 3
    assert any(location.is_high_point for location in located)
    for location in located:
        assert location.forecast is not None
        assert location.forecast.periods
        for period in location.forecast.periods:
            # Celsius on Mount Hood, where Fahrenheit would read far higher.
            assert -40 < period.temperature_c < 45
            assert period.start_time.utcoffset() is not None
