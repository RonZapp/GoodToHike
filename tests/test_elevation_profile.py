import pytest

from goodtohike.elevation_profile import (
    CLIMB_THRESHOLD_M,
    build_profile,
    get_elevation_change,
)
from goodtohike.route import Point

# A hundred-thousandth of a degree of latitude on gpxpy's sphere.
STEP_DEGREES = 0.0001
STEP_M = 11.131949


def due_north(elevations: list[float]) -> list[Point]:
    """A track heading due north, one point every STEP_M, at these elevations."""
    return [
        (47.0 + i * STEP_DEGREES, -123.0, elevation)
        for i, elevation in enumerate(elevations)
    ]


# get_elevation_change


def test_change_of_no_elevations_is_zero():
    assert get_elevation_change([]) == (0.0, 0.0)


def test_change_of_one_elevation_is_zero():
    assert get_elevation_change([1_200.0]) == (0.0, 0.0)


def test_change_of_flat_track_is_zero():
    assert get_elevation_change([500.0] * 10) == (0.0, 0.0)


def test_steady_climb_counts_in_full():
    elevations = [100.0 + i * 20 for i in range(11)]

    assert get_elevation_change(elevations) == (200.0, 0.0)


def test_small_steps_add_up_once_past_the_threshold():
    # Each step is under the threshold, but the climb is not.
    elevations = [100.0 + i * 2 for i in range(51)]

    gain_m, loss_m = get_elevation_change(elevations)

    assert gain_m == pytest.approx(100.0, abs=CLIMB_THRESHOLD_M)
    assert loss_m == 0.0


def test_jitter_under_the_threshold_is_ignored():
    elevations = [500.0, 504.0, 497.0, 503.0, 498.0, 506.0, 495.0] * 50

    assert get_elevation_change(elevations) == (0.0, 0.0)


def test_climb_then_descent_counts_both():
    elevations = [100.0, 200.0, 300.0, 200.0, 150.0]

    assert get_elevation_change(elevations) == (200.0, 150.0)


def test_change_exactly_at_the_threshold_counts():
    assert get_elevation_change([0.0, 10.0], threshold_m=10.0) == (10.0, 0.0)


def test_change_just_under_the_threshold_does_not_count():
    assert get_elevation_change([0.0, 9.9], threshold_m=10.0) == (0.0, 0.0)


def test_zero_threshold_sums_every_change():
    elevations = [0.0, 3.0, 1.0, 4.0]

    assert get_elevation_change(elevations, threshold_m=0.0) == (6.0, 2.0)


# build_profile


def test_profile_of_single_point():
    profile = build_profile(due_north([800.0]))

    assert profile.length_m == 0.0
    assert profile.gain_m == 0.0
    assert [(p.distance_m, p.elevation_m, p.grade_percent) for p in profile.points] == [
        (0.0, 800.0, None)
    ]


def test_profile_includes_first_and_last_points():
    points = due_north([100.0 + i for i in range(200)])

    profile = build_profile(points)

    assert profile.points[0].distance_m == 0.0
    assert profile.points[0].elevation_m == 100.0
    assert profile.points[-1].distance_m == pytest.approx(profile.length_m)
    assert profile.points[-1].elevation_m == 299.0


def test_profile_points_are_spread_along_the_ground():
    # 199 hops of about 11.13 m is 2.2 km, so about 45 points at 50 m.
    points = due_north([100.0] * 200)

    profile = build_profile(points, spacing_m=50.0)

    gaps = [
        b.distance_m - a.distance_m for a, b in zip(profile.points, profile.points[1:])
    ]
    assert 40 <= len(profile.points) <= 46
    assert all(40.0 <= gap <= 70.0 for gap in gaps)


def test_profile_reports_its_spacing():
    profile = build_profile(due_north([100.0] * 200), spacing_m=50.0)

    assert profile.spacing_m == 50.0


def test_long_route_widens_spacing_to_fit_the_ceiling():
    points = due_north([100.0] * 1_000)

    profile = build_profile(points, spacing_m=50.0, max_points=20)

    assert len(profile.points) <= 20
    assert profile.spacing_m == pytest.approx(profile.length_m / 19)


def test_first_point_has_no_grade():
    profile = build_profile(due_north([100.0, 110.0, 120.0]), spacing_m=1.0)

    assert profile.points[0].grade_percent is None


def test_grade_is_climb_over_distance_since_the_previous_point():
    # 10 m up per STEP_M along, every point kept.
    points = due_north([100.0 + i * 10 for i in range(5)])

    profile = build_profile(points, spacing_m=1.0)

    expected = 10.0 / STEP_M * 100
    assert [p.grade_percent for p in profile.points[1:]] == pytest.approx(
        [expected] * 4, rel=1e-4
    )


def test_downhill_grade_is_negative():
    points = due_north([500.0, 490.0])

    profile = build_profile(points, spacing_m=1.0)

    assert profile.points[1].grade_percent is not None
    assert profile.points[1].grade_percent < 0


def test_grade_between_stationary_points_is_none():
    points: list[Point] = [(47.0, -123.0, 100.0), (47.0, -123.0, 110.0)]

    profile = build_profile(points, spacing_m=1.0)

    assert profile.points[1].grade_percent is None


def test_gain_counts_every_point_not_only_profile_points():
    # A 40 m bump between the 50 m profile points, which the profile skips.
    elevations = [100.0] * 60
    elevations[7] = 140.0
    points = due_north(elevations)

    profile = build_profile(points, spacing_m=50.0)

    assert 140.0 not in [p.elevation_m for p in profile.points]
    assert profile.gain_m == 40.0
    assert profile.loss_m == 40.0


def test_gain_does_not_depend_on_spacing():
    points = due_north([100.0 + (i % 20) * 3 for i in range(400)])

    fine = build_profile(points, spacing_m=20.0)
    coarse = build_profile(points, spacing_m=500.0)

    assert (fine.gain_m, fine.loss_m) == (coarse.gain_m, coarse.loss_m)
