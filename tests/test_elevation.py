import pytest

from goodtohike.elevation import (
    InterpolateOnly,
)
from goodtohike.route import RawPoint

# One degree of arc on gpxpy's sphere, radius 6,378,137 m. Copied from
# test_gaps.py; move both into a shared helper once a third file needs it.
ONE_DEGREE_M = 111_319.49


def north(metres: float, elevation: float | None = None) -> RawPoint:
    """A point ``metres`` due north of a fixed origin."""
    return (47.0 + metres / ONE_DEGREE_M, -123.0, elevation)


def elevations(points) -> list[float]:
    return [elevation for _, _, elevation in points]


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

    with pytest.raises(ValueError, match="no elevation"):
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
