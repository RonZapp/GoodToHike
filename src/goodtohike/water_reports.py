"""Field reports on water sources: whether a spring or stream is running.

Water sources are not stored here. A report names its source by an id from the
map data the source comes from, such as ``osm-node-5207123456`` for a spring
mapped in OpenStreetMap, so reports stay attached to the same spring whichever
uploaded route passes it. See ``docs/decisions/0005``.
"""

from datetime import timedelta
from typing import Literal

WaterStatus = Literal["flowing", "trickle", "dry"]

# An OpenStreetMap element: a node for a spring or tap, a way or relation for a
# stream or lake. Prefixed with its source, so ids from other map data can sit
# beside these later without colliding.
WATER_SOURCE_ID_PATTERN = r"^osm-(node|way|relation)-[1-9][0-9]{0,18}$"
MAX_WATER_SOURCE_ID_LENGTH = 40

MAX_NOTE_LENGTH = 500

# How far past the server's clock an observation may claim to be, since a
# phone's clock can run a little ahead.
ALLOWED_CLOCK_SKEW = timedelta(minutes=5)
