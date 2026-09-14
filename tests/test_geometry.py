import pytest

from goodtohike.geometry import (
    get_cumulative_m,
    get_hops_m,
    get_spaced_indices,
    lerp_coordinate,
)

# One degree of arc on gpxpy's sphere, radius 6,378,137 m. Written out rather
# than computed, so a change to the underlying formula shows up here.
ONE_DEGREE_M = 111_319.49


# get_hops_m


def test_hops_of_empty_track_is_empty():
    assert get_hops_m([]) == []


def test_hops_of_single_point_is_empty():
    assert get_hops_m([(47.0, -123.0, 100.0)]) == []


def test_hops_is_one_shorter_than_points():
    points = [(47.0 + i * 0.001, -123.0, None) for i in range(10)]

    assert len(get_hops_m(points)) == 9


def test_hop_between_identical_points_is_zero():
    assert get_hops_m([(47.0, -123.0, 100.0), (47.0, -123.0, 100.0)]) == [0.0]


def test_hop_of_one_degree_latitude():
    hops = get_hops_m([(0.0, 0.0, None), (1.0, 0.0, None)])

    assert hops == [pytest.approx(ONE_DEGREE_M, rel=1e-6)]


def test_hop_of_one_degree_longitude_shrinks_with_latitude():
    # A degree of longitude at 60 degrees north spans half what it does at the
    # equator, since cos(60) is 0.5.
    hops = get_hops_m([(60.0, 0.0, None), (60.0, 1.0, None)])

    assert hops == [pytest.approx(ONE_DEGREE_M / 2, rel=1e-3)]


def test_hops_keep_walked_order():
    points = [(0.0, 0.0, None), (1.0, 0.0, None), (3.0, 0.0, None)]

    hops = get_hops_m(points)

    assert hops == [
        pytest.approx(ONE_DEGREE_M, rel=1e-6),
        pytest.approx(2 * ONE_DEGREE_M, rel=1e-6),
    ]


def test_hops_ignore_elevation():
    # Same position a kilometre apart vertically: a flat-ground distance.
    points = [(47.0, -123.0, 0.0), (47.0, -123.0, 1000.0), (47.0, -123.0, None)]

    assert get_hops_m(points) == [0.0, 0.0]


def test_hops_of_reversed_track_are_reversed():
    points = [(47.0, -123.0, None), (47.01, -123.0, None), (47.01, -122.97, None)]

    forward = get_hops_m(points)
    backward = get_hops_m(list(reversed(points)))

    assert backward == pytest.approx(list(reversed(forward)))


# get_cumulative_m


def test_cumulative_of_zero_points_is_empty_list():
    assert get_cumulative_m([]) == []


def test_cumulative_of_single_point_is_zero():
    assert get_cumulative_m([(47.0, -123.0, 100.0)]) == [0.0]


def test_cumulative_has_one_entry_per_point():
    points = [(47.0 + i * 0.001, -123.0, None) for i in range(10)]

    assert len(get_cumulative_m(points)) == 10


def test_cumulative_starts_at_zero():
    points = [(47.0, -123.0, None), (47.01, -123.0, None)]

    assert get_cumulative_m(points)[0] == 0.0


def test_cumulative_adds_each_hop():
    points = [(0.0, 0.0, None), (1.0, 0.0, None), (3.0, 0.0, None)]

    assert get_cumulative_m(points) == [
        0.0,
        pytest.approx(ONE_DEGREE_M, rel=1e-6),
        pytest.approx(3 * ONE_DEGREE_M, rel=1e-6),
    ]


def test_cumulative_never_decreases():
    # A zigzag, so direction changes cannot subtract distance.
    points = [
        (47.0, -123.0, None),
        (47.01, -123.0, None),
        (47.0, -123.0, None),
        (47.02, -122.99, None),
    ]

    cumulative = get_cumulative_m(points)

    assert all(a <= b for a, b in zip(cumulative, cumulative[1:]))


def test_cumulative_counts_stationary_points_as_zero():
    points = [(47.0, -123.0, None), (47.0, -123.0, None), (47.0, -123.0, None)]

    assert get_cumulative_m(points) == [0.0, 0.0, 0.0]


def test_out_and_back_ends_at_twice_one_way():
    one_way = [(47.0, -123.0, None), (47.01, -123.0, None), (47.02, -123.0, None)]
    out_and_back = one_way + list(reversed(one_way))[1:]

    one_way_m = get_cumulative_m(one_way)[-1]

    assert get_cumulative_m(out_and_back)[-1] == pytest.approx(2 * one_way_m)


