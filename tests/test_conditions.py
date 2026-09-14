from datetime import UTC, datetime

import pytest

from goodtohike.conditions import (
    Forecast,
    GridCell,
    NoWeatherCoverageError,
    WeatherServiceError,
    choose_forecast_indices,
    get_high_point_index,
    get_route_forecasts,
)
from goodtohike.route import Point

# A thousandth of a degree of latitude on gpxpy's sphere, about 111 m.
STEP_DEGREES = 0.001
STEP_M = 111.31949


def due_north(count: int, elevation_at=lambda index: 100.0) -> list[Point]:
    """A track heading due north, one point every STEP_M."""
    return [(40.0 + i * STEP_DEGREES, -121.0, elevation_at(i)) for i in range(count)]


class FakeWeather:
    """Puts every 10 km of latitude in its own cell and records what it is asked."""

    def __init__(self, uncovered_below_lat: float = -90.0) -> None:
        self.uncovered_below_lat = uncovered_below_lat
        self.cells_asked: list[tuple[float, float]] = []
        self.forecasts_asked: list[GridCell] = []

    def get_cell(self, lat: float, lon: float) -> GridCell:
        self.cells_asked.append((lat, lon))
        if lat < self.uncovered_below_lat:
            raise NoWeatherCoverageError(lat, lon)
        return GridCell(office="TST", x=0, y=int((lat - 40.0) / 0.09))

    def get_forecast(self, cell: GridCell) -> Forecast:
        self.forecasts_asked.append(cell)
        return Forecast(
            updated_at=datetime(2026, 9, 14, tzinfo=UTC),
            elevation_m=float(cell.y),
            periods=[],
        )


class BrokenWeather:
    def get_cell(self, lat: float, lon: float) -> GridCell:
        raise WeatherServiceError("down")

    def get_forecast(self, cell: GridCell) -> Forecast:
        raise AssertionError("never reached")


# get_high_point_index


def test_high_point_is_the_highest_elevation():
    points = due_north(5, lambda i: [100.0, 300.0, 900.0, 400.0, 200.0][i])

    assert get_high_point_index(points) == 2


def test_high_point_tie_goes_to_the_first():
    points = due_north(3, lambda i: [500.0, 100.0, 500.0][i])

    assert get_high_point_index(points) == 0


# choose_forecast_indices


def test_single_point_is_forecast_once():
    assert choose_forecast_indices(due_north(1)) == [0]


def test_short_route_gets_start_end_and_high_point():
    # About 5.5 km, far under the spacing.
    points = due_north(50, lambda i: 1_000.0 if i == 20 else 100.0)

    assert choose_forecast_indices(points) == [0, 20, 49]


def test_high_point_at_an_end_is_not_repeated():
    points = due_north(50, lambda i: float(i))

    assert choose_forecast_indices(points) == [0, 49]


def test_long_route_gets_a_location_every_spacing():
    # 900 hops of about 111 m is 100 km, so five locations 25 km apart.
    points = due_north(901)

    indices = choose_forecast_indices(points, spacing_m=25_000.0)

    assert [round(i * STEP_M / 1000) for i in indices] == [0, 25, 50, 75, 100]


def test_high_point_is_added_between_spaced_locations():
    points = due_north(901, lambda i: 3_000.0 if i == 300 else 100.0)

    indices = choose_forecast_indices(points, spacing_m=25_000.0)

    assert 300 in indices
    assert indices == sorted(indices)
    assert len(indices) == 6


def test_locations_never_exceed_the_ceiling():
    # About 1,000 km, which wants 41 locations at 25 km.
    points = due_north(9_001, lambda i: 3_000.0 if i == 4_321 else 100.0)

    indices = choose_forecast_indices(points, spacing_m=25_000.0, max_locations=10)

    assert len(indices) <= 10
    assert indices[0] == 0
    assert indices[-1] == 9_000
    assert 4_321 in indices


# get_route_forecasts


def test_each_location_carries_its_place_on_the_route():
    points = due_north(50, lambda i: 1_000.0 if i == 20 else 100.0)

    located = get_route_forecasts(points, FakeWeather())

    assert [loc.distance_m for loc in located] == pytest.approx(
        [0.0, 20 * STEP_M, 49 * STEP_M], rel=1e-4
    )
    assert [loc.elevation_m for loc in located] == [100.0, 1_000.0, 100.0]
    assert [loc.is_high_point for loc in located] == [False, True, False]
    assert (located[1].lat, located[1].lon) == points[20][:2]


def test_locations_in_one_cell_share_one_forecast_request():
    # About 5.5 km, all inside one 10 km cell.
    weather = FakeWeather()
    points = due_north(50, lambda i: 1_000.0 if i == 20 else 100.0)

    located = get_route_forecasts(points, weather)

    assert len(weather.cells_asked) == 3
    assert len(weather.forecasts_asked) == 1
    assert all(loc.forecast is located[0].forecast for loc in located)


def test_locations_in_different_cells_get_their_own_forecasts():
    weather = FakeWeather()

    located = get_route_forecasts(due_north(901), weather, spacing_m=25_000.0)

    assert len(weather.forecasts_asked) == len(located) == 5
    assert len({loc.forecast.elevation_m for loc in located if loc.forecast}) == 5


def test_location_outside_coverage_has_no_forecast_and_the_rest_still_do():
    # The first 25 km or so is outside coverage.
    weather = FakeWeather(uncovered_below_lat=40.1)

    located = get_route_forecasts(due_north(901), weather, spacing_m=25_000.0)

    assert located[0].forecast is None
    assert all(loc.forecast is not None for loc in located[1:])


def test_weather_service_failure_propagates():
    with pytest.raises(WeatherServiceError):
        get_route_forecasts(due_north(10), BrokenWeather())
