import pytest

from goodtohike.geometry import get_cumulative_m, get_hops_m, lerp_coordinate

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
