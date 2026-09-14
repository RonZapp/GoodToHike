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
missing, since many devices write zero when they have no reading.

Export the track again with elevation included.

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
