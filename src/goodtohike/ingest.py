"""Turning a parsed track into a Route."""

from goodtohike.elevation import ElevationFiller
from goodtohike.gaps import check_continuity, check_track_joins, fill_gaps
from goodtohike.route import MAX_NAME_LENGTH, ParsedTrack, Route

UNNAMED = "Unnamed route"


def _choose_name(given: str | None, from_file: str | None) -> str:
    """The uploader's name, then the file's, then a default."""
    for candidate in (given, from_file):
        if candidate and candidate.strip():
            return candidate.strip()[:MAX_NAME_LENGTH].rstrip()
    return UNNAMED


def build_route(
    track: ParsedTrack, filler: ElevationFiller, name: str | None = None
) -> Route:
    """Build a Route, filling elevation with the chosen filler.

    A given ``name`` wins over the track's own.
    A name that is empty or only whitespace counts as not given.
    """

    # Geometry first. A jump too large to be one walk is rejected outright,
    # and everything else is straight-lined.
    check_track_joins(track.points, track.track_seams)
    check_continuity(track.points)
    points_without_gaps, inferred = fill_gaps(track.points)

    # Now handle missing elevation.
    points_with_elevations = filler.fill(points_without_gaps)

    return Route(
        name=_choose_name(name, track.name),
        points=points_with_elevations,
        source=track.source,
        inferred_ranges=inferred,
    )
