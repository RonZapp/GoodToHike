"""Client for the USGS Elevation Point Query Service (EPQS).

EPQS reads the 3D Elevation Program (3DEP) dataset, bare-earth elevation for
the United States at up to 1 m resolution. It answers one point per request, so
``get_elevations`` spreads a batch of points across a small pool of threads.
Upstream behaviour this relies on is recorded in ``docs/sources/epqs.md``.
"""

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from time import sleep

import httpx2

BASE_URL = "https://epqs.nationalmap.gov/v1"

# The spatial reference EPQS should read coordinates in: plain latitude and
# longitude on WGS 84, which is what GPX carries.
WGS84 = 4326

# Lookups in flight at once for one batch. Measured 2026-09-14: 40 lookups took
# 13.3 s one at a time and 1.2 s across 8 threads, with no throttling at 16.
DEFAULT_MAX_WORKERS = 8

# Per request, replacing the shared client's shorter default. EPQS slows down
# under load: on 2026-09-14 its median went from 0.24 s to 2 s within an hour,
# single requests took up to 10.5 s, and a 5 s timeout failed one point three
# times running. About twice the slowest request seen.
DEFAULT_TIMEOUT_S = 20.0

# Tries per point, the first one included.
DEFAULT_ATTEMPTS = 3

# Wait before the first retry, doubling before each one after it.
DEFAULT_BACKOFF_S = 0.5

# Lowest and highest ground on Earth, the Dead Sea shore and Everest, with a
# margin. A value outside it is a sentinel or garbage, not an elevation.
MIN_PLAUSIBLE_M = -500.0
MAX_PLAUSIBLE_M = 9_000.0


class ElevationServiceError(Exception):
    """EPQS gave no usable elevation: it failed, or sent something unreadable."""


class NoElevationDataError(ElevationServiceError):
    """EPQS has no elevation for a location, such as open ocean or outside the US."""

    def __init__(self, lat: float, lon: float, message: str) -> None:
        super().__init__(f"no elevation data at {lat},{lon}: {message}")
        self.lat = lat
        self.lon = lon


class EpqsClient:
    base_url = BASE_URL

    def __init__(
        self,
        http: httpx2.Client,
        *,
        max_workers: int = DEFAULT_MAX_WORKERS,
        attempts: int = DEFAULT_ATTEMPTS,
        backoff_s: float = DEFAULT_BACKOFF_S,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        if max_workers < 1:
            raise ValueError(f"max_workers must be at least 1, got {max_workers}")
        if attempts < 1:
            raise ValueError(f"attempts must be at least 1, got {attempts}")
        self._http = http
        self.max_workers = max_workers
        self.attempts = attempts
        self.backoff_s = backoff_s
        self.timeout_s = timeout_s

    def get_elevation(self, lat: float, lon: float) -> float:
        """Bare-earth elevation in metres at one point.

        Raises NoElevationDataError where EPQS has no data, and
        ElevationServiceError when EPQS rejects the request, is still failing
        after ``attempts`` tries, or answers with anything but a plausible
        elevation.
        """
        response = self._query(lat, lon)
        return _read_elevation(response, lat, lon)

    def get_elevations(self, coordinates: Sequence[tuple[float, float]]) -> list[float]:
        """Elevations in metres for each ``(lat, lon)``, in the same order.

        Matches ``ElevationFetcher``, so ``client.get_elevations`` can be handed
        to a filler as its ``fetch``. Up to ``max_workers`` lookups run at once.

        Raises the error ``get_elevation`` raised for the earliest point that
        failed. Lookups are only started a few at a time, so a failure early in
        a long batch leaves the rest of it unrequested.
        """
        if not coordinates:
            return []

        workers = min(self.max_workers, len(coordinates))
        latitudes = [lat for lat, _ in coordinates]
        longitudes = [lon for _, lon in coordinates]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            # Without a buffer, map submits the whole batch up front, and a
            # failure could not stop lookups already queued. With one, it
            # submits no more than ``workers`` ahead of the result it is
            # waiting on, and cancels those when a result raises.
            return list(
                pool.map(self.get_elevation, latitudes, longitudes, buffersize=workers)
            )

    def _query(self, lat: float, lon: float) -> httpx2.Response:
        """The successful response for one point, retrying transient failures.

        Retries timeouts, dropped connections, throttling and server errors,
        waiting ``backoff_s`` before the first retry and doubling after that.
        Any other failing status means the request itself is wrong, so it
        raises at once.
        """
        params = {
            "x": lon,
            "y": lat,
            "wkid": WGS84,
            "units": "Meters",
            "includeDate": "false",
        }
        failure: Exception | None = None
        for attempt in range(self.attempts):
            if attempt:
                sleep(self.backoff_s * 2 ** (attempt - 1))
            try:
                response = self._http.get(
                    f"{self.base_url}/json", params=params, timeout=self.timeout_s
                )
                response.raise_for_status()
            except httpx2.HTTPStatusError as exc:
                if not _is_transient(exc.response.status_code):
                    raise ElevationServiceError(
                        f"EPQS rejected the request for {lat},{lon}: {exc}"
                    ) from exc
                failure = exc
            except httpx2.TransportError as exc:
                failure = exc
            else:
                return response

        raise ElevationServiceError(
            f"EPQS still failing for {lat},{lon} after {self.attempts} attempts: "
            f"{failure!r}"
        ) from failure


def _is_transient(status: int) -> bool:
    """Whether a failing status might pass on a second try: throttling, or the
    server's own failure."""
    return status == HTTPStatus.TOO_MANY_REQUESTS or status >= 500


def _read_elevation(response: httpx2.Response, lat: float, lon: float) -> float:
    """The elevation in a successful EPQS response.

    EPQS answers a location it has no data for with a 200 carrying a plain-text
    message, still labelled ``application/json``, and does not always send the
    same message for the same place. So any body that is not JSON counts as no
    data, whatever it says.
    """
    try:
        body = response.json()
    except ValueError:
        raise NoElevationDataError(lat, lon, response.text.strip()) from None

    try:
        # A string in metres, although a number when asked for feet.
        elevation = float(body["value"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ElevationServiceError(
            f"EPQS sent no readable elevation for {lat},{lon}: {response.text[:200]}"
        ) from exc

    # Written so NaN, which fails every comparison, is rejected too.
    if not MIN_PLAUSIBLE_M <= elevation <= MAX_PLAUSIBLE_M:
        raise ElevationServiceError(
            f"EPQS sent an implausible elevation for {lat},{lon}: {elevation} m"
        )
    return elevation
