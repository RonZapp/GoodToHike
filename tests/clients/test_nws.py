from datetime import UTC, datetime, timedelta, timezone

import httpx2
import pytest

from goodtohike.clients.nws import NwsClient, NwsWeather
from goodtohike.conditions import GridCell, NoWeatherCoverageError, WeatherServiceError


def make_client(handler):
    transport = httpx2.MockTransport(handler)
    return NwsClient(httpx2.Client(transport=transport))


def test_get_point_returns_parsed_body_and_sends_accept():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["url"] = str(request.url)
        seen["accept"] = request.headers["Accept"]
        return httpx2.Response(200, json={"properties": {"gridId": "LOX"}})

    client = make_client(handler)
    result = client.get_point(34.2884, -117.6465)

    assert result["properties"]["gridId"] == "LOX"
    assert seen["url"] == "https://api.weather.gov/points/34.2884,-117.6465"
    assert seen["accept"] == "application/geo+json"


def test_get_point_rounds_coordinates_to_four_places():
    # A real track's precision. Sent as is, /points answers with a 301.
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["url"] = str(request.url)
        return httpx2.Response(200, json={"properties": {"gridId": "PQR"}})

    make_client(handler).get_point(45.331289, -121.710876)

    assert seen["url"] == "https://api.weather.gov/points/45.3313,-121.7109"


def test_get_point_raises_on_http_error():
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(404, json={"detail": "not found"})

    client = make_client(handler)

    with pytest.raises(httpx2.HTTPStatusError):
        client.get_point(0, 0)


def test_get_gridpoint_builds_grid_url():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["url"] = str(request.url)
        return httpx2.Response(
            200,
            json={
                "properties": {
                    "updateTime": "2026-09-11T04:00:00+00:00",
                    "temperature": {"values": [{"validTime": "x", "value": 21.1}]},
                }
            },
        )

    client = make_client(handler)
    result = client.get_gridpoint("LOX", 178, 52)

    assert seen["url"] == "https://api.weather.gov/gridpoints/LOX/178,52"
    assert result["properties"]["temperature"]["values"][0]["value"] == 21.1


def test_get_gridpoint_forecast_builds_forecast_url():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["url"] = str(request.url)
        return httpx2.Response(200, json={"properties": {"periods": []}})

    client = make_client(handler)
    client.get_gridpoint_forecast("LOX", 178, 52)

    assert (
        seen["url"] == "https://api.weather.gov/gridpoints/LOX/178,52/forecast?units=si"
    )


def test_gridpoint_raises_on_http_error():
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(500, json={"detail": "server error"})

    client = make_client(handler)

    with pytest.raises(httpx2.HTTPStatusError):
        client.get_gridpoint("LOX", 178, 52)


# NwsWeather

POINT_BODY = {"properties": {"gridId": "PQR", "gridX": 142, "gridY": 89}}

PERIOD = {
    "number": 1,
    "name": "Today",
    "startTime": "2026-09-14T06:00:00-07:00",
    "endTime": "2026-09-14T18:00:00-07:00",
    "isDaytime": True,
    "temperature": 9,
    "temperatureUnit": "C",
    "probabilityOfPrecipitation": {"unitCode": "wmoUnit:percent", "value": 2},
    "windSpeed": "7 to 17 km/h",
    "windDirection": "WNW",
    "shortForecast": "Mostly Sunny",
    "detailedForecast": "Mostly sunny, with a high near 9.",
}

FORECAST_BODY = {
    "properties": {
        "units": "si",
        "updateTime": "2026-09-14T13:41:27+00:00",
        "elevation": {"unitCode": "wmoUnit:m", "value": 1932.1272},
        "periods": [PERIOD],
    }
}

CELL = GridCell(office="PQR", x=142, y=89)


def make_weather(handler) -> NwsWeather:
    return NwsWeather(make_client(handler))


def answering(status: int, **kwargs) -> NwsWeather:
    return make_weather(lambda _: httpx2.Response(status, **kwargs))


def test_cell_comes_from_the_points_body():
    assert answering(200, json=POINT_BODY).get_cell(45.3313, -121.7109) == CELL


def test_point_without_coverage_is_no_weather_coverage():
    weather = answering(404, json={"title": "Data Unavailable For Requested Point"})

    with pytest.raises(NoWeatherCoverageError) as caught:
        weather.get_cell(40.0, -130.0)

    assert (caught.value.lat, caught.value.lon) == (40.0, -130.0)


@pytest.mark.parametrize("status", [400, 500, 503])
def test_points_failure_is_a_weather_service_error(status):
    with pytest.raises(WeatherServiceError):
        answering(status, json={}).get_cell(45.0, -121.0)


def test_points_timeout_is_a_weather_service_error():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("timed out", request=request)

    with pytest.raises(WeatherServiceError):
        make_weather(handler).get_cell(45.0, -121.0)


@pytest.mark.parametrize(
    "body",
    [{}, {"properties": {}}, {"properties": {"gridId": "PQR", "gridX": "east"}}],
)
def test_points_body_without_a_cell_is_a_weather_service_error(body):
    with pytest.raises(WeatherServiceError):
        answering(200, json=body).get_cell(45.0, -121.0)


def test_points_body_that_is_not_json_is_a_weather_service_error():
    with pytest.raises(WeatherServiceError):
        answering(200, text="<html>maintenance</html>").get_cell(45.0, -121.0)


def test_forecast_is_read_from_the_forecast_body():
    forecast = answering(200, json=FORECAST_BODY).get_forecast(CELL)

    assert forecast.updated_at == datetime(2026, 9, 14, 13, 41, 27, tzinfo=UTC)
    assert forecast.elevation_m == 1932.1272
    [period] = forecast.periods
    assert period.name == "Today"
    assert period.start_time == datetime(
        2026, 9, 14, 6, tzinfo=timezone(timedelta(hours=-7))
    )
    assert period.is_daytime is True
    assert period.temperature_c == 9.0
    assert period.precipitation_chance_percent == 2
    assert period.wind_speed == "7 to 17 km/h"
    assert period.wind_direction == "WNW"
    assert period.short_forecast == "Mostly Sunny"


def test_forecast_requests_the_cell_it_was_given():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["url"] = str(request.url)
        return httpx2.Response(200, json=FORECAST_BODY)

    make_weather(handler).get_forecast(CELL)

    assert seen["url"] == (
        "https://api.weather.gov/gridpoints/PQR/142,89/forecast?units=si"
    )


def test_missing_precipitation_chance_is_none():
    period = {**PERIOD, "probabilityOfPrecipitation": {"value": None}}
    body = {"properties": {**FORECAST_BODY["properties"], "periods": [period]}}

    forecast = answering(200, json=body).get_forecast(CELL)

    assert forecast.periods[0].precipitation_chance_percent is None


def test_forecast_in_fahrenheit_is_a_weather_service_error():
    period = {**PERIOD, "temperature": 49, "temperatureUnit": "F"}
    body = {"properties": {**FORECAST_BODY["properties"], "periods": [period]}}

    with pytest.raises(WeatherServiceError):
        answering(200, json=body).get_forecast(CELL)


@pytest.mark.parametrize("status", [404, 500, 503])
def test_forecast_failure_is_a_weather_service_error(status):
    with pytest.raises(WeatherServiceError):
        answering(status, json={}).get_forecast(CELL)


def test_unreadable_forecast_is_a_weather_service_error():
    with pytest.raises(WeatherServiceError):
        answering(200, json={"properties": {"periods": [{}]}}).get_forecast(CELL)
