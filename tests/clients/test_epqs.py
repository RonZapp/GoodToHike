import threading
from collections.abc import Callable
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest

from goodtohike.clients.epqs import (
    ElevationServiceError,
    EpqsClient,
    NoElevationDataError,
)
from goodtohike.elevation import HybridFill

Handler = Callable[[httpx2.Request], httpx2.Response]

# Both messages EPQS was seen sending, as a 200, for a point in open ocean.
NO_DATA_MESSAGES = [
    "Invalid or missing input parameters.",
    "Call failed.  [Failed cloud operation: Open, Path: /vsimem/_000000B1.aux.xml]",
]


def make_client(handler: Handler, **settings) -> EpqsClient:
    transport = httpx2.MockTransport(handler)
    # No waiting between retries, so retry tests run instantly.
    settings.setdefault("backoff_s", 0.0)
    return EpqsClient(httpx2.Client(transport=transport), **settings)


def epqs_body(value: object) -> dict:
    """A successful EPQS response body, trimmed to what the client reads."""
    return {"locationId": 0, "value": value, "rasterId": 8857}


def query_of(request: httpx2.Request) -> dict[str, str]:
    return {
        key: values[0]
        for key, values in parse_qs(urlsplit(str(request.url)).query).items()
    }


class CountingHandler:
    """Answers each request with the next response in ``responses``, counting calls.

    Once the list runs out it keeps giving the last one. A response may be an
    exception, which is raised instead, the way a transport failure would be.
    """

    def __init__(self, *responses: httpx2.Response | Exception) -> None:
        self.responses = responses
        self.calls = 0
        self._lock = threading.Lock()

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        with self._lock:
            response = self.responses[min(self.calls, len(self.responses) - 1)]
            self.calls += 1
        if isinstance(response, Exception):
            raise response
        return response


# get_elevation, the request


def test_get_elevation_sends_longitude_as_x_and_latitude_as_y():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["path"] = request.url.path
        seen["host"] = request.url.host
        seen["query"] = query_of(request)
        return httpx2.Response(200, json=epqs_body("1234.5"))

    make_client(handler).get_elevation(46.8523, -121.7603)

    assert seen["host"] == "epqs.nationalmap.gov"
    assert seen["path"] == "/v1/json"
    assert seen["query"] == {
        "x": "-121.7603",
        "y": "46.8523",
        "wkid": "4326",
        "units": "Meters",
        "includeDate": "false",
    }


def test_get_elevation_uses_its_own_timeout_not_the_shared_clients():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["timeout"] = request.extensions["timeout"]
        return httpx2.Response(200, json=epqs_body("1.0"))

    http = httpx2.Client(transport=httpx2.MockTransport(handler), timeout=5.0)
    EpqsClient(http, timeout_s=20.0).get_elevation(46.85, -121.76)

    assert seen["timeout"]["read"] == 20.0


def test_get_elevation_sends_full_coordinate_precision():
    # EPQS accepts 17 significant digits, so nothing needs rounding first.
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["query"] = query_of(request)
        return httpx2.Response(200, json=epqs_body("1.0"))

    make_client(handler).get_elevation(46.123456789012344, -121.33876000000001)

    assert seen["query"]["y"] == "46.123456789012344"
    assert seen["query"]["x"] == "-121.33876000000001"


# get_elevation, reading the answer


def test_get_elevation_reads_the_value_sent_as_a_string():
    client = make_client(
        lambda _: httpx2.Response(200, json=epqs_body("4387.059082031"))
    )

    assert client.get_elevation(46.8523, -121.7603) == pytest.approx(4387.059082031)


def test_get_elevation_reads_the_value_sent_as_a_number():
    client = make_client(lambda _: httpx2.Response(200, json=epqs_body(1191.5)))

    assert client.get_elevation(47.8, -123.9) == 1191.5


@pytest.mark.parametrize("value", ["0.000000000", "-0.356616676"])
def test_get_elevation_keeps_sea_level_and_just_below_it(value):
    # Both measured on the Washington coast. Zero is an elevation, not missing.
    client = make_client(lambda _: httpx2.Response(200, json=epqs_body(value)))

    assert client.get_elevation(47.6, -122.4) == float(value)


