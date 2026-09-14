"""The elevation profile of a route: distance, elevation and grade along it.

Filling in missing elevation is :mod:`goodtohike.elevation`'s job. This module
starts from a route that already has an elevation at every point, and nothing
here performs I/O.

Two different resolutions are used on purpose. The points in a profile are
spread out along the ground, because a chart cannot show tens of thousands of
them and grade between points a metre apart is mostly GPS noise. Total climb
is counted over every point instead, so it does not change with the spacing a
profile happens to be drawn at.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from goodtohike.geometry import get_cumulative_m, get_spaced_indices
from goodtohike.route import Point

# How far apart profile points are aimed along the ground. Close enough to
# show a switchback climb, far enough that a few metres of elevation error
# moves grade by a few percent rather than by hundreds.
PROFILE_SPACING_M = 50.0

# Ceiling on points in one profile. Past it, spacing widens instead, so a
# thru-hike stays a response of a few hundred kilobytes. 2,000 points covers
# 100 km at the default spacing, and is more than a chart has pixels for.
MAX_PROFILE_POINTS = 2_000

# How far elevation has to move from the last counted point before the change
# counts as climb or descent. Anything smaller is treated as noise.
#
# Chosen against 300 Peakbagger tracks with recorded elevation, comparing each
# track's computed gain with the total gain its climber reported. Reports are
# rounded estimates, so this settles the scale of the threshold, not its exact
# value. Median computed / reported gain:
#
#   threshold   0 m   3 m   5 m   10 m   15 m
#   ratio      1.28  1.12  1.07   1.01   0.98
#
# Median error stops improving around 10 m, and 15 m starts to undercount.
CLIMB_THRESHOLD_M = 10.0


@dataclass(frozen=True)
class ProfilePoint:
    """One point on a profile.

    Attributes:
        distance_m: Distance along the route, from its start.
        elevation_m: Elevation at this point.
        grade_percent: Average grade from the previous profile point to this
            one, positive uphill. None for the first point, which has nothing
            before it, and for a point at the same distance as the previous
            one, where grade is undefined.
    """

    distance_m: float
    elevation_m: float
    grade_percent: float | None


@dataclass(frozen=True)
class Profile:
    """A route's elevation profile.

    Attributes:
        spacing_m: The least distance apart that points were aimed, widened
            on a route too long to fit within the point ceiling. Targets sit
            between this and just under twice it, and each lands on the
            recorded point nearest it, so actual gaps vary.
        length_m: Distance along the whole route.
        gain_m: Total climb over every point, ignoring changes smaller than
            the threshold.
        loss_m: Total descent, counted the same way.
        points: Profile points in walked order, always including the route's
            first and last points.
    """

    spacing_m: float
    length_m: float
    gain_m: float
    loss_m: float
    points: list[ProfilePoint]


def get_elevation_change(
    elevations: Sequence[float], threshold_m: float = CLIMB_THRESHOLD_M
) -> tuple[float, float]:
    """Total climb and total descent, as ``(gain_m, loss_m)``.

    Keeps an anchor at the last elevation that counted, and only counts a
    change once elevation has moved at least ``threshold_m`` from it. Summing
    every rise instead would count GPS noise as climbing: a few metres of
    jitter on each of thousands of points adds up to hundreds of metres that
    nobody walked.

    A change still under the threshold when the route ends is not counted.
    """
    if not elevations:
        return 0.0, 0.0

    gain_m = loss_m = 0.0
    anchor = elevations[0]
    for elevation in elevations[1:]:
        change = elevation - anchor
        if change >= threshold_m:
            gain_m += change
            anchor = elevation
        elif -change >= threshold_m:
            loss_m -= change
            anchor = elevation
    return gain_m, loss_m


def build_profile(
    points: Sequence[Point],
    spacing_m: float = PROFILE_SPACING_M,
    max_points: int = MAX_PROFILE_POINTS,
) -> Profile:
    """The elevation profile of a route.

    Requires at least one point, and ``max_points`` of at least 2.
    """
    distance = get_cumulative_m(points)
    length_m = distance[-1]

    # Widening here, rather than leaving it to the point ceiling, keeps the
    # reported spacing true to what was asked of the points.
    spacing_m = max(spacing_m, length_m / (max_points - 1))
    indices = get_spaced_indices(
        range(len(points)), distance, spacing_m, max_count=max_points
    )

    profile_points = [ProfilePoint(distance[indices[0]], points[indices[0]][2], None)]
    for low, high in pairwise(indices):
        run_m = distance[high] - distance[low]
        climb_m = points[high][2] - points[low][2]
        grade = climb_m / run_m * 100 if run_m > 0 else None
        profile_points.append(ProfilePoint(distance[high], points[high][2], grade))

    gain_m, loss_m = get_elevation_change([elevation for _, _, elevation in points])

    return Profile(
        spacing_m=spacing_m,
        length_m=length_m,
        gain_m=gain_m,
        loss_m=loss_m,
        points=profile_points,
    )
