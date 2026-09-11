import httpx
import pytest

from goodtohike.clients.nws import NwsClient


def make_client(handler):
    transport = httpx.MockTransport(handler)
    return NwsClient(httpx.Client(transport=transport))


def test_get_point_returns_parsed_body_and_sends_accept():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["accept"] = request.headers["Accept"]
        return httpx.Response(200, json={"properties": {"gridId": "LOX"}})

    client = make_client(handler)
    result = client.get_point(34.2884, -117.6465)

    assert result["properties"]["gridId"] == "LOX"
    assert seen["url"] == "https://api.weather.gov/points/34.2884,-117.6465"
    assert seen["accept"] == "application/geo+json"


def test_get_point_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    client = make_client(handler)

    with pytest.raises(httpx.HTTPStatusError):
        client.get_point(0, 0)


def test_get_gridpoint_builds_grid_url():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
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

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"properties": {"periods": []}})

    client = make_client(handler)
    client.get_gridpoint_forecast("LOX", 178, 52)

    assert seen["url"] == "https://api.weather.gov/gridpoints/LOX/178,52/forecast"


def test_gridpoint_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "server error"})

    client = make_client(handler)

    with pytest.raises(httpx.HTTPStatusError):
        client.get_gridpoint("LOX", 178, 52)