@pytest.mark.parametrize("message", NO_DATA_MESSAGES)
def test_get_elevation_treats_a_plain_text_200_as_no_data(message):
    client = make_client(
        lambda _: httpx2.Response(
            200, text=message, headers={"Content-Type": "application/json"}
        )
    )

    with pytest.raises(NoElevationDataError) as caught:
        client.get_elevation(40.0, -130.0)

    assert (caught.value.lat, caught.value.lon) == (40.0, -130.0)
    assert message.strip() in str(caught.value)


def test_get_elevation_does_not_retry_no_data():
    handler = CountingHandler(httpx2.Response(200, text=NO_DATA_MESSAGES[0]))

    with pytest.raises(NoElevationDataError):
        make_client(handler, attempts=3).get_elevation(40.0, -130.0)

    assert handler.calls == 1


@pytest.mark.parametrize(
    "body",
    [
        {"locationId": 0},
        {"value": None},
        {"value": "not a number"},
        ["4387.0"],
    ],
    ids=["no value", "null value", "non-numeric value", "not an object"],
)
def test_get_elevation_rejects_json_without_a_readable_value(body):
    client = make_client(lambda _: httpx2.Response(200, json=body))

    with pytest.raises(ElevationServiceError) as caught:
        client.get_elevation(46.85, -121.76)

    assert not isinstance(caught.value, NoElevationDataError)


@pytest.mark.parametrize("value", ["-1000000", "9000.1", "-500.1", "NaN", "inf"])
def test_get_elevation_rejects_an_implausible_elevation(value):
    client = make_client(lambda _: httpx2.Response(200, json=epqs_body(value)))

    with pytest.raises(ElevationServiceError, match="implausible"):
        client.get_elevation(46.85, -121.76)


@pytest.mark.parametrize("value", ["-500", "9000"])
def test_get_elevation_accepts_the_edges_of_the_plausible_range(value):
    client = make_client(lambda _: httpx2.Response(200, json=epqs_body(value)))

    assert client.get_elevation(46.85, -121.76) == float(value)


# get_elevation, retries


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_get_elevation_retries_a_transient_status(status):
    handler = CountingHandler(
        httpx2.Response(status), httpx2.Response(200, json=epqs_body("12.5"))
    )

    assert make_client(handler).get_elevation(46.85, -121.76) == 12.5
    assert handler.calls == 2


@pytest.mark.parametrize(
    "error",
    [httpx2.ReadTimeout("timed out"), httpx2.ConnectError("connection refused")],
    ids=["timeout", "connection"],
)
def test_get_elevation_retries_a_transport_failure(error):
    handler = CountingHandler(error, httpx2.Response(200, json=epqs_body("12.5")))

    assert make_client(handler).get_elevation(46.85, -121.76) == 12.5
    assert handler.calls == 2


def test_get_elevation_gives_up_after_its_attempts():
    handler = CountingHandler(httpx2.ReadTimeout("timed out"))

    with pytest.raises(ElevationServiceError, match="after 3 attempts") as caught:
        make_client(handler, attempts=3).get_elevation(46.85, -121.76)

    assert handler.calls == 3
    assert isinstance(caught.value.__cause__, httpx2.ReadTimeout)


def test_get_elevation_with_one_attempt_never_retries():
    handler = CountingHandler(httpx2.Response(503))

    with pytest.raises(ElevationServiceError):
        make_client(handler, attempts=1).get_elevation(46.85, -121.76)

    assert handler.calls == 1


@pytest.mark.parametrize("status", [400, 403, 404])
def test_get_elevation_does_not_retry_a_rejected_request(status):
    handler = CountingHandler(
        httpx2.Response(
            status, json={"errorMessage": "[BadRequest] missing parameters"}
        )
    )

    with pytest.raises(ElevationServiceError, match="rejected"):
        make_client(handler, attempts=3).get_elevation(46.85, -121.76)

    assert handler.calls == 1


