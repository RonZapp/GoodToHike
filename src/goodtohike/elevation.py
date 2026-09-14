"""Providing elevation data for gps points.

This module is designed to end at the boundary where work can no longer be
done internally, ensure nothing is added here that does I/O.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Protocol

from goodtohike.geometry import get_cumulative_m
from goodtohike.route import Point, RawPoint


class ElevationFiller(Protocol):
    """A policy for giving every point an elevation.

    Strategy pattern, classes that implement the protocol will determine how to
    fill elevations, and what to do with tracks that already have complete
    elevations.
    """

    def fill(self, points: Sequence[RawPoint]) -> list[Point]:
        """Returns the track with an elevation on every point.

        Guarantees one output point per input point, same order,
        elevation always present.
        """
        ...


@dataclass(frozen=True)
class InterpolateOnly:
    """Fills missing elevations from the track's own, never looking anything up.

    Gaps between known elevations are interpolated, and gaps at either end of
    the track hold the nearest known value flat. Recorded elevations are kept.
    """

    def fill(self, points: Sequence[RawPoint]) -> list[Point]:
        """Fills missing elevations from the recorded ones.

        Returns [] for an empty track. Raises ValueError when a track has no
        recorded elevations at all, since there is nothing to interpolate from.
        """
        if not points:
            return []
        recorded = [elevation for _, _, elevation in points]
        return _interpolate(points, get_cumulative_m(points), recorded)


# The helpers below are private to this module, and trust what they are given
# rather than checking it. Each states what it requires. Only the fetcher's
# answer is checked, because it comes from outside.


def _interpolate(
    points: Sequence[RawPoint],
    distance: Sequence[float],
    elevations: Sequence[float | None],
) -> list[Point]:
    """Returns a list where every Point has an elevation, calculating missing ones
    by straight-line interpolating between known ones.

    Requires ``distance`` and ``elevations`` to hold one entry per point, where
    ``elevations`` is None wherever the elevation is still unknown, and
    ``distance`` never decreases. Whatever elevation the points themselves
    carry is ignored.

    Weighted by distance along the track, so a point halfway in metres between
    two known elevations gets the midpoint value, regardless of how many
    recorded points happen to sit on either side of it. Points before the first
    known elevation or after the last hold it flat, rather than extrapolating a
    trend off the end of the data.

    Raises ValueError when no elevation is known.
    """
    known = [
        (index, elevation)
        for index, elevation in enumerate(elevations)
        if elevation is not None
    ]
    if not known:
        raise ValueError("track has no elevation to interpolate from")

    first_index, first_elevation = known[0]
    filled = [first_elevation] * first_index

    for (low, low_elevation), (high, high_elevation) in pairwise(known):
        filled.append(low_elevation)
        if high == low + 1:
            # Nothing missing between them, the usual case on a recorded track.
            continue
        run_m = distance[high] - distance[low]
        if run_m <= 0:
            # Stationary points share one distance, and would divide by zero.
            filled.extend([low_elevation] * (high - low - 1))
            continue
        climb_m = high_elevation - low_elevation
        filled.extend(
            low_elevation + climb_m * (distance[index] - distance[low]) / run_m
            for index in range(low + 1, high)
        )

    last_index, last_elevation = known[-1]
    filled.extend([last_elevation] * (len(points) - last_index))

    return [
        (lat, lon, elevation)
        for (lat, lon, _), elevation in zip(points, filled, strict=True)
    ]
