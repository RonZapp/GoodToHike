From documentation: "The new API will use headers to modify the version and format of the response."

Make sure to send an `Accept` header rather than relying on the default so that our program can be protected if the default changes.

Documentation says versioning will be done through headers but never says which header, parameter, or values. 
- Tested `Accept: application/geo+json; version=1`, `version=999`, and `version=banana` on 2026-09-10, all returned 200 with the same content-type and byte-identical bodies to a request with no version.
- The server does parse `Accept` (asking for `application/ld+json` changes the response), so it isn't the whole header being ignored, the version parameter specifically is ignored. Not sending it.

API claims it requires a User-Agent in the request header, but responded even when it wasn't provided. Good to provide anyways, as the actual language says it **may** be blocked without User-Agent, not that it will be blocked without User-Agent.

Specification: https://www.weather.gov/documentation/services-web-api

https://api.weather.gov/openapi.json is authoritative, the docs page is only a rendering. Grep the spec when they disagree.

Gridpoint `updateTime` and `generatedAt` are UTC. Forecast period `startTime` and `endTime` carry the local offset (-07:00 on Mount Hood), and so does astronomicalData in /points/.

Use /points/{lat},{lon} to get grid and office, those can be used to get the actual forecast.

Spec calls the office wfo, response body calls it gridId. Same value.

The response from /points/ itself carries a direct link to the API to get forecasts for that polygon, you don't need to generate it yourself.

Points result is cacheable for 24 hours.
Forecast result is cacheable for up to 1 hour, max-age is sent each time to accurately reflect how much time is left, use latest max-age for cache length decisions.

Freshness can be extracted from updateTime in response body, reuse from cache-control in header.

Weak ETag is sent, If-None-Match works.

Gridpoint data is per-cell, not per-point.

Weather and other values are run-length encoded intervals, not regularized intervals.

Rate limits are not published. Retry after 5s on 429/503.

/points/ accepts at most four decimal places. Tested 2026-09-14: `/points/45.331289,-121.710876`, a Timberline Trail point exactly as its GPX file stores it, answered `301` with `Location: /points/45.3313,-121.7109`. httpx does not follow redirects by default, so unrounded coordinates fail outright. Rounding to four places is about 11 m, far inside a 2.5 km grid cell.

A location with no forecast, such as open ocean (40.0, -130.0) or London, answers `404` with `application/problem+json`, type `https://api.weather.gov/problems/InvalidPoint`, title "Data Unavailable For Requested Point". Coastal points on the Lost Coast Trail are covered.

`/forecast` takes `units=si`: temperature in Celsius (`temperatureUnit: "C"`, still a whole number) and wind as a string such as "7 to 17 km/h". The default is US units. `probabilityOfPrecipitation.value` is a percentage and can be null.

A forecast body's `elevation` is the grid cell's, which can differ from the route point's by a few hundred metres, so it is passed through with each forecast.

Timing on 2026-09-14: /points/ 0.2 to 0.4 s, /forecast about 0.8 s, and a Timberline route's four forecast locations 2.1 s one after another. The same requests repeated straight away took 0.25 s in total.

