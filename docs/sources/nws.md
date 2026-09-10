From documentation: "The new API will use headers to modify the version and format of the response."

Make sure to send an `Accept` header rather than relying on the default so that our program can be protected if the default changes.

API claims it requires a User-Agent in the request header, but responded even when it wasn't provided. Good to provide anyways, as the actual language says it **may** be blocked without User-Agent, not that it will be blocked without User-Agent.

Specification: https://www.weather.gov/documentation/services-web-api

Timestamps are in UTC

Use /points/{lat},{lon} to get grid and office, those can be used to get the actual forecast.

The response from /points/ itself carries a direct link to the API to get forecasts for that polygon, you don't need to generate it yourself.

Points result is cacheable for 24 hours.
Forecast result is cacheable for up to 1 hour, max-age is sent each time to accurately reflect how much time is left, use latest max-age for cache length decisions.

Freshness can be extracted from updateTime in response body, reuse from cache-control in header.

Gridpoint data is per-cell, not per-point.

Weather and other values are run-length encoded intervals, not regularized intervals.