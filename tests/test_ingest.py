from collections.abc import Sequence
from pathlib import Path

import pytest

from goodtohike.elevation import InterpolateOnly
from goodtohike.gaps import TrackGapError
from goodtohike.gpx import parse_gpx
from goodtohike.ingest import UNNAMED, build_route
from goodtohike.route import ParsedTrack, Point, RawPoint

SAMPLES = Path(__file__).parents[1] / "samples"
SYNTHETIC = SAMPLES / "synthetic"

# One degree of arc on gpxpy's sphere, radius 6,378,137 m. Copied from
# test_gaps.py; move both into a shared helper once a third file needs it.
ONE_DEGREE_M = 111_319.49

# Nothing real is this high, so a point carrying it came from the fake.
FAKE_ELEVATION_M = 9_999.0


def north(metres: float, elevation: float | None = None) -> RawPoint:
    """A point ``metres`` due north of a fixed origin."""
    return (47.0 + metres / ONE_DEGREE_M, -123.0, elevation)


def parse_fixture(path: Path) -> ParsedTrack:
    return parse_gpx(path.read_bytes())


class RecordingFiller:
    """Records the points it was given and returns them all at one elevation.

    Written by hand rather than with unittest.mock, because a Mock accepts any
    method name and would hide a typo in the call build_route makes.
    """

    def __init__(self) -> None:
        self.received: list[RawPoint] | None = None

    def fill(self, points: Sequence[RawPoint]) -> list[Point]:
        self.received = list(points)
        return [(lat, lon, FAKE_ELEVATION_M) for lat, lon, _ in points]


# build_route with a fake filler


def test_build_route_gives_filler_the_gap_filled_points():
    # A 260 m hop: fill_gaps inserts int(260 // 50) - 1 = 4 points across it.
    track = ParsedTrack(points=[north(0, 100.0), north(260, 200.0)], source="gpx")
    filler = RecordingFiller()

    build_route(track, filler)

    assert filler.received is not None
    assert len(filler.received) == 6
    assert filler.received[0] == north(0, 100.0)
    assert filler.received[-1] == north(260, 200.0)
    assert [elevation for _, _, elevation in filler.received[1:-1]] == [None] * 4


def test_build_route_uses_the_points_the_filler_returns():
    track = ParsedTrack(points=[north(0, 100.0), north(50, 110.0)], source="gpx")
    filler = RecordingFiller()

    route = build_route(track, filler)

    assert route.points == [north(0, FAKE_ELEVATION_M), north(50, FAKE_ELEVATION_M)]


@pytest.mark.parametrize(
    "filename",
    [
        "drive-mid-track.gpx",
        "drive-between-segments.gpx",
        "walk-with-annotation-track.gpx",
    ],
)
def test_build_route_rejects_geometry_before_filling(filename):
    track = parse_fixture(SYNTHETIC / filename)
    filler = RecordingFiller()

    with pytest.raises(TrackGapError):
        build_route(track, filler)

    assert filler.received is None


def test_build_route_rejects_tracks_that_do_not_join():
    # 250 m at the seam: far inside MAX_HOP_M, so only the join check objects.
    track = ParsedTrack(
        points=[north(0, 100.0), north(50, 110.0), north(300, 120.0)],
        source="gpx",
        track_seams=[2],
    )
    filler = RecordingFiller()

    with pytest.raises(TrackGapError, match="do not join up"):
        build_route(track, filler)

    assert filler.received is None


def test_build_route_records_where_it_filled_gaps():
    # Same 260 m hop: the 4 inserted points sit at indices 1 to 4.
    track = ParsedTrack(points=[north(0, 100.0), north(260, 200.0)], source="gpx")

    route = build_route(track, RecordingFiller())

    assert route.inferred_ranges == [(1, 4)]


def test_build_route_records_no_ranges_when_nothing_was_filled():
    track = ParsedTrack(points=[north(0, 100.0), north(50, 110.0)], source="gpx")

    route = build_route(track, RecordingFiller())

    assert route.inferred_ranges == []


def test_build_route_keeps_name_and_source():
    track = ParsedTrack(
        points=[north(0, 100.0), north(50, 110.0)], source="fixture", name="Hoh River"
    )

    route = build_route(track, RecordingFiller())

    assert route.name == "Hoh River"
    assert route.source == "fixture"


def test_build_route_names_an_unnamed_track():
    track = ParsedTrack(points=[north(0, 100.0), north(50, 110.0)], source="gpx")

    route = build_route(track, RecordingFiller())

    assert route.name == UNNAMED


# build_route with InterpolateOnly, on real files


def test_clean_fixture_keeps_every_recorded_elevation():
    track = parse_fixture(SYNTHETIC / "one-clean-walk.gpx")

    route = build_route(track, InterpolateOnly())

    assert route.points == track.points


def test_real_track_with_inserted_points_gets_elevation_everywhere():
    # fill_gaps inserts 4 points into this file, none of them with elevation.
    track = parse_fixture(
        SAMPLES / "hikingguy" / "elevation_added" / "hoh-river-trail.gpx"
    )

    route = build_route(track, InterpolateOnly())

    assert len(route.points) == len(track.points) + 4
    assert all(elevation is not None for _, _, elevation in route.points)
