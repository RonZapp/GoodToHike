"""EPQS itself, over the network. Run with ``uv run pytest -m network``.

The mocked tests in test_epqs.py assert what EPQS was seen doing; these check
it still does.

No sample's recorded elevation is used as a reference. The hikingguy files that
carry elevation had it generated, from 3DEP itself in at least one case, so
agreeing with them proves nothing. Filled elevation is checked against EPQS
asked directly instead.
"""

import statistics
from collections.abc import Iterator, Sequence
from itertools import pairwise
from pathlib import Path

import pytest

from goodtohike.clients.epqs import EpqsClient, NoElevationDataError
from goodtohike.elevation import HybridFill
from goodtohike.gpx import parse_gpx
from goodtohike.http import make_http_client
from goodtohike.ingest import build_route
from goodtohike.route import ParsedTrack

pytestmark = pytest.mark.network

SAMPLES = Path(__file__).parents[2] / "samples"

# The one real hikingguy export with no elevation at all. It holds the trail
# plus four short feature tracks, so the upload endpoint rejects it whole.
LOST_COAST = (
    SAMPLES / "hikingguy" / "no_elevation" / "how-to-hike-the-lost-coast-trail.gpx"
)

# Interpolated points checked against a direct lookup.
CHECKED_POINTS = 40


@pytest.fixture
def client() -> Iterator[EpqsClient]:
    with make_http_client() as http:
        yield EpqsClient(http)


def test_a_known_point_has_its_elevation(client):
    # Near the summit of Mount Rainier, 4,392 m. EPQS answered 4,387.06 m.
    elevation = client.get_elevation(46.8523, -121.7603)

    assert elevation == pytest.approx(4_392, abs=30)


def test_open_ocean_has_no_elevation_data(client):
    with pytest.raises(NoElevationDataError):
        client.get_elevation(40.0, -130.0)


def test_a_batch_answers_each_point_in_order(client):
    # Sea level on the coast, then Mount Rainier, then back down to Seattle.
    coast, summit, city = client.get_elevations(
        [(46.0, -124.9), (46.8523, -121.7603), (47.6, -122.4)]
    )

    assert coast == pytest.approx(0, abs=5)
    assert summit > 4_000
    assert city == pytest.approx(0, abs=5)


def longest_track(track: ParsedTrack) -> ParsedTrack:
    """The track's longest source track on its own, by point count."""
    bounds = [0, *track.track_seams, len(track.points)]
    start, stop = max(pairwise(bounds), key=lambda run: run[1] - run[0])
    return ParsedTrack(
        points=track.points[start:stop], source=track.source, name=track.name
    )


def test_a_real_track_without_elevation_is_filled_close_to_epqs_itself(client):
    # Measured 2026-09-14 on 40 interpolated points: median 0.34 m, 95th
    # percentile 5.3 m, max 6.25 m, identical across three runs. 205 lookups
    # took under 10 s with EPQS quiet and up to 129 s under load.
    trail = longest_track(parse_gpx(LOST_COAST.read_bytes()))
    assert all(elevation is None for _, _, elevation in trail.points)

    asked: set[tuple[float, float]] = set()

    def fetch(coordinates: Sequence[tuple[float, float]]) -> list[float]:
        asked.update(coordinates)
        return client.get_elevations(coordinates)

    route = build_route(trail, HybridFill(fetch=fetch))

    # Only points the filler interpolated, since a looked-up point matches a
    # direct lookup by definition.
    interpolated = [point for point in route.points if point[:2] not in asked]
    checked = interpolated[:: len(interpolated) // CHECKED_POINTS][:CHECKED_POINTS]
    direct = client.get_elevations([point[:2] for point in checked])

    differences = [
        abs(point[2] - asked_directly)
        for point, asked_directly in zip(checked, direct, strict=True)
    ]
    assert asked
    assert statistics.median(differences) < 2
    assert max(differences) < 20
