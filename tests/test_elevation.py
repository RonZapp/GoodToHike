from collections.abc import Sequence

import pytest

from goodtohike.elevation import (
    DEFAULT_MAX_SAMPLES,
    HybridFill,
    InterpolateOnly,
    LookUpEveryPoint,
    LookUpGaps,
    NoElevationError,
)
from goodtohike.geometry import get_cumulative_m
from goodtohike.route import RawPoint

# One degree of arc on gpxpy's sphere, radius 6,378,137 m. Copied from
# test_gaps.py; move both into a shared helper once a third file needs it.
ONE_DEGREE_M = 111_319.49

# Nothing real is this high, so an elevation carrying it came from a lookup.
LOOKED_UP_M = 7_777.0


def north(metres: float, elevation: float | None = None) -> RawPoint:
    """A point ``metres`` due north of a fixed origin."""
    return (47.0 + metres / ONE_DEGREE_M, -123.0, elevation)


def elevations(points) -> list[float]:
    return [elevation for _, _, elevation in points]


def coordinates(*points: RawPoint) -> list[tuple[float, float]]:
    return [(lat, lon) for lat, lon, _ in points]


class RecordingFetcher:
    """Answers every lookup with LOOKED_UP_M and records what it was asked."""

    def __init__(self) -> None:
        self.calls: list[list[tuple[float, float]]] = []

    def __call__(self, coords: Sequence[tuple[float, float]]) -> list[float]:
        self.calls.append(list(coords))
        return [LOOKED_UP_M] * len(coords)

    @property
    def requested(self) -> list[tuple[float, float]]:
        return [coord for call in self.calls for coord in call]


def numbered(coords: Sequence[tuple[float, float]]) -> list[float]:
    """A fetcher answering 0.0, 1.0, 2.0... so each answer shows where it went."""
    return [float(i) for i in range(len(coords))]


# InterpolateOnly


def test_interpolate_only_leaves_a_complete_track_unchanged():
    # Strategies decide what to do with complete tracks. This one keeps them.
    points = [north(0, 100.0), north(80, 142.5), north(160, 97.0)]

    assert InterpolateOnly().fill(points) == points


def test_interpolate_only_fills_by_distance_between_known_elevations():
    points = [
        north(0, 100.0),
        north(100, None),
        north(300, None),
        north(400, 500.0),
    ]

    filled = InterpolateOnly().fill(points)

    assert [elevation for _, _, elevation in filled] == [
        100.0,
        pytest.approx(200.0, abs=0.01),
        pytest.approx(400.0, abs=0.01),
        500.0,
    ]


def test_interpolate_only_keeps_every_coordinate_in_order():
    points = [north(0, 100.0), north(100, None), north(200, 300.0)]

    filled = InterpolateOnly().fill(points)

    assert [(lat, lon) for lat, lon, _ in filled] == [
        (lat, lon) for lat, lon, _ in points
    ]


def test_interpolate_only_holds_gaps_at_either_end_flat():
    points = [north(0, None), north(100, 250.0), north(200, None)]

    filled = InterpolateOnly().fill(points)

    assert [elevation for _, _, elevation in filled] == [250.0, 250.0, 250.0]


def test_interpolate_only_rejects_a_track_with_no_elevation():
    points = [north(0, None), north(100, None)]

    with pytest.raises(NoElevationError, match="no elevation"):
        InterpolateOnly().fill(points)


def test_interpolate_only_of_an_empty_track_is_empty():
    assert InterpolateOnly().fill([]) == []


def test_interpolate_only_weights_by_distance_not_by_point_count():
    # Four points bunched in the first 30 m, then one at 400 m. Counting points
    # would put index 3 three-quarters of the way up; it is 30 m of 400.
    points = [north(0, 100.0), north(10), north(20), north(30), north(400, 500.0)]

    filled = InterpolateOnly().fill(points)

    assert elevations(filled)[3] == pytest.approx(130.0, abs=0.01)


