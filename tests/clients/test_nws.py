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
