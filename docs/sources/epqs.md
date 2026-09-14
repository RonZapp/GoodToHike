USGS Elevation Point Query Service (EPQS), reads 3DEP which is bare-earth elevation for the US. No key needed, no rate limit published.

Specification: https://epqs.nationalmap.gov/v1/docs

`GET https://epqs.nationalmap.gov/v1/json?x={lon}&y={lat}&wkid=4326&units=Meters&includeDate=false`

x is longitude and y is latitude, backwards from GPX and from everything else in this codebase. Easy to swap by accident.

wkid=4326 is plain lat/lon on WGS 84, same as GPX.

Picked EPQS over Open-Meteo's elevation endpoint on 2026-09-14.
- README already says 3DEP.
- Open-Meteo is a 90 m global grid. Mount Rainier came back 4,387 m from EPQS and 4,380 m from Open-Meteo, one point doesn't prove anything but trails are exactly where a finer grid should matter. Didn't measure that.
- Open-Meteo takes 100 points per request, EPQS only takes one. Threads mostly make up for it (below).
- EPQS is US only. Tried Paris, no data. A point in Manitoba and one in central Mexico did answer though. If non-US routes ever matter Open-Meteo can be a second fetcher, ElevationFetcher is just a callable so nothing in the fill strategies has to change.

No data comes back as a 200, not an error. Open ocean and Paris both returned 200, content-type still says `application/json`, but the body is plain text. Same ocean point, two requests in a row, two different messages:
- `Invalid or missing input parameters.`
- `Call failed.  [Failed cloud operation: Open, Path: /vsimem/_000000B1.aux.xml]`

So don't match on the message. Body isn't JSON = no data. Check before calling `.json()`.

Garbage coordinates (`x=abc`) also get the 200 text body. Only real HTTP error seen was leaving a parameter out, `400` `{"errorMessage" : "[BadRequest] missing parameters"}`.

Elevation comes back as a string in meters, `"value":"4387.059082031"`. Ask for `units=Feet` and it's a number instead. float() handles both.

0 and slightly negative are real values, not missing. Washington coast gave `0.000000000`, Seattle waterfront gave `-0.356616676`. Careful, our GPX parser treats 0 as missing, the elevation service shouldn't.

Precision is fine. Sent `-121.33876000000001` (17 digits) and it answered, unlike the USGS water services bbox which 400s past ~6 decimals. No rounding needed.

Resolution isn't one grid, it depends on where you ask. The `resolution` field came back 1 in Seattle, Hawaii and Puerto Rico, 5 near Anchorage, 0.0000309 on Rainier and 0.0000926 in a lot of other places. The small ones have to be degrees (~3 m and ~10 m) and the others meters, so the field doesn't have consistent units. Not reading it.

`includeDate=true` adds `attributes.AcquisitionDate`, got `0/4/2008` which isn't a real date. Not using it.

Speed, tested 2026-09-14:
- Single request 0.25 to 1 s normally.
- 302 Timberline points at 16 threads, all JSON, median 0.24 s, p95 1.46 s, max 3.31 s. None of them got the text body so it isn't a random transient failure on real land.
- 40 requests took 13.3 s one at a time, 1.2 s with 8 threads, 0.6 s with 16. No 429s at 16.
- Client uses 8 threads. Tried `Executor.map` buffersize 8, 16, 32 and unbounded on 240 points, 5.0 to 7.4 s, just network noise. Kept buffersize = workers since it stops a failed batch soonest.

It gets slow under load. Same day, a few hours later, nothing changed on our end, Rainier went from 0.4 s to 9.9 s. 40 requests at 8 threads were median 2.0 s, p90 4.9 s, max 5.1 s. One Lost Coast point timed out at 5 s three times in a row and the whole HybridFill failed with it.

The shared http client timeout is 5 s which is right in that tail, so EpqsClient passes its own per-request timeout, 20 s (roughly double the worst request seen). Retries didn't save it on their own, the slowdown lasted way longer than the 0.5 s / 1 s backoff. With 20 s the same 205 lookups finished, 79 to 129 s under load vs under 10 s when it's quiet.

Retrying on timeouts, dropped connections, 429 and 5xx, 3 tries. Not retrying the 200 text body (no data won't change) or 4xx (our request is wrong).

LookUpEveryPoint is expensive. Hoh River = 1,224 lookups, 35 s quiet, about 29 ms a point at 8 threads. Timberline has 72k points, that's ~35 min, can't do that inside an upload request.

Accuracy.
- Hoh River's recorded elevation matches EPQS at every point to 0.2 m median (p95 1.75 m, all rounded to 1 decimal). It's 3DEP. Comparing against it is 3DEP vs 3DEP, proves nothing.
- Enchanted Valley is off from 3DEP by 19.9 m median, came from something else.
- Lost Coast's elevation_added copy has beach points at 72 to 94 m where 3DEP says 1 to 3 m.

Without ground truth, what we can check is how far our fill strategies drift from EPQS itself. That's what the network test does.
- Lost Coast from no_elevation/ is the only real export with no elevation at all. Main track is 1,136 points, HybridFill did 205 lookups. Asked EPQS directly at 40 of the 1,061 interpolated points, median 0.34 m off, p95 5.3 m, max 6.25 m, same all three runs. Mostly beach and gentle bluffs though, steep trails could be worse, haven't checked.
- Hoh River filled both ways: HybridFill (142 lookups) vs LookUpEveryPoint (1,224), median 0.9 m apart, p95 8.8 m, max 26.5 m. Looks small per point but gain (5 m threshold) was 1,484 m vs 1,682 m, HybridFill is 12% low. Interpolating across 200 m flattens the small ups and downs that gain adds up. Think about this when the profile endpoint picks a strategy.

None of this says whether 3DEP matches the actual ground, only that we're consistent with it.
