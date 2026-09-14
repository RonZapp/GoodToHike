"""Providing elevation data for gps points.

This module is designed to end at the boundary where work can no longer be
done internally, ensure nothing is added here that does I/O.
"""

import math
from bisect import bisect_left
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import groupby, pairwise
from typing import Protocol

from goodtohike.geometry import get_cumulative_m
from goodtohike.route import Point, RawPoint

# The smallest distance apart that elevation lookups are aimed along the
# ground.
DEFAULT_SPACING_M = 200.0

# Ceiling on the lookups spent on any one elevation gap, whatever the spacing
# asks for. It applies to each gap separately, so a track with several gaps
# can look up more than this in total.
DEFAULT_MAX_SAMPLES = 400

# Longest elevation gap, measured from the last known elevation before it to
# the first known one after it, that we are comfortable filling with
# interpolation rather than a lookup.
DEFAULT_MAX_GAP_M = 250.0

# Given coordinates, return one elevation in metres for each, in order.
ElevationFetcher = Callable[[Sequence[tuple[float, float]]], Sequence[float]]


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


@dataclass(frozen=True, kw_only=True)
class HybridFill:
    """Interpolates short elevation gaps and looks up long ones.

    Decides gap by gap, by the gap's bridge: the along-track distance from the last
    known elevation before it to the first known one after it, or from the
    track's start, or to its end, for a gap at either end.

    A gap whose bridge is no longer than ``max_gap_m`` is interpolated from the
    track's own elevations, or held flat if it runs off either end of the track.
    A longer one has elevations looked up through ``fetch`` at points at least
    ``spacing_m`` apart across it, up to ``DEFAULT_MAX_SAMPLES`` per gap, so
    lookups scale with how much elevation is missing rather than with the
    length of the track.

    A track with no elevation at all is looked up whatever its length, since
    there is nothing to interpolate from. Recorded elevations are kept.
    """

    fetch: ElevationFetcher
    max_gap_m: float = DEFAULT_MAX_GAP_M
    spacing_m: float = DEFAULT_SPACING_M

    def fill(self, points: Sequence[RawPoint]) -> list[Point]:
        """Fills each gap by interpolation or lookup, per the class docstring.

        Returns [] for an empty track. Raises ValueError when ``fetch`` returns
        a different number of elevations than it was asked for.
        """
        if not points:
            return []

        distance = get_cumulative_m(points)
        elevations = [elevation for _, _, elevation in points]
        last = len(points) - 1

        # groupby hands over each run of consecutive missing elevations as it
        # reaches it, so every gap is found, measured and decided in one pass.
        lookups: list[int] = []
        for missing, group in groupby(
            range(len(points)), key=lambda index: elevations[index] is None
        ):
            if not missing:
                continue
            indices = list(group)
            run = range(indices[0], indices[-1] + 1)
            bridge_m = distance[min(run.stop, last)] - distance[max(run.start - 1, 0)]
            if len(run) == len(points) or bridge_m > self.max_gap_m:
                lookups.extend(_spaced_indices(run, distance, self.spacing_m))

        looked_up = _look_up(points, lookups, self.fetch)
        for index, elevation in zip(lookups, looked_up, strict=True):
            elevations[index] = elevation
        return _interpolate(points, distance, elevations)


@dataclass(frozen=True, kw_only=True)
class LookUpGaps:
    """Looks up elevation in every gap, however short, and keeps the rest.

    Each gap has elevations looked up through ``fetch`` at points at least
    ``spacing_m`` apart across it, up to ``DEFAULT_MAX_SAMPLES`` per gap, and
    at least one lookup even for a single missing point. Points between
    lookups are interpolated along the ground. Recorded elevations are kept.

    The track's first and last points are always looked up when they have no
    elevation, so neither end of the profile is held flat from a guess.
    """

    fetch: ElevationFetcher
    spacing_m: float = DEFAULT_SPACING_M

    def fill(self, points: Sequence[RawPoint]) -> list[Point]:
        """Fills every gap from lookups, per the class docstring.

        Returns [] for an empty track. Raises ValueError when ``fetch`` returns
        a different number of elevations than it was asked for.
        """
        # HybridFill with no gap short enough to interpolate. Not 0: a missing
        # point between two recorded ones on the same spot bridges 0 m.
        hybrid = HybridFill(
            fetch=self.fetch, spacing_m=self.spacing_m, max_gap_m=-math.inf
        )
        return hybrid.fill(points)


@dataclass(frozen=True, kw_only=True)
class LookUpEveryPoint:
    """Replaces every elevation, recorded or missing, with its own lookup.

    Nothing is interpolated and nothing recorded is kept, so the profile comes
    entirely from the elevation service. GPS elevation is noisy, and this
    trades it for one lookup per point: every coordinate goes to ``fetch`` in a
    single call with no sample ceiling, so a 70,000-point track asks for
    70,000 elevations, and splitting that into requests the service accepts
    is the fetcher's job.
    """

    fetch: ElevationFetcher

    def fill(self, points: Sequence[RawPoint]) -> list[Point]:
        """Looks up an elevation for every point, per the class docstring.

        Returns [] for an empty track. Raises ValueError when ``fetch`` returns
        a different number of elevations than it was asked for.
        """
        looked_up = _look_up(points, range(len(points)), self.fetch)
        return [
            (lat, lon, elevation)
            for (lat, lon, _), elevation in zip(points, looked_up, strict=True)
        ]


# The helpers below are private to this module, and trust what they are given
# rather than checking it. Each states what it requires. Only the fetcher's
# answer is checked, because it comes from outside.


def _spaced_indices(
    run: range, distance: Sequence[float], spacing_m: float
) -> list[int]:
    """Indices inside ``run`` to look up, spread evenly along the ground.

    Requires a non-empty ``run`` and ``distance`` holding the distance along
    the track at every point, never decreasing.

    Aims at as many evenly spaced targets as fit at least ``spacing_m`` apart,
    so the spacing between targets lands between ``spacing_m`` and just under
    twice it, then takes the point nearest each target. Never returns more
    than ``DEFAULT_MAX_SAMPLES``; a longer run gets wider spacing instead.

    The run's first and last points are always included, so a gap at either
    end of the track has that end looked up rather than held flat. Returns
    indices in ascending order without repeats.
    """
    first, last = run.start, run.stop - 1
    start_m = distance[first]
    length_m = distance[last] - start_m

    # Counting both ends. Too short a run, or no spacing, wants only the ends.
    wanted = 2
    if spacing_m > 0:
        wanted = min(int(length_m // spacing_m) + 1, DEFAULT_MAX_SAMPLES)

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


def _look_up(
    points: Sequence[RawPoint], indices: Sequence[int], fetch: ElevationFetcher
) -> list[float]:
    """Elevations for the points at ``indices``, in the same order.

    Sends every coordinate in one call, so the fetcher can batch its requests,
    and makes no call at all when ``indices`` is empty.

    Raises ValueError when ``fetch`` returns a different number of elevations
    than it was asked for.
    """
    if not indices:
        return []

    fetched = list(fetch([points[index][:2] for index in indices]))
    if len(fetched) != len(indices):
        raise ValueError(
            f"asked for {len(indices)} elevations, fetcher returned {len(fetched)}"
        )
    return fetched


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