def test_interpolate_only_holds_the_lower_elevation_across_a_stationary_stretch():
    # A stationary recording puts several points on one spot. Zero distance
    # between known elevations must not divide by zero.
    points = [north(0, 100.0), north(0), north(0, 200.0)]

    filled = InterpolateOnly().fill(points)

    assert elevations(filled) == [100.0, 100.0, 200.0]


def test_interpolate_only_treats_zero_as_a_real_elevation():
    # Placeholder zeros are blanked by the GPX parser. A zero that reaches
    # here is data, and must not be mistaken for a missing value.
    points = [north(0, 0.0), north(100, None), north(200, 200.0)]

    filled = InterpolateOnly().fill(points)

    assert elevations(filled) == [0.0, pytest.approx(100.0, abs=0.01), 200.0]


def test_interpolate_only_fills_several_gaps_between_several_known_elevations():
    points = [
        north(0, 100.0),
        north(50),
        north(100, 200.0),
        north(200),
        north(300),
        north(400, 500.0),
    ]

    filled = InterpolateOnly().fill(points)

    assert elevations(filled) == [
        100.0,
        pytest.approx(150.0, abs=0.01),
        200.0,
        pytest.approx(300.0, abs=0.01),
        pytest.approx(400.0, abs=0.01),
        500.0,
    ]


# HybridFill


def test_hybrid_fill_leaves_a_complete_track_unchanged_without_lookups():
    fetch = RecordingFetcher()
    points = [north(0, 100.0), north(80, 142.5), north(160, 97.0)]

    assert HybridFill(fetch=fetch).fill(points) == points
    assert fetch.calls == []


def test_hybrid_fill_interpolates_a_short_gap_without_lookups():
    fetch = RecordingFetcher()
    points = [north(0, 100.0), north(100, None), north(200, 300.0)]

    filled = HybridFill(fetch=fetch).fill(points)

    assert fetch.calls == []
    assert elevations(filled) == [100.0, pytest.approx(200.0, abs=0.01), 300.0]


def test_hybrid_fill_looks_up_inside_a_long_gap_at_its_spacing():
    # A 600 m bridge. The missing run spans 400 m, so 200 m spacing samples
    # its first, middle and last points.
    fetch = RecordingFetcher()
    missing = [north(m) for m in (100, 200, 300, 400, 500)]
    points = [north(0, 100.0), *missing, north(600, 700.0)]

    filled = HybridFill(fetch=fetch, spacing_m=200.0).fill(points)

    assert fetch.requested == coordinates(missing[0], missing[2], missing[4])
    assert [elevations(filled)[i] for i in (1, 3, 5)] == [LOOKED_UP_M] * 3
    assert elevations(filled)[0] == 100.0
    assert elevations(filled)[-1] == 700.0


def test_hybrid_fill_uses_its_spacing_setting():
    fetch = RecordingFetcher()
    missing = [north(m) for m in (100, 200, 300, 400, 500)]
    points = [north(0, 100.0), *missing, north(600, 700.0)]

    HybridFill(fetch=fetch, spacing_m=100.0).fill(points)

    assert fetch.requested == coordinates(*missing)


def test_hybrid_fill_decides_each_gap_separately():
    fetch = RecordingFetcher()
    points = [
        north(0, 100.0),
        north(100, None),  # 200 m bridge: interpolated
        north(200, 100.0),
        north(300, None),  # 600 m bridge: looked up
        north(500, None),
        north(700, None),
        north(800, 100.0),
    ]

    filled = HybridFill(fetch=fetch).fill(points)

    assert coordinates(points[1])[0] not in fetch.requested
    assert elevations(filled)[1] == pytest.approx(100.0, abs=0.01)
    assert set(fetch.requested) <= set(coordinates(*points[3:6]))
    assert fetch.requested


# Each track has one gap whose bridge runs the whole track: known elevation to
# known elevation, track start to known elevation, and known elevation to
# track end.
ONE_GAP_TRACKS = [
    pytest.param([north(0, 100.0), north(100), north(300, 300.0)], id="middle"),
    pytest.param([north(0), north(100), north(250, 10.0)], id="leading"),
    pytest.param([north(0, 10.0), north(100), north(250)], id="trailing"),
]


