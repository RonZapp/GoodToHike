"""Client for the National Weather Service API.

Upstream behaviour this relies on is recorded in ``docs/sources/nws.md``.
"""

from datetime import datetime
from http import HTTPStatus
from typing import Any

import httpx2

from goodtohike.conditions import (
    Forecast,
    ForecastPeriod,
    GridCell,
    NoWeatherCoverageError,
    WeatherServiceError,
)

BASE_URL = "https://api.weather.gov"
ACCEPT = "application/geo+json"

# /points answers a coordinate with more than four decimal places with a 301
# to the rounded URL, which the HTTP client does not follow. Real tracks carry
# up to seven. Four places is about 11 m, far inside a forecast grid cell.
COORDINATE_DECIMALS = 4

# Metric forecasts: Celsius and km/h rather than Fahrenheit and mph.
UNITS = "si"


class NwsClient:
    base_url = BASE_URL
    accept = ACCEPT

    def __init__(self, http: httpx2.Client) -> None:
        self._http = http

    def _get(self, path: str, params: dict[str, str] | None = None) -> dict:
        response = self._http.get(
            f"{self.base_url}{path}",
            params=params,
            headers={"Accept": self.accept},
        )
        response.raise_for_status()
        return response.json()

    def get_point(self, lat: float, lon: float) -> dict:
        lat = round(lat, COORDINATE_DECIMALS)
        lon = round(lon, COORDINATE_DECIMALS)
        return self._get(f"/points/{lat},{lon}")

    def get_gridpoint(self, grid_id: str, grid_x: int, grid_y: int) -> dict:
        return self._get(f"/gridpoints/{grid_id}/{grid_x},{grid_y}")

    def get_gridpoint_forecast(self, grid_id: str, grid_x: int, grid_y: int) -> dict:
        return self._get(
            f"/gridpoints/{grid_id}/{grid_x},{grid_y}/forecast",
            params={"units": UNITS},
        )


class NwsWeather:
    """The National Weather Service as a :class:`~goodtohike.conditions.WeatherSource`.

    Turns its responses into GoodToHike's forecast types, and its failures into
    the errors a weather source raises. Nothing is retried.
    """

    def __init__(self, client: NwsClient) -> None:
        self._client = client

    def get_cell(self, lat: float, lon: float) -> GridCell:
        try:
            body = self._client.get_point(lat, lon)
        except httpx2.HTTPStatusError as exc:
            # /points answers 404 for anywhere it has no forecast, such as
            # open ocean or outside the United States.
            if exc.response.status_code == HTTPStatus.NOT_FOUND:
                raise NoWeatherCoverageError(lat, lon) from exc
            raise WeatherServiceError(
                f"NWS /points failed for {lat},{lon}: {exc}"
            ) from exc
        except (httpx2.TransportError, ValueError) as exc:
            raise WeatherServiceError(
                f"NWS /points failed for {lat},{lon}: {exc!r}"
            ) from exc

        try:
            properties = body["properties"]
            return GridCell(
                office=str(properties["gridId"]),
                x=int(properties["gridX"]),
                y=int(properties["gridY"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise WeatherServiceError(
                f"NWS /points sent no readable grid cell for {lat},{lon}"
            ) from exc

    def get_forecast(self, cell: GridCell) -> Forecast:
        try:
            body = self._client.get_gridpoint_forecast(cell.office, cell.x, cell.y)
        except (httpx2.HTTPError, ValueError) as exc:
            raise WeatherServiceError(
                f"NWS forecast failed for {cell}: {exc!r}"
            ) from exc

        try:
            return _read_forecast(body)
        except (KeyError, TypeError, ValueError) as exc:
            raise WeatherServiceError(
                f"NWS sent an unreadable forecast for {cell}: {exc!r}"
            ) from exc


def _read_forecast(body: dict[str, Any]) -> Forecast:
    """A forecast from a /forecast body. Raises KeyError, TypeError or ValueError."""
    properties = body["properties"]
    return Forecast(
        updated_at=datetime.fromisoformat(properties["updateTime"]),
        elevation_m=(properties.get("elevation") or {}).get("value"),
        periods=[_read_period(period) for period in properties["periods"]],
    )


def _read_period(period: dict[str, Any]) -> ForecastPeriod:
    if period["temperatureUnit"] != "C":
        raise ValueError(f"expected Celsius, got {period['temperatureUnit']!r}")
    return ForecastPeriod(
        name=period["name"],
        start_time=datetime.fromisoformat(period["startTime"]),
        end_time=datetime.fromisoformat(period["endTime"]),
        is_daytime=bool(period["isDaytime"]),
        temperature_c=float(period["temperature"]),
        precipitation_chance_percent=(
            period.get("probabilityOfPrecipitation") or {}
        ).get("value"),
        wind_speed=period["windSpeed"],
        wind_direction=period["windDirection"],
        short_forecast=period["shortForecast"],
        detailed_forecast=period["detailedForecast"],
    )
