import pytest

from goodtohike.gpx import (
    NO_POINTS,
    NOT_DECODABLE,
    NOT_GPX,
    ROUTE_NOT_TRACK,
    SOURCE,
    GpxError,
    parse_gpx,
)

PROLOG = '<?xml version="1.0" encoding="UTF-8"?>\n'
OPEN_GPX = (
    '<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">'
)


def gpx(*children: str) -> bytes:
    """A GPX 1.1 document holding ``children``, encoded as an upload would be."""
    return (PROLOG + OPEN_GPX + "".join(children) + "</gpx>").encode("utf-8")


def trkpt(lat: float, lon: float, ele: float | str | None = None) -> str:
    inner = f"<ele>{ele}</ele>" if ele is not None else ""
    return f'<trkpt lat="{lat}" lon="{lon}">{inner}</trkpt>'


def trk(*points: str, name: str | None = None) -> str:
    """One track with a single segment holding ``points``."""
    named = f"<name>{name}</name>" if name is not None else ""
    return f"<trk>{named}<trkseg>{''.join(points)}</trkseg></trk>"


def metadata_name(name: str) -> str:
    return f"<metadata><name>{name}</name></metadata>"


# Points


def test_parse_gpx_reads_points_in_file_order():
    points = [trkpt(47.0, -123.0, 100), trkpt(47.001, -123.002, 110.5)]

    track = parse_gpx(gpx(trk(*points)))

    assert track.points == [(47.0, -123.0, 100.0), (47.001, -123.002, 110.5)]
    assert track.source == SOURCE


def test_parse_gpx_gives_none_for_a_point_without_elevation():
    track = parse_gpx(gpx(trk(trkpt(47.0, -123.0))))

    assert track.points == [(47.0, -123.0, None)]


@pytest.mark.parametrize("zero", ["0", "0.0", "0.00"])
def test_parse_gpx_blanks_placeholder_zero_elevation(zero):
    track = parse_gpx(gpx(trk(trkpt(47.0, -123.0, zero))))

    assert track.points == [(47.0, -123.0, None)]


@pytest.mark.parametrize("elevation", [-3.5, 0.4, 1234.0])
def test_parse_gpx_keeps_nonzero_elevation(elevation):
    # Death Valley is below sea level, and a coastal track can sit at 0.4 m.
    track = parse_gpx(gpx(trk(trkpt(47.0, -123.0, elevation))))

    assert track.points == [(47.0, -123.0, elevation)]


def test_parse_gpx_flattens_segments_within_a_track_without_a_seam():
    # Segments inside one track are pauses in one recording, not separate tracks.
    two_segments = (
        f"<trk><trkseg>{trkpt(47.0, -123.0, 1)}</trkseg>"
        f"<trkseg>{trkpt(47.1, -123.0, 2)}</trkseg></trk>"
    )

    track = parse_gpx(gpx(two_segments))

    assert track.points == [(47.0, -123.0, 1.0), (47.1, -123.0, 2.0)]
    assert track.track_seams == []


# Track seams


def test_parse_gpx_single_track_has_no_seams():
    track = parse_gpx(gpx(trk(trkpt(47.0, -123.0, 1), trkpt(47.1, -123.0, 1))))

    assert track.track_seams == []


def test_parse_gpx_records_seam_at_first_point_of_each_later_track():
    first = trk(trkpt(47.0, -123.0, 1), trkpt(47.1, -123.0, 1))
    second = trk(trkpt(47.2, -123.0, 1))
    third = trk(trkpt(47.3, -123.0, 1), trkpt(47.4, -123.0, 1))

    track = parse_gpx(gpx(first, second, third))

    assert len(track.points) == 5
    assert track.track_seams == [2, 3]


def test_parse_gpx_skips_empty_tracks_without_recording_a_seam():
    empty = "<trk><trkseg></trkseg></trk>"

    track = parse_gpx(
        gpx(empty, trk(trkpt(47.0, -123.0, 1)), empty, trk(trkpt(47.1, -123.0, 1)))
    )

    assert len(track.points) == 2
    assert track.track_seams == [1]


# Names


def test_parse_gpx_prefers_the_file_name_over_the_track_name():
    day_one = trk(trkpt(47.0, -123.0, 1), name="Day 1")

    track = parse_gpx(gpx(metadata_name("Enchanted Valley"), day_one))

    assert track.name == "Enchanted Valley"


def test_parse_gpx_falls_back_to_the_first_named_track():
    unnamed = trk(trkpt(47.0, -123.0, 1))
    named = trk(trkpt(47.0001, -123.0, 1), name="Tidal Zone 2")

    track = parse_gpx(gpx(unnamed, named))

    assert track.name == "Tidal Zone 2"


def test_parse_gpx_strips_whitespace_from_names():
    track = parse_gpx(gpx(trk(trkpt(47.0, -123.0, 1), name="  Hoh River  ")))

    assert track.name == "Hoh River"


def test_parse_gpx_treats_blank_names_as_absent():
    track = parse_gpx(gpx(metadata_name("   "), trk(trkpt(47.0, -123.0, 1), name=" ")))

    assert track.name is None


def test_parse_gpx_reads_non_ascii_names():
    track = parse_gpx(gpx(trk(trkpt(47.0, -123.0, 1), name="Cañon Creek")))

    assert track.name == "Cañon Creek"


# Encoding


def test_parse_gpx_accepts_a_utf8_byte_order_mark():
    # Windows tools commonly prefix UTF-8 files with one.
    track = parse_gpx(b"\xef\xbb\xbf" + gpx(trk(trkpt(47.0, -123.0, 1))))

    assert track.points == [(47.0, -123.0, 1.0)]


def test_parse_gpx_rejects_bytes_that_are_not_utf8():
    # Declares Latin-1 honestly, but the decision is to read UTF-8 only.
    latin1 = (
        b'<?xml version="1.0" encoding="ISO-8859-1"?>'
        b'<gpx version="1.1"><trk><name>Ca\xf1on</name><trkseg>'
        b'<trkpt lat="47" lon="-123"/></trkseg></trk></gpx>'
    )

    with pytest.raises(GpxError) as caught:
        parse_gpx(latin1)

    assert str(caught.value) == NOT_DECODABLE


# Rejections


def test_gpx_error_is_a_value_error():
    # Lets the HTTP layer treat every bad-upload error alike, as TrackGapError is too.
    assert issubclass(GpxError, ValueError)


@pytest.mark.parametrize(
    "raw",
    [b"", b"this is not gpx at all", b'{"type": "FeatureCollection"}', b"<gpx"],
    ids=["empty", "plain text", "json", "truncated xml"],
)
def test_parse_gpx_rejects_content_that_is_not_gpx(raw):
    with pytest.raises(GpxError) as caught:
        parse_gpx(raw)

    assert str(caught.value) == NOT_GPX


def test_parse_gpx_explains_a_route_export():
    route = (
        '<rte><rtept lat="47.0" lon="-123.0"/><rtept lat="47.1" lon="-123.0"/></rte>'
    )

    with pytest.raises(GpxError) as caught:
        parse_gpx(gpx(route))

    assert str(caught.value) == ROUTE_NOT_TRACK


@pytest.mark.parametrize(
    "children",
    [(), ('<wpt lat="47.0" lon="-123.0"/>',), ("<trk><trkseg></trkseg></trk>",)],
    ids=["no content", "waypoints only", "empty track"],
)
def test_parse_gpx_rejects_a_file_without_track_points(children):
    with pytest.raises(GpxError) as caught:
        parse_gpx(gpx(*children))

    assert str(caught.value) == NO_POINTS
