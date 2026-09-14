"""Client for the National Weather Service API."""

import httpx

BASE_URL = "https://api.weather.gov"
ACCEPT = "application/geo+json"


class NwsClient:
    base_url = BASE_URL
    accept = ACCEPT

    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def _get(self, path: str) -> dict:
        response = self._http.get(
            f"{self.base_url}{path}",
            headers={"Accept": self.accept},
        )
        response.raise_for_status()
        return response.json()

    def get_point(self, lat: float, lon: float) -> dict:
        return self._get(f"/points/{lat},{lon}")

    def get_gridpoint(self, grid_id: str, grid_x: int, grid_y: int) -> dict:
        return self._get(f"/gridpoints/{grid_id}/{grid_x},{grid_y}")

    def get_gridpoint_forecast(self, grid_id: str, grid_x: int, grid_y: int) -> dict:
        return self._get(f"/gridpoints/{grid_id}/{grid_x},{grid_y}/forecast")