# get_spaced_indices


def evenly(count: int, step_m: float) -> list[float]:
    """Distance along a track of ``count`` points ``step_m`` apart."""
    return [i * step_m for i in range(count)]


def test_spaced_indices_of_single_point_is_that_point():
    assert get_spaced_indices(range(1), [0.0], 50.0, max_count=10) == [0]


def test_spaced_indices_always_include_both_ends():
    distance = evenly(101, 10.0)

    indices = get_spaced_indices(range(101), distance, 50.0, max_count=1_000)

    assert indices[0] == 0
    assert indices[-1] == 100


def test_spaced_indices_land_on_the_spacing():
    # 1,000 m at 10 m per point, so every fifth point is 50 m on.
    distance = evenly(101, 10.0)

    indices = get_spaced_indices(range(101), distance, 50.0, max_count=1_000)

    assert indices == list(range(0, 101, 5))


def test_spaced_indices_run_shorter_than_spacing_gives_only_the_ends():
    distance = evenly(5, 10.0)

    assert get_spaced_indices(range(5), distance, 50.0, max_count=1_000) == [0, 4]


def test_spaced_indices_zero_spacing_gives_only_the_ends():
    distance = evenly(5, 10.0)

    assert get_spaced_indices(range(5), distance, 0.0, max_count=1_000) == [0, 4]


def test_spaced_indices_never_exceed_max_count():
    # 10 km wants 201 points at 50 m.
    distance = evenly(1_001, 10.0)

    indices = get_spaced_indices(range(1_001), distance, 50.0, max_count=20)

    assert len(indices) == 20


def test_spaced_indices_widen_spacing_when_capped():
    distance = evenly(1_001, 10.0)

    indices = get_spaced_indices(range(1_001), distance, 50.0, max_count=11)

    # Eleven points over 10 km is one per kilometre.
    assert [distance[i] for i in indices] == evenly(11, 1_000.0)


def test_spaced_indices_stay_inside_the_run():
    distance = evenly(101, 10.0)

    indices = get_spaced_indices(range(20, 41), distance, 50.0, max_count=1_000)

    assert indices == [20, 25, 30, 35, 40]


def test_spaced_indices_take_the_nearest_point_to_each_target():
    # A 60 m target sits between points at 55 m and 70 m, nearer the first.
    distance = [0.0, 55.0, 70.0, 120.0]

    indices = get_spaced_indices(range(4), distance, 60.0, max_count=1_000)

    assert indices == [0, 1, 3]


def test_spaced_indices_skip_repeats_across_a_sparse_stretch():
    # One long hop swallows several targets, which all map to the same point.
    distance = [0.0, 10.0, 500.0, 510.0]

    indices = get_spaced_indices(range(4), distance, 50.0, max_count=1_000)

    assert indices == sorted(set(indices))
    assert indices[0] == 0
    assert indices[-1] == 3


def test_spaced_indices_handle_stationary_points():
    distance = [0.0, 0.0, 0.0, 100.0, 100.0, 200.0]

    indices = get_spaced_indices(range(6), distance, 100.0, max_count=1_000)

    assert indices == sorted(set(indices))
    assert [distance[i] for i in indices] == [0.0, 100.0, 200.0]


# lerp_coordinate


START = (47.0, -123.0, 100.0)
END = (48.0, -121.0, 900.0)


@pytest.mark.parametrize(
    ("fraction", "expected"),
    [
        (0.0, (47.0, -123.0)),
        (0.25, (47.25, -122.5)),
        (0.5, (47.5, -122.0)),
        (1.0, (48.0, -121.0)),
    ],
)
def test_lerp_coordinate_at_fraction(fraction, expected):
    assert lerp_coordinate(START, END, fraction) == pytest.approx(expected)


def test_lerp_coordinate_drops_elevation():
    assert len(lerp_coordinate(START, END, 0.5)) == 2


def test_lerp_coordinate_accepts_missing_elevation():
    start = (47.0, -123.0, None)
    end = (48.0, -121.0, None)

    assert lerp_coordinate(start, end, 0.5) == pytest.approx((47.5, -122.0))


def test_lerp_coordinate_between_identical_points_stays_put():
    assert lerp_coordinate(START, START, 0.7) == pytest.approx((47.0, -123.0))


def test_lerp_coordinate_crosses_the_equator_and_prime_meridian():
    start = (-1.0, -1.0, None)
    end = (1.0, 1.0, None)

    assert lerp_coordinate(start, end, 0.5) == pytest.approx((0.0, 0.0))
