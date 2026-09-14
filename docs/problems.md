# Problem types

Every error response from the API uses the problem details format from
[RFC 9457](https://www.rfc-editor.org/rfc/rfc9457), served as
`application/problem+json`. Each body carries the same five fields:

| Field | Meaning |
| --- | --- |
| `type` | Which problem this is. A link to its section below, or `about:blank`. |
| `title` | A short summary of the problem type. The same every time it occurs. |
| `status` | The HTTP status code, repeated so the body stands on its own. |
| `detail` | What went wrong with this particular request, and how to fix it. |
| `instance` | The path of the request that failed. |

Clients should branch on `type` and show `detail` to people. Titles and
details are written for humans and may be reworded.

```json
{
  "type": "https://github.com/RonZapp/GoodToHike/blob/main/docs/problems.md#track-gap",
  "title": "Track is not one continuous walk",
  "status": 422,
  "detail": "This track jumps 54.1 km between points 23 and 24. That is too far to be one continuous walk, so the file may hold several separate outings, or a drive between trailheads. Split it into one file per walk and upload them separately.",
  "instance": "/v1/routes"
}
```

## track-gap

**Status:** 422. **Title:** Track is not one continuous walk.

The uploaded track cannot be a single walk. Either two consecutive points are
more than 5 km apart, or the file holds several tracks that do not start
within 100 m of where the previous one ended.

Both usually mean the file holds more than the walk itself, such as a drive
between trailheads, a second outing, or hazard and closure outlines stored as
extra tracks. Upload a file containing only the track that was walked.

## no-elevation

**Status:** 422. **Title:** Track has no elevation.

No point in the track carries an elevation, and the server is filling
elevation from the track's own data. Elevations of exactly zero count as
missing, since many devices write zero when they have no reading. So do
elevations that are not numbers at all, such as `NaN` or `inf`.

Export the track again with elevation included.

## outside-elevation-coverage

**Status:** 422. **Title:** Track is outside elevation coverage.

The track needed elevation looked up, and the elevation service has no data
for at least one of its points. The service covers the United States, so the
usual cause is a track elsewhere, or a point in open water. The `detail` names
the first point found without data.

Upload a track that carries its own elevation.

## elevation-service-failed

**Status:** 502. **Title:** Elevation service failed.

The track needed elevation looked up, and the upstream elevation service did
not give a usable answer: it timed out, kept failing after retries, or sent a
response the server could not read. Nothing is wrong with the upload.

Try again later. The `detail` is deliberately generic, and the error itself is
logged on the server.

## weather-service-failed

**Status:** 502. **Title:** Weather service failed.

Conditions for the route needed forecasts, and the upstream weather service
did not give a usable answer: it failed, timed out, or sent a response the
server could not read. Nothing is wrong with the route.

Try again later. The `detail` is deliberately generic, and the error itself is
logged on the server.

A route that runs outside the weather service's coverage is not this problem.
Those locations come back with a `forecast` of `null` instead.

## invalid-gpx

**Status:** 422. **Title:** The GPX could not be processed.

The uploaded file cannot be turned into a track. The `detail` says which of
these applies:

| Cause | Fix |
| --- | --- |
| The file is not UTF-8 text. | Upload the GPX file itself, not an archive or another format. |
| The file is not valid GPX. | Check that the export finished and the file is complete. |
| The file holds a GPX route, not a GPX track. | Re-export and choose "GPX Track". |
| The file holds no track points. | Export a track that was actually recorded. |
| A point's coordinates are not a place on Earth. | The `detail` names the first such point. Latitude must be between -90 and 90, and longitude between -180 and 180. Export the track again, or correct that point. |

## invalid-request

**Status:** 422. **Title:** Request is not valid.

The request itself does not match what the endpoint accepts, before any file
is read. The usual cause is a missing field, such as an upload with no `file`
part. The `detail` lists every problem as `location: message`, separated by
semicolons:

```
body.file: Field required
```

## about:blank

Some errors mean no more than their HTTP status code. Those use the type
`about:blank`, and their title is the status code's standard phrase.

| Status | When |
| --- | --- |
| 404 Not Found | No endpoint exists at that path. |
| 405 Method Not Allowed | The path exists but not for that method. The `Allow` header lists the methods it supports. |
| 500 Internal Server Error | An unexpected error on the server. The `detail` is deliberately generic, and the error itself is logged on the server. |