def test_get_elevation_waits_longer_before_each_retry(monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr("goodtohike.clients.epqs.sleep", waits.append)
    handler = CountingHandler(httpx2.Response(503))

    with pytest.raises(ElevationServiceError):
        make_client(handler, attempts=4, backoff_s=0.5).get_elevation(46.85, -121.76)

    assert waits == [0.5, 1.0, 2.0]


# get_elevations


def elevation_from_coordinates(request: httpx2.Request) -> httpx2.Response:
    """Answers with the latitude as the elevation, so each answer is traceable."""
    return httpx2.Response(200, json=epqs_body(query_of(request)["y"]))


def test_get_elevations_answers_in_the_order_asked():
    # Descending, so an answer sorted by value would not pass for one in order.
    coordinates = [(float(n), -121.0) for n in reversed(range(50))]

    result = make_client(elevation_from_coordinates).get_elevations(coordinates)

    assert result == [float(n) for n in reversed(range(50))]


def test_get_elevations_keeps_order_when_later_lookups_finish_first():
    first_may_answer = threading.Event()

    def handler(request: httpx2.Request) -> httpx2.Response:
        if query_of(request)["y"] == "9.0":
            # Holds the first point back until the second has answered.
            assert first_may_answer.wait(timeout=5)
        else:
            first_may_answer.set()
        return elevation_from_coordinates(request)

    client = make_client(handler, max_workers=2)

    assert client.get_elevations([(9.0, -121.0), (1.0, -121.0)]) == [9.0, 1.0]


def test_get_elevations_runs_lookups_at_the_same_time():
    # Every handler waits at the barrier until all four are inside it, which
    # can only happen if four lookups are in flight together.
    barrier = threading.Barrier(4, timeout=5)

    def handler(request: httpx2.Request) -> httpx2.Response:
        barrier.wait()
        return elevation_from_coordinates(request)

    client = make_client(handler, max_workers=4)

    assert client.get_elevations([(float(n), -121.0) for n in range(4)]) == [0, 1, 2, 3]


def test_get_elevations_of_nothing_makes_no_requests():
    handler = CountingHandler(httpx2.Response(500))

    assert make_client(handler).get_elevations([]) == []
    assert handler.calls == 0


def test_get_elevations_leaves_the_rest_of_a_batch_unrequested_after_a_failure():
    calls: list[float] = []
    far_down_the_batch = threading.Event()

    def handler(request: httpx2.Request) -> httpx2.Response:
        latitude = float(query_of(request)["y"])
        calls.append(latitude)
        if latitude >= 10:
            far_down_the_batch.set()
        if latitude == 0.0:
            # The first point gives the other worker time to run on through the
            # batch, if the batch is queued up front, before failing.
            far_down_the_batch.wait(timeout=0.5)
            return httpx2.Response(200, text=NO_DATA_MESSAGES[0])
        return elevation_from_coordinates(request)

    client = make_client(handler, max_workers=2)

    with pytest.raises(NoElevationDataError):
        client.get_elevations([(float(n), -121.0) for n in range(100)])

    assert not far_down_the_batch.is_set()
    assert len(calls) < 10


def test_get_elevations_raises_the_earliest_failing_point_not_the_first_to_fail():
    earlier_may_fail = threading.Event()

    def handler(request: httpx2.Request) -> httpx2.Response:
        latitude = float(query_of(request)["y"])
        if latitude == 0.0:
            # Point 0 fails only after point 1 already has.
            assert earlier_may_fail.wait(timeout=5)
            return httpx2.Response(200, text="no data at point 0")
        earlier_may_fail.set()
        return httpx2.Response(200, text="no data at point 1")

    client = make_client(handler, max_workers=2)

    with pytest.raises(NoElevationDataError) as caught:
        client.get_elevations([(0.0, -121.0), (1.0, -121.0)])

    assert caught.value.lat == 0.0


# Settings


@pytest.mark.parametrize("settings", [{"max_workers": 0}, {"attempts": 0}])
def test_client_rejects_settings_that_could_never_look_anything_up(settings):
    with pytest.raises(ValueError):
        EpqsClient(httpx2.Client(), **settings)


# With an elevation filler


def test_get_elevations_works_as_a_fillers_fetcher():
    client = make_client(elevation_from_coordinates)
    filler = HybridFill(fetch=client.get_elevations)
    track = [(46.0, -121.0, None), (46.001, -121.0, None)]

    filled = filler.fill(track)

    assert [elevation for _, _, elevation in filled] == [46.0, 46.001]
