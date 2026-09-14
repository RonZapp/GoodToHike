"""Deciding what to do about distance between consecutive track points."""

from collections.abc import Sequence
from dataclasses import dataclass

from gpxpy.geo import haversine_distance

from goodtohike.geometry import get_hops_m, lerp_coordinate
from goodtohike.route import RawPoint

# Gaps shorter than this are considered ordinary point spacing. Nothing to do.
NORMAL_HOP_M = 100.0

# With gaps above this, the file is not plausibly one continuous walk.
# purpose: platforms simplify tracks before export, so a dead-straight road
# walk can legitimately be two points kilometres apart, and a hiker who loses
# signal in a canyon for a quarter of an hour leaves a real 1 km gap.
MAX_HOP_M = 5_000.0

# How far apart two consecutive source tracks may be and still count as one
# paused walk. Deliberately tight, and much tighter than MAX_HOP_M, because a
# gap inside a track is signal loss or simplified straight line and can
# legitimately be long, while a gap at a track boundary usually means somebody pressed
# stop and then start. They were standing still, so the distance should be GPS
# drift and nothing more.
MAX_TRACK_JOIN_M = 100.0

# Target spacing for points inserted across a gap, with a ceiling so a single
# large gap cannot dominate the track.
FILL_SPACING_M = 50.0
MAX_INSERTED_PER_GAP = 400


class TrackGapError(ValueError):
    """A track with a jump too large to be one continuous walk."""


@dataclass(frozen=True)
class Hop:
    """The distance from point ``index`` to point ``index + 1``."""

    index: int
    distance_m: float


def find_hops_over(points: Sequence[RawPoint], threshold_m: float) -> list[Hop]:
    """Every consecutive pair further apart than ``threshold_m``."""
    return [
        Hop(index=i, distance_m=d)
        for i, d in enumerate(get_hops_m(points))
        if d > threshold_m
    ]


def check_continuity(points: Sequence[RawPoint], max_hop_m: float = MAX_HOP_M) -> None:
    """Raise if any jump is too large for the track to be one walk.

    The message names the worst offender, a user who has to act on this
    needs to know where the problem is rather than only that one exists.
    """
    too_far = find_hops_over(points, max_hop_m)
    if not too_far:
        return

    worst = max(too_far, key=lambda hop: hop.distance_m)
    raise TrackGapError(
        f"This track jumps {worst.distance_m / 1000:.1f} km between points "
        f"{worst.index} and {worst.index + 1}"
        + (f", and has {len(too_far)} such jumps" if len(too_far) > 1 else "")
        + ". That is too far to be one continuous walk, so the file may hold "
        "several separate outings, or a drive between trailheads. Split it "
        "into one file per walk and upload them separately."
    )


def check_track_joins(
    points: Sequence[RawPoint],
    track_starts: list[int],
    max_join_m: float = MAX_TRACK_JOIN_M,
) -> None:
    """Raise unless every source track continues where the previous one ended.

    A file holding several tracks is either one walk recorded across pauses,
    or a route plus unrelated geometry such as hazard zones and closures,
    which tools store as extra tracks because GPX has no type for an area.

    Nothing in the format distinguishes them, so this asks the data instead:
    paused tracks chain end-to-start within GPS drift, and unrelated geometry
    starts wherever the hazard happens to be.

    This sometimes rejects valid files, and that is the intended trade. Guessing
    which track is the route and guessing wrong produces a confidently wrong
    trip brief, which is a worse outcome than being turned away.
    """
    for start in track_starts:
        end_of_previous = points[start - 1]
        start_of_next = points[start]
        join_m = haversine_distance(
            end_of_previous[0],
            end_of_previous[1],
            start_of_next[0],
            start_of_next[1],
        )
        if join_m > max_join_m:
            raise TrackGapError(
                f"This file holds several tracks that do not join up: one ends "
                f"{join_m / 1000:.1f} km from where the next begins. That "
                f"usually means the file contains more than the walk itself, "
                f"such as hazard zones, closures or a second outing. Upload a "
                f"file containing only the track you walked."
            )


def fill_gaps(
    points: Sequence[RawPoint],
    min_gap_m: float = NORMAL_HOP_M,
    spacing_m: float = FILL_SPACING_M,
    max_inserted: int = MAX_INSERTED_PER_GAP,
) -> tuple[list[RawPoint], list[tuple[int, int]]]:
    """Insert straight-line points across gaps wider than ``min_gap_m``.

    Returns the new point list and the index ranges that were inserted, each
    ``(start, end)`` inclusive in the *new* list. Ranges rather than a flag on
    every point: a long track has tens of thousands of points and only a
    handful of gaps, so the ranges cost almost nothing to carry.

    Inserted points get no elevation. They are new positions that nothing has
    measured, so they become elevation gaps by construction and are filled by
    whichever elevation path the track ends up taking.
    """
    if len(points) < 2:
        return list(points), []

    hops = get_hops_m(points)
    filled: list[RawPoint] = [points[0]]
    inferred: list[tuple[int, int]] = []

    for index, hop in enumerate(hops):
        start, end = points[index], points[index + 1]
        if hop > min_gap_m:
            count = min(int(hop // spacing_m) - 1, max_inserted)
            if count > 0:
                first_new = len(filled)
                for step in range(1, count + 1):
                    lat, lon = lerp_coordinate(start, end, step / (count + 1))
                    filled.append((lat, lon, None))
                inferred.append((first_new, len(filled) - 1))
        filled.append(end)

    return filled, inferred
