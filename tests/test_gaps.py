from pathlib import Path

import pytest

from goodtohike.gaps import (
    MAX_HOP_M,
    MAX_INSERTED_PER_GAP,
    MAX_TRACK_JOIN_M,
    NORMAL_HOP_M,
    TrackGapError,
    check_continuity,
    check_track_joins,
    fill_gaps,
    find_hops_over,
)
from goodtohike.geometry import get_hops_m
from goodtohike.gpx import parse_gpx
from goodtohike.route import RawPoint

SYNTHETIC = Path(__file__).parents[1] / "samples" / "synthetic"

# One degree of arc on gpxpy's sphere, radius 6,378,137 m. Written out rather
# than computed, so a change to the underlying formula shows up here.
ONE_DEGREE_M = 111_319.49


def north(metres: float, elevation: float | None = None) -> RawPoint:
    """A point ``metres`` due north of a fixed origin.

    Along a meridian, distance is proportional to the change in latitude, so
    points built this way sit apart by exactly the difference in ``metres``,
    to within the rounding of ONE_DEGREE_M.
    """
    return (47.0 + metres / ONE_DEGREE_M, -123.0, elevation)


def track(*metres: float) -> list[RawPoint]:
    """Points at each distance north of the origin, all carrying elevation."""
    return [north(m, elevation=100.0) for m in metres]


# find_hops_over


def test_find_hops_over_empty_track_is_empty():
    assert find_hops_over([], 100.0) == []


def test_find_hops_over_ignores_short_hops():
    assert find_hops_over(track(0, 50, 100, 150), 60.0) == []


def test_find_hops_over_reports_index_of_hop_start():
    hops = find_hops_over(track(0, 50, 250, 300), 100.0)

    assert len(hops) == 1
    assert hops[0].index == 1
    assert hops[0].distance_m == pytest.approx(200.0, abs=0.01)


def test_find_hops_over_reports_every_long_hop_in_order():
    hops = find_hops_over(track(0, 500, 550, 1550), 100.0)

    assert [hop.index for hop in hops] == [0, 2]
    assert [hop.distance_m for hop in hops] == [
        pytest.approx(500.0, abs=0.01),
        pytest.approx(1000.0, abs=0.01),
    ]


def test_find_hops_over_excludes_hop_equal_to_threshold():
    points = track(0, 100)
    exact = get_hops_m(points)[0]

    assert find_hops_over(points, exact) == []


# check_continuity


def test_track_gap_error_is_a_value_error():
    # Lets the HTTP layer treat every bad-upload error alike, as GpxError is too.
    assert issubclass(TrackGapError, ValueError)


@pytest.mark.parametrize("points", [[], track(0)], ids=["empty", "single point"])
def test_continuity_accepts_tracks_with_no_hops(points):
    check_continuity(points)


def test_continuity_accepts_hops_under_limit():
    check_continuity(track(0, 1000, 4000, 8000))


def test_continuity_accepts_hop_exactly_at_limit():
    points = track(0, 2000)
    exact = get_hops_m(points)[0]

    check_continuity(points, max_hop_m=exact)


def test_continuity_rejects_hop_over_limit():
    with pytest.raises(TrackGapError):
        check_continuity(track(0, 2000), max_hop_m=1000.0)


def test_continuity_defaults_to_max_hop_m():
    check_continuity(track(0, MAX_HOP_M - 100))

    with pytest.raises(TrackGapError):
        check_continuity(track(0, MAX_HOP_M + 100))


def test_continuity_message_names_worst_jump_and_count():
    # Two jumps over the limit; the 7 km one between points 2 and 3 is worse.
    points = track(0, 6000, 6050, 13050)

    with pytest.raises(TrackGapError) as caught:
        check_continuity(points)

    message = str(caught.value)
    assert "7.0 km between points 2 and 3" in message
    assert "2 such jumps" in message


def test_continuity_message_omits_count_for_a_single_jump():
    with pytest.raises(TrackGapError) as caught:
        check_continuity(track(0, 50, 6050))

    message = str(caught.value)
    assert "6.0 km between points 1 and 2" in message
    assert "such jumps" not in message


# check_track_joins


def test_track_joins_accept_single_track_whatever_its_hops():
    # Long hops inside a track are check_continuity's concern, not this one's.
    check_track_joins(track(0, 50_000), track_starts=[])


def test_track_joins_accept_join_within_drift():
    check_track_joins(track(0, 500, 520, 1000), track_starts=[2])


def test_track_joins_accept_join_exactly_at_limit():
    points = track(0, 500, 580, 1000)
    exact = get_hops_m(points)[1]

    check_track_joins(points, track_starts=[2], max_join_m=exact)


def test_track_joins_reject_join_over_limit():
    with pytest.raises(TrackGapError, match="30.0 km"):
        check_track_joins(track(0, 500, 30_500, 31_000), track_starts=[2])


def test_track_joins_check_every_seam():
    # The first join is drift, the second is not.
    points = track(0, 500, 510, 1000, 9000, 9500)

    with pytest.raises(TrackGapError):
        check_track_joins(points, track_starts=[2, 4])


