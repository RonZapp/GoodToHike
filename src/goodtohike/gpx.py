"""Reading GPX track files into tracks.

This module reports what the file says. It does not interpolate, does not
judge gaps, and does not fetch anything: those are decisions, and they live
in :mod:`goodtohike.gaps` and :mod:`goodtohike.ingest`.
"""

import gpxpy
from gpxpy.gpx import GPX, GPXTrack

from goodtohike.route import ParsedTrack, RawPoint

SOURCE = "gpx"

# GPX declares its encoding in the XML prolog, but gpxpy ignores that and
# decodes bytes as UTF-8 regardless. Decoding here makes the assumption
# visible and turns a violation into our error rather than the library's.
ENCODING = "utf-8"

# Many devices and exporters write <ele>0</ele> when they have no elevation
# fix, so a zero is more often a placeholder than a reading. Keeping one
# carves a spike to sea level and back, inventing phantom climb proportional
# to your real altitude; interpolating a genuine sea-level zero costs a few
# metres, because real sea level is surrounded by low ground.
PLACEHOLDER_ELEVATION = 0.0

ROUTE_NOT_TRACK = (
    "This file holds a GPX route, not a GPX track. A route is a handful of "
    "waypoints joined by straight lines, too coarse to profile or to locate "
    "water crossings. Re-export and choose 'GPX Track'."
)
NOT_DECODABLE = (
    f"File is not valid {ENCODING.upper()} text, so it cannot be read as GPX."
)
NOT_GPX = "File could not be parsed as GPX."
NO_POINTS = "This GPX file contains no track points."


class GpxError(ValueError):
    """A GPX upload that cannot be turned into a usable track.

    Its message is written for the person who uploaded the file, because the
    endpoint hands it straight back to them.
    """


def _count_points(track: GPXTrack) -> int:
    return sum(len(segment.points) for segment in track.segments)


def _blank_placeholder_elevations(gpx: GPX) -> int:
    """Turn placeholder zeros into None, returning how many were blanked."""
    blanked = 0
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                if point.elevation == PLACEHOLDER_ELEVATION:
                    point.elevation = None
                    blanked += 1
    return blanked


def _get_name(gpx: GPX) -> str | None:
    """The first name the file offers, or None if it offers none."""
    if gpx.name and gpx.name.strip():
        return gpx.name.strip()
    for track in gpx.tracks:
        if track.name and track.name.strip():
            return track.name.strip()
    return None


def parse_gpx(raw: bytes) -> ParsedTrack:
    """Turn the bytes of an uploaded GPX file into a track.

    Reports elevation exactly as the file gave it, minus placeholder zeros.

    Raises :class:`GpxError` for anything that cannot yield track points.
    """
    try:
        text = raw.decode(ENCODING)
    except UnicodeDecodeError as exc:
        raise GpxError(NOT_DECODABLE) from exc

    try:
        gpx = gpxpy.parse(text)
    except Exception as exc:
        # gpxpy raises several unrelated types depending on which XML backend
        # it picked, so its exceptions are not a usable contract.
        raise GpxError(NOT_GPX) from exc

    _blank_placeholder_elevations(gpx)

    # Every track and every segment, in file order, flattened into one list.
    # track_seams will record where the tracks split from one-another
    # internally.
    points: list[RawPoint] = []
    track_seams: list[int] = []
    for track in gpx.tracks:
        if _count_points(track) == 0:
            continue
        if points:
            track_seams.append(len(points))
        points.extend(
            (point.latitude, point.longitude, point.elevation)
            for segment in track.segments
            for point in segment.points
        )

    if not points:
        # A route-only export is the common mistake and earns its own message.
        raise GpxError(ROUTE_NOT_TRACK if gpx.routes else NO_POINTS)

    return ParsedTrack(
        points=points,
        source=SOURCE,
        name=_get_name(gpx),
        track_seams=track_seams,
    )
