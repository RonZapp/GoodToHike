"""Weather along a route: where to forecast, and gathering those forecasts.

A forecast describes a grid cell a few kilometres across, not a point, so a
route needs a handful of forecasts rather than one per point. Which places get
one is decided here. Fetching them is not: the caller supplies a
:class:`WeatherSource`, which keeps this module free of I/O and testable
without a network, the same way elevation filling takes a fetcher.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from goodtohike.geometry import get_cumulative_m, get_spaced_indices
from goodtohike.route import Point

# How far apart forecast locations are aimed along the ground. Weather over a
# day's walk changes more with elevation than with distance, so this is kept
# coarse, and the route's highest point is always added on top of it.
FORECAST_SPACING_M = 25_000.0

# Ceiling on forecast locations for one route, the highest point included.
# Past it, spacing widens instead. Each location can cost two requests to the
# weather service, so this bounds the work a single request can cause, however
# long the route is.
MAX_FORECAST_LOCATIONS = 10


@dataclass(frozen=True)
class GridCell:
    """The forecast area a location falls in, named the way the source names it."""

    office: str
    x: int
    y: int


@dataclass(frozen=True)
class ForecastPeriod:
    """One period of a forecast, usually a day or a night.

    Attributes:
        name: The source's own label, such as ``Tonight`` or ``Tuesday``.
        start_time: When the period starts, with the offset the source gave.
        end_time: When the period ends, with the offset the source gave.
        is_daytime: Whether this is a day period rather than a night one.
        temperature_c: The period's high for a day, or low for a night.
        precipitation_chance_percent: Chance of precipitation, or None when
            the source gives none.
        wind_speed: As the source words it, such as ``10 to 15 km/h``.
        wind_direction: Compass direction the wind blows from, such as ``NW``.
        short_forecast: A few words, such as ``Mostly Sunny``.
        detailed_forecast: A sentence or two of prose.
    """

    name: str
    start_time: datetime
    end_time: datetime
    is_daytime: bool
    temperature_c: float
    precipitation_chance_percent: float | None
    wind_speed: str
    wind_direction: str
    short_forecast: str
    detailed_forecast: str


@dataclass(frozen=True)
class Forecast:
    """A forecast for one grid cell.

    Attributes:
        updated_at: When the source last updated the forecast.
        elevation_m: The elevation the forecast is made for, which is the
            cell's, not any one point's. None when the source does not say.
        periods: Forecast periods in time order.
    """

    updated_at: datetime
    elevation_m: float | None
    periods: list[ForecastPeriod]


@dataclass(frozen=True)
class LocationForecast:
    """The forecast at one place along a route.

    Attributes:
        distance_m: Distance along the route, from its start.
        lat: Latitude of the route point.
        lon: Longitude of the route point.
        elevation_m: Elevation of the route point.
        is_high_point: Whether this is the route's highest point.
        forecast: The forecast for the cell this point falls in, or None when
            the source has no forecast there, such as outside its coverage.
    """

    distance_m: float
    lat: float
    lon: float
    elevation_m: float
    is_high_point: bool
    forecast: Forecast | None


class NoWeatherCoverageError(Exception):
    """The weather source has no forecast for a location."""

    def __init__(self, lat: float, lon: float) -> None:
        super().__init__(f"no weather coverage at {lat},{lon}")
        self.lat = lat
        self.lon = lon


class WeatherServiceError(Exception):
    """The weather source failed, or answered with something unreadable."""


class WeatherSource(Protocol):
    """Where forecasts come from."""

    def get_cell(self, lat: float, lon: float) -> GridCell:
        """The grid cell a location falls in.

        Raises NoWeatherCoverageError where the source has no forecasts, and
        WeatherServiceError when it fails.
        """
        ...

    def get_forecast(self, cell: GridCell) -> Forecast:
        """The current forecast for a cell. Raises WeatherServiceError."""
        ...


def get_high_point_index(points: Sequence[Point]) -> int:
    """Index of the highest point, the first one if several tie.

    Requires at least one point.
    """
    return max(range(len(points)), key=lambda index: points[index][2])


def choose_forecast_indices(
    points: Sequence[Point],
    spacing_m: float = FORECAST_SPACING_M,
    max_locations: int = MAX_FORECAST_LOCATIONS,
) -> list[int]:
    """Indices of the points to forecast, in walked order.

    Points spaced about ``spacing_m`` apart along the ground, always including
    the start and the end, plus the highest point. Never more than
    ``max_locations``; a longer route gets wider spacing instead.

    Requires at least one point, and ``max_locations`` of at least 3, which
    leaves room for the start, the end and the highest point.
    """
    distance = get_cumulative_m(points)
    # One place is held back for the highest point, whether or not it lands
    # on a spaced point anyway.
    spaced = get_spaced_indices(
        range(len(points)), distance, spacing_m, max_count=max_locations - 1
    )
    return sorted({*spaced, get_high_point_index(points)})


def get_route_forecasts(
    points: Sequence[Point],
    weather: WeatherSource,
    spacing_m: float = FORECAST_SPACING_M,
    max_locations: int = MAX_FORECAST_LOCATIONS,
) -> list[LocationForecast]:
    """Forecasts at the places :func:`choose_forecast_indices` picks.

    Locations that share a grid cell share one forecast request. A location
    the source has no coverage for gets None instead of a forecast, so a route
    running partly outside coverage still gets forecasts for the rest.

    Requires at least one point. Raises WeatherServiceError when the source
    fails.
    """
    distance = get_cumulative_m(points)
    high = get_high_point_index(points)

    forecasts: dict[GridCell, Forecast] = {}
    located: list[LocationForecast] = []
    for index in choose_forecast_indices(points, spacing_m, max_locations):
        lat, lon, elevation = points[index]
        try:
            cell = weather.get_cell(lat, lon)
        except NoWeatherCoverageError:
            forecast = None
        else:
            if cell not in forecasts:
                forecasts[cell] = weather.get_forecast(cell)
            forecast = forecasts[cell]
        located.append(
            LocationForecast(
                distance_m=distance[index],
                lat=lat,
                lon=lon,
                elevation_m=elevation,
                is_high_point=index == high,
                forecast=forecast,
            )
        )
    return located