def test_track_joins_measure_only_across_seams():
    # A 3 km hop inside the second track, but the tracks themselves chain.
    check_track_joins(track(0, 500, 510, 3510), track_starts=[2])


def test_track_joins_default_to_max_track_join_m():
    check_track_joins(track(0, MAX_TRACK_JOIN_M - 20), track_starts=[1])

    with pytest.raises(TrackGapError):
        check_track_joins(track(0, MAX_TRACK_JOIN_M + 20), track_starts=[1])


# fill_gaps


@pytest.mark.parametrize("points", [[], track(0)], ids=["empty", "single point"])
def test_fill_gaps_returns_short_tracks_unchanged(points):
    assert fill_gaps(points) == (points, [])


def test_fill_gaps_leaves_track_without_gaps_unchanged():
    points = track(0, 50, 90, 180)

    assert fill_gaps(points) == (points, [])


def test_fill_gaps_ignores_hop_equal_to_min_gap():
    points = track(0, 100)
    exact = get_hops_m(points)[0]

    assert fill_gaps(points, min_gap_m=exact) == (points, [])


def test_fill_gaps_does_not_modify_its_input():
    points = track(0, 500)
    before = list(points)

    fill_gaps(points)

    assert points == before


def test_fill_gaps_inserts_midpoint_across_short_gap():
    filled, inferred = fill_gaps(track(0, 120))

    assert len(filled) == 3
    assert filled[1][:2] == pytest.approx(north(60)[:2])
    assert inferred == [(1, 1)]


def test_fill_gaps_spaces_inserted_points_evenly():
    filled, _ = fill_gaps(track(0, 500))

    assert get_hops_m(filled) == [pytest.approx(50.0, abs=0.01)] * 10


def test_fill_gaps_inserted_points_have_no_elevation():
    filled, inferred = fill_gaps(track(0, 300))
    (start, end) = inferred[0]

    assert all(point[2] is None for point in filled[start : end + 1])


def test_fill_gaps_keeps_original_points_in_order():
    points = track(0, 300, 350, 650)
    filled, inferred = fill_gaps(points)

    inserted = {i for start, end in inferred for i in range(start, end + 1)}
    kept = [point for i, point in enumerate(filled) if i not in inserted]

    assert kept == points


def test_fill_gaps_ranges_are_inclusive_indices_in_the_new_list():
    # Two 300 m gaps get five points each. The second range starts after the
    # first gap's insertions have shifted every later index along.
    filled, inferred = fill_gaps(track(0, 300, 350, 650))

    assert inferred == [(1, 5), (8, 12)]
    assert len(filled) == 14
    assert [i for i, point in enumerate(filled) if point[2] is None] == [
        *range(1, 6),
        *range(8, 13),
    ]


def test_fill_gaps_leaves_no_gap_behind():
    # Awkward lengths, so a rounding slip in the insertion count would leave a
    # hop over the limit.
    points = track(0, 101, 250, 449, 1449, 4449)

    filled, _ = fill_gaps(points)

    assert all(hop <= NORMAL_HOP_M for hop in get_hops_m(filled))
    assert fill_gaps(filled) == (filled, [])


def test_fill_gaps_caps_points_per_gap():
    filled, inferred = fill_gaps(track(0, 10_000), max_inserted=5)

    assert len(filled) == 7
    assert inferred == [(1, 5)]


def test_fill_gaps_defaults_to_max_inserted_per_gap():
    filled, _ = fill_gaps(track(0, 50_000))

    assert len(filled) == MAX_INSERTED_PER_GAP + 2


def test_fill_gaps_records_no_range_when_nothing_fits():
    # Over min_gap_m, but too short to hold a point at this spacing.
    filled, inferred = fill_gaps(track(0, 60), min_gap_m=10.0, spacing_m=50.0)

    assert len(filled) == 2
    assert inferred == []


# Synthetic fixtures. See samples/synthetic/README.md for what each one isolates.


def parse_fixture(filename: str):
    return parse_gpx((SYNTHETIC / filename).read_bytes())


@pytest.mark.parametrize(
    "filename",
    [
        "one-clean-walk.gpx",
        "paused-recording-two-tracks.gpx",
        "late-restart-50m-gap.gpx",
    ],
)
def test_fixture_accepted_with_nothing_inserted(filename):
    parsed = parse_fixture(filename)

    check_track_joins(parsed.points, parsed.track_seams)
    check_continuity(parsed.points)
    assert fill_gaps(parsed.points) == (parsed.points, [])


@pytest.mark.parametrize(
    "filename", ["drive-mid-track.gpx", "drive-between-segments.gpx"]
)
def test_fixture_rejected_for_a_jump(filename):
    parsed = parse_fixture(filename)

    with pytest.raises(TrackGapError, match="too far to be one continuous walk"):
        check_continuity(parsed.points)


def test_fixture_with_annotation_track_rejected_at_the_join():
    parsed = parse_fixture("walk-with-annotation-track.gpx")

    with pytest.raises(TrackGapError, match="do not join up"):
        check_track_joins(parsed.points, parsed.track_seams)
