"""Distance along a route, over our own point type.

The spherical trigonometry comes from :mod:`gpxpy.geo`, whose functions take
plain floats and are not tied to GPX in any way. Only the compositions that
gpxpy has no equivalent for live here, because it offers cumulative distance
solely as a method on its own objects.
"""

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
    return cumulative if len(cumulative) > 1 else []


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
