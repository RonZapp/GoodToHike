"""Distance along a route, over our own point type."""

from bisect import bisect_left
from collections.abc import Sequence

from gpxpy.geo import haversine_distance

from goodtohike.route import RawPoint


def get_hops_m(points: Sequence[RawPoint]) -> list[float]:
    """Distance between each consecutive pair. One shorter than ``points``."""
    return [
        haversine_distance(a[0], a[1], b[0], b[1]) for a, b in zip(points, points[1:])
    ]


def get_cumulative_m(points: Sequence[RawPoint]) -> list[float]:
    """Distance along the track at each point, starting at 0.0.

    Path length, not displacement: every bend and switchback counts, so an
    out-and-back ends at twice its one-way length rather than at zero.
    """
    cumulative = [0.0]
    for hop in get_hops_m(points):
        cumulative.append(cumulative[-1] + hop)
    return cumulative if points else []


def get_spaced_indices(
    run: range, distance: Sequence[float], spacing_m: float, *, max_count: int
) -> list[int]:
    """Indices inside ``run`` spread evenly along the ground.

    Requires a non-empty ``run``, ``distance`` holding the distance along the
    track at every point, never decreasing, and ``max_count`` of at least 2.

    Aims at as many evenly spaced targets as fit at least ``spacing_m`` apart,
    so the spacing between targets lands between ``spacing_m`` and just under
    twice it, then takes the point nearest each target. Never returns more
    than ``max_count``; a longer run gets wider spacing instead. The cap is the
    caller's, because what it protects differs: lookups against a service, or
    the size of a response.

    The run's first and last points are always included. Returns indices in
    ascending order without repeats.
    """
    first, last = run.start, run.stop - 1
    start_m = distance[first]
    length_m = distance[last] - start_m

    # Counting both ends. Too short a run, or no spacing, wants only the ends.
    wanted = 2
    if spacing_m > 0:
        wanted = min(int(length_m // spacing_m) + 1, max_count)

    # The ends are added rather than searched for, so only the targets between
    # them go through the search.
    indices = [first]
    for step in range(1, wanted - 1):
        target = start_m + step * length_m / (wanted - 1)
        # Searching only within the run, bisect_left finds the first point at
        # or past the target. The point before it may be nearer. A target
        # strictly between the ends always has a point on each side inside the
        # run, so neither neighbour needs a bounds check.
        position = bisect_left(distance, target, first, run.stop)
        if target - distance[position - 1] <= distance[position] - target:
            position -= 1
        # Points further apart than the spacing, or stationary ones, can map
        # two targets onto one point. Positions never go down, so a repeat can
        # only match the one added just before it.
        if position != indices[-1]:
            indices.append(position)

    if indices[-1] != last:
        indices.append(last)
    return indices


def lerp_coordinate(
    start: RawPoint, end: RawPoint, fraction: float
) -> tuple[float, float]:
    """A coordinate ``fraction`` of the way from ``start`` to ``end``.

    Linear in latitude and longitude rather than along a great circle. Over
    the distances this is used for, a few kilometres at most, the difference
    is centimetres, and the straight line between two trail points is already
    a far bigger approximation than the projection is.
    """
    lat = start[0] + (end[0] - start[0]) * fraction
    lon = start[1] + (end[1] - start[1]) * fraction
    return lat, lon