@pytest.mark.parametrize("points", ONE_GAP_TRACKS)
def test_hybrid_fill_interpolates_a_gap_exactly_at_max_gap_m(points):
    fetch = RecordingFetcher()
    bridge_m = get_cumulative_m(points)[-1]

    HybridFill(fetch=fetch, max_gap_m=bridge_m).fill(points)

    assert fetch.calls == []


@pytest.mark.parametrize("points", ONE_GAP_TRACKS)
def test_hybrid_fill_looks_up_a_gap_just_over_max_gap_m(points):
    fetch = RecordingFetcher()
    bridge_m = get_cumulative_m(points)[-1]

    HybridFill(fetch=fetch, max_gap_m=bridge_m - 0.01).fill(points)

    missing = [point for point in points if point[2] is None]
    assert fetch.requested == coordinates(*missing)


def test_hybrid_fill_interpolates_between_its_lookups_by_distance():
    # Lookups land on indices 1, 3 and 5 and answer 0.0, 1.0 and 2.0. The
    # points between are halfway along the ground between two of them.
    missing = [north(m) for m in (100, 200, 300, 400, 500)]
    points = [north(0, 100.0), *missing, north(600, 700.0)]

    filled = HybridFill(fetch=numbered, spacing_m=200.0).fill(points)

    assert elevations(filled)[1:6] == [
        0.0,
        pytest.approx(0.5, abs=0.01),
        1.0,
        pytest.approx(1.5, abs=0.01),
        2.0,
    ]


def test_hybrid_fill_holds_a_short_leading_gap_flat_without_lookups():
    fetch = RecordingFetcher()
    points = [north(0, None), north(100, 250.0), north(200, 260.0)]

    filled = HybridFill(fetch=fetch).fill(points)

    assert fetch.calls == []
    assert elevations(filled)[0] == 250.0


def test_hybrid_fill_looks_up_a_long_leading_gap_from_the_first_point():
    fetch = RecordingFetcher()
    points = [north(0), north(200), north(400), north(500, 300.0)]

    filled = HybridFill(fetch=fetch).fill(points)

    assert coordinates(points[0])[0] in fetch.requested
    assert elevations(filled)[0] == LOOKED_UP_M


def test_hybrid_fill_looks_up_a_short_track_with_no_elevation():
    # 100 m is well under max_gap_m, but there is nothing to interpolate from.
    fetch = RecordingFetcher()

    filled = HybridFill(fetch=fetch).fill([north(0), north(100)])

    assert fetch.requested
    assert elevations(filled) == [LOOKED_UP_M, LOOKED_UP_M]


def test_hybrid_fill_asks_for_every_long_gap_in_one_call():
    fetch = RecordingFetcher()
    points = [
        north(0, 100.0),
        north(300, None),
        north(600, 100.0),
        north(900, None),
        north(1200, 100.0),
    ]

    HybridFill(fetch=fetch).fill(points)

    assert len(fetch.calls) == 1
    assert fetch.requested == coordinates(points[1], points[3])


def test_hybrid_fill_rejects_a_fetcher_that_answers_the_wrong_count():
    points = [north(0, 100.0), north(300, None), north(600, 100.0)]

    with pytest.raises(ValueError, match="asked for 1 elevations, fetcher returned 0"):
        HybridFill(fetch=lambda coords: []).fill(points)


def test_hybrid_fill_of_an_empty_track_is_empty():
    fetch = RecordingFetcher()

    assert HybridFill(fetch=fetch).fill([]) == []
    assert fetch.calls == []


# LookUpGaps


def test_look_up_gaps_leaves_a_complete_track_unchanged_without_lookups():
    fetch = RecordingFetcher()
    points = [north(0, 100.0), north(80, 142.5), north(160, 97.0)]

    assert LookUpGaps(fetch=fetch).fill(points) == points
    assert fetch.calls == []


