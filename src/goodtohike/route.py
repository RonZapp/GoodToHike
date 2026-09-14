"""Route types: the track as a source described it, and one we have verified.

Two types, differing by a single guarantee. A source may or may not carry
elevation; a ``Route`` always does.
"""

from dataclasses import dataclass, field

# Latitude, longitude, elevation in metres.
# None means no usable elevation for that point.
RawPoint = tuple[float, float, float | None]

# The same triple, with elevation guaranteed present.
Point = tuple[float, float, float]


@dataclass
class ParsedTrack:
    """A track exactly as its source described it.

    Attributes:
        points: Every point the source offered, in walked order, flattened
            across all of its tracks and segments.
        source: The kind of file this came from, such as ``gpx``.
        name: Whatever the file called the track, or None if it named
            nothing. Picking a name to show a user is the ingest layer's
            job, since it knows things the file does not, such as the
            uploaded filename.
        track_seams: Index of the first point of each source track after
            the first, so a two-track file has one seam. Empty for a
            single-track file.
    """

    points: list[RawPoint]
    source: str
    name: str | None = None
    track_seams: list[int] = field(default_factory=list)


@dataclass
class Route:
    """A track with an elevation at every point.

    Nothing constructs one of these until that is true. See
    :mod:`goodtohike.ingest`.

    Attributes:
        inferred_ranges: Inclusive ``(start, end)`` index spans whose
            coordinates were straight-lined across a gap rather than
            recorded. Empty when the track had no gaps to fill.
    """

    name: str
    points: list[Point]
    source: str
    inferred_ranges: list[tuple[int, int]] = field(default_factory=list)
