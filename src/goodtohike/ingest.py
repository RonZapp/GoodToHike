"""Turning a parsed track into a Route."""

from goodtohike.elevation import ElevationFiller
from goodtohike.gaps import check_continuity, check_track_joins, fill_gaps
from goodtohike.route import ParsedTrack, Route

UNNAMED = "Unnamed route"


def build_route(track: ParsedTrack, filler: ElevationFiller) -> Route:
    """Build a Route, filling elevation with the chosen filler."""
    # Geometry first. A jump too large to be one walk is rejected outright,
    # and everything else is straight-lined.
    check_track_joins(track.points, track.track_seams)
    check_continuity(track.points)
    points_without_gaps, inferred = fill_gaps(track.points)

    # Now handle missing elevation.
    points_with_elevations = filler.fill(points_without_gaps)

    return Route(
        name=track.name or UNNAMED,
        points=points_with_elevations,
        source=track.source,
        inferred_ranges=inferred,
    )