def test_look_up_gaps_looks_up_a_short_gap_that_hybrid_fill_would_interpolate():
    fetch = RecordingFetcher()
    points = [north(0, 100.0), north(100), north(200, 300.0)]

    filled = LookUpGaps(fetch=fetch).fill(points)

    assert fetch.requested == coordinates(points[1])
    assert elevations(filled) == [100.0, LOOKED_UP_M, 300.0]


def test_look_up_gaps_looks_up_a_short_gap_at_the_track_start():
    fetch = RecordingFetcher()
    points = [north(0), north(100, 250.0), north(200, 260.0)]

    filled = LookUpGaps(fetch=fetch).fill(points)

    assert fetch.requested == coordinates(points[0])
    assert elevations(filled) == [LOOKED_UP_M, 250.0, 260.0]


@pytest.mark.parametrize(
    "points",
    [
        pytest.param([north(0, 1.0), north(100, 1.0), north(200)], id="short-trailing"),
        pytest.param(
            [north(m) for m in range(0, 2000, 50)] + [north(2000, 1.0)],
            id="long-leading",
        ),
        pytest.param(
            [north(0, 1.0)] + [north(m) for m in range(50, 2050, 50)],
            id="long-trailing",
        ),
        pytest.param(
            [north(0), north(10), north(100, 1.0), north(190), north(200)],
            id="both-ends",
        ),
        pytest.param(
            [north(0, 1.0), north(100)] + [north(100)] * 5,
            id="stationary-trailing",
        ),
        pytest.param(
            [north(0, 1.0)] + [north(m) for m in range(1, 100_001)],
            id="trailing-gap-at-sample-ceiling",
        ),
        pytest.param([north(m) for m in range(0, 1000, 10)], id="no-elevation"),
    ],
)
def test_look_up_gaps_looks_up_the_track_ends_when_they_are_missing(points):
    fetch = RecordingFetcher()

    filled = LookUpGaps(fetch=fetch).fill(points)

    for end in (0, -1):
        if points[end][2] is None:
            assert coordinates(points[end])[0] in fetch.requested
            assert elevations(filled)[end] == LOOKED_UP_M


def test_look_up_gaps_does_not_look_up_recorded_track_ends():
    fetch = RecordingFetcher()
    points = [north(0, 100.0), north(100), north(200, 300.0)]

    LookUpGaps(fetch=fetch).fill(points)

    assert coordinates(points[0])[0] not in fetch.requested
    assert coordinates(points[-1])[0] not in fetch.requested


def test_look_up_gaps_samples_a_long_gap_at_its_spacing():
    fetch = RecordingFetcher()
    missing = [north(m) for m in (100, 200, 300, 400, 500)]
    points = [north(0, 100.0), *missing, north(600, 700.0)]

    filled = LookUpGaps(fetch=fetch, spacing_m=200.0).fill(points)

    assert fetch.requested == coordinates(missing[0], missing[2], missing[4])
    assert elevations(filled)[0] == 100.0
    assert elevations(filled)[-1] == 700.0


def test_look_up_gaps_uses_its_spacing_setting():
    fetch = RecordingFetcher()
    missing = [north(m) for m in (100, 200, 300, 400, 500)]
    points = [north(0, 100.0), *missing, north(600, 700.0)]

    LookUpGaps(fetch=fetch, spacing_m=100.0).fill(points)

    assert fetch.requested == coordinates(*missing)


def test_look_up_gaps_spaces_lookups_at_least_spacing_m_apart():
    # The missing run spans 399 m, which fits only one 200 m interval, so only
    # its two ends are looked up.
    missing = [north(m) for m in range(1, 401)]
    fetch = RecordingFetcher()

    LookUpGaps(fetch=fetch, spacing_m=200.0).fill([north(0, 1.0), *missing])

    assert fetch.requested == coordinates(missing[0], missing[-1])


@pytest.mark.parametrize("spacing_m", [0.0, -200.0], ids=["zero", "negative"])
def test_look_up_gaps_looks_up_only_a_gaps_ends_without_a_positive_spacing(
    spacing_m,
):
    # With no spacing to step by, a gap's ends are its only lookups, however
    # long it is.
    fetch = RecordingFetcher()
    missing = [north(m) for m in (100, 200, 300, 400, 500)]
    points = [north(0, 100.0), *missing, north(600, 700.0)]

    LookUpGaps(fetch=fetch, spacing_m=spacing_m).fill(points)

    assert fetch.requested == coordinates(missing[0], missing[-1])


