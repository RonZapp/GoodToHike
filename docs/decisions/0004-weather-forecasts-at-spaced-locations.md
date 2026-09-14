# 4. Weather forecasts at spaced locations along a route

Date: 2026-09-14

Status: Accepted

## Context

The conditions endpoint needs a weather forecast for a route. The National Weather Service forecasts per grid cell, about 2.5 km across, and finding a location's cell takes a `/points` request before a `/forecast` request for that cell. Timberline is 68 km long and crosses about 28 cells.

Measured 2026-09-14, each `/points` request took 0.2 to 0.4 s and each `/forecast` request about 0.8 s. Asking for every cell along Timberline would take over ten seconds per request, and put that load on a free service with unpublished rate limits.

The service offers two forecast shapes. `/forecast` returns 12-hour periods with a temperature, wind, chance of precipitation and a written summary. `/gridpoints/{cell}` returns the raw values behind them as run-length encoded ISO 8601 intervals, which the client would have to decode.

## Decision

Forecast a route at points about 25 km apart along the ground, always including the start and the end, plus the route's highest point. A route gets at most 10 locations, and a longer one gets wider spacing instead.

Locations that fall in the same grid cell share one `/forecast` request.

Use `/forecast` with `units=si`, and pass its periods through with their own labels and local offsets.

A location outside the service's coverage gets a `forecast` of `null`, and the rest of the route still gets forecasts. A failure of the service itself fails the request with a `502` problem. Nothing is retried or cached yet.

## Alternatives considered

1. Every grid cell along the route. The most complete, but request time and upstream load grow with route length, and neighbouring cells rarely differ in what a hiker would plan around.

2. Only the start, the end and the highest point. Bounded and cheap, but a multi-day route could go a hundred kilometres without a forecast.

3. Spaced points without the highest point. Weather over a day's walk changes more with elevation than with distance, and a pass or summit between two spaced points would be missed.

4. `/gridpoints` raw data. Hourly values and more fields, at the cost of decoding intervals ourselves. Not needed to show a forecast, and still available if hourly detail is wanted later.

5. Fail the whole request when any location is outside coverage. Simpler, but a route that crosses into Canada would get nothing at all.

## Consequences

A request makes at most 20 upstream calls, one after another, and a typical route of three or four locations took about 2 s. A long route near the location ceiling could take several seconds. Running the lookups concurrently, as the elevation client does, is the first fix if that becomes a problem.

A single failed upstream request fails the whole response. The service is known to return occasional errors, so retries are likely to be needed. They belong in the shared HTTP client or a service layer rather than in each client.

`/points` answers are cacheable for 24 hours and forecasts for up to an hour, according to the service's own `Cache-Control`. Neither is cached yet, so every request repeats the full set of calls.

A forecast is for the grid cell's elevation, not the route point's. Both are returned so a client can see the difference.

`wind_speed` stays the service's own text, such as "7 to 17 km/h", rather than being parsed into numbers.