def test_look_up_gaps_asks_once_for_a_point_several_targets_land_on():
    # Two points 1 km apart: six 200 m targets, but only two points to take.
    fetch = RecordingFetcher()
    points = [north(0), north(1000)]

    LookUpGaps(fetch=fetch, spacing_m=200.0).fill(points)

    assert fetch.requested == coordinates(*points)


def test_look_up_gaps_never_exceeds_the_sample_ceiling_for_one_gap():
    # 1 m spacing over a 999 m run wants 1,000 lookups. The run finishes
    # standing still, so four points share its final distance, and only the
    # last of them counts as its end.
    missing = [north(m) for m in range(1000)] + [north(999)] * 3
    fetch = RecordingFetcher()

    LookUpGaps(fetch=fetch, spacing_m=1.0).fill([*missing, north(1500, 1.0)])

    assert len(fetch.requested) == DEFAULT_MAX_SAMPLES
    assert fetch.calls[0][-1] == coordinates(missing[-1])[0]


def test_look_up_gaps_looks_up_a_gap_that_bridges_no_distance():
    # A missing point between two recorded ones, all on one spot.
    fetch = RecordingFetcher()
    points = [north(0, 100.0), north(0), north(0, 300.0)]

    filled = LookUpGaps(fetch=fetch).fill(points)

    assert fetch.requested == coordinates(points[1])
    assert elevations(filled) == [100.0, LOOKED_UP_M, 300.0]


def test_look_up_gaps_asks_for_every_gap_in_one_call():
    fetch = RecordingFetcher()
    points = [north(0, 1.0), north(50), north(100, 1.0), north(150), north(200, 1.0)]

    LookUpGaps(fetch=fetch).fill(points)

    assert fetch.calls == [coordinates(points[1], points[3])]


def test_look_up_gaps_looks_up_a_track_with_no_elevation():
    fetch = RecordingFetcher()

    filled = LookUpGaps(fetch=fetch).fill([north(0), north(100)])

    assert elevations(filled) == [LOOKED_UP_M, LOOKED_UP_M]


def test_look_up_gaps_of_an_empty_track_is_empty():
    fetch = RecordingFetcher()

    assert LookUpGaps(fetch=fetch).fill([]) == []
    assert fetch.calls == []


# LookUpEveryPoint


def test_look_up_every_point_asks_for_every_coordinate_in_order_in_one_call():
    fetch = RecordingFetcher()
    points = [north(0, 100.0), north(100), north(200, 300.0)]

    LookUpEveryPoint(fetch=fetch).fill(points)

    assert fetch.calls == [coordinates(*points)]


def test_look_up_every_point_uses_each_lookup_without_interpolating():
    points = [north(0), north(100), north(200), north(300)]

    filled = LookUpEveryPoint(fetch=numbered).fill(points)

    assert elevations(filled) == [0.0, 1.0, 2.0, 3.0]


def test_look_up_every_point_replaces_recorded_elevations():
    points = [north(0, 100.0), north(80, 142.5), north(160, 97.0)]

    filled = LookUpEveryPoint(fetch=numbered).fill(points)

    assert elevations(filled) == [0.0, 1.0, 2.0]
    assert coordinates(*filled) == coordinates(*points)


def test_look_up_every_point_rejects_a_fetcher_that_answers_the_wrong_count():
    points = [north(0), north(100)]

    with pytest.raises(ValueError, match="asked for 2 elevations, fetcher returned 1"):
        LookUpEveryPoint(fetch=lambda coords: [1.0]).fill(points)


def test_look_up_every_point_of_an_empty_track_is_empty():
    fetch = RecordingFetcher()

    assert LookUpEveryPoint(fetch=fetch).fill([]) == []
    assert fetch.calls == []
