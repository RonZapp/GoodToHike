# GoodToHike

[![CI](https://github.com/RonZapp/GoodToHike/actions/workflows/ci.yml/badge.svg)](https://github.com/RonZapp/GoodToHike/actions/workflows/ci.yml)

It's easy to find hiking trails online. But are they actually hikeable *right
now*?

GoodToHike is an API that answers whether your trail will try to kill you. (And 
more benign things like road and campground closures.)

Give it a route and it pulls together current conditions from public data
sources — streamflow, snowpack, weather, closures, fire activity — and returns a
trip brief you can read before you lose signal.

## Status

Early, with the core path working end to end. Upload a GPX track and GoodToHike
checks that it is one continuous walk, straight-lines gaps in the recording,
fills in missing elevation from USGS 3DEP, and stores it. From there it serves
the route's elevation profile and a weather forecast along it. It also takes
field reports on whether a water source is running.

Water sources, snow, closures and trip plans are next.

## Data sources

All public. Most require no authentication.

✅ implemented · ⬜ planned

| Status | Source | Provides | Auth |
| :---: | --- | --- | --- |
| ⬜ | OpenStreetMap (Overpass) | Trail geometry, water features, surface tags | None |
| ⬜ | USGS Water Services | Real-time streamflow at gauge stations | None |
| ⬜ | NRCS SNOTEL | Snow depth and water equivalent | None |
| ✅ | National Weather Service | 12-hour forecasts per grid cell | None |
| ⬜ | Open-Meteo | Historical precipitation and temperature | None |
| ✅ | USGS 3DEP | Elevation for tracks that lack it | None |
| ⬜ | National Park Service | Park alerts and closures | Free key |
| ⬜ | NASA FIRMS | Active fire detections | Free key |

## Endpoints

✅ implemented · ⬜ planned

Reads:

| Status | Method | Path | Returns |
| :---: | --- | --- | --- |
| ✅ | `GET` | `/v1/routes/{id}` | Route metadata |
| ✅ | `GET` | `/v1/routes/{id}/profile` | Elevation profile, grade, distance |
| ⬜ | `GET` | `/v1/routes/{id}/water` | Water sources with current reliability |
| ✅ | `GET` | `/v1/routes/{id}/conditions` | Snow, streamflow, weather, closures, fire. Weather only so far. |
| ⬜ | `GET` | `/v1/routes/{id}/trail-reports` | Trail reports near a route |
| ⬜ | `GET` | `/v1/plans/{id}` | A plan, with a day-by-day brief built from current conditions |
| ✅ | `GET` | `/v1/water-sources/{id}/reports` | Report history for a water source |
| ✅ | `GET` | `/v1/water-sources/{id}/reports/{report_id}` | One water source report |

Writes:

| Status | Method | Path | Does |
| :---: | --- | --- | --- |
| ✅ | `POST` | `/v1/routes` | Ingest a GPX file or OSM relation. GPX only so far. |
| ⬜ | `POST` | `/v1/routes/{id}/plans` | Create a plan from dates and pace |
| ⬜ | `PATCH` | `/v1/plans/{id}` | Change a plan's dates or pace |
| ✅ | `POST` | `/v1/water-sources/{id}/reports` | Field report: flowing, trickle, dry |
| ⬜ | `POST` | `/v1/trail-reports` | Snow depth, blowdown, or ford at a location |

## Getting a route in

GoodToHike accepts a route as an uploaded GPX track file.

### From AllTrails

Most people have a route in mind on AllTrails already. Exporting it is
straightforward but well hidden:

1. Open the trail page on **alltrails.com** in a browser, or the trail in the
   mobile app.
2. Click the **three-dot menu** in the top right of the trail page.
3. Choose **Export route file**. Older versions of the interface label this
   **Download route** — same thing.
4. In the format list, choose **GPX Track**.

   AllTrails offers both *GPX Track* and *GPX Route*. A track
   is a dense series of recorded points that follows the trail's actual shape. A
   route is a sparse set of waypoints with straight lines between them. Only a
   track has enough resolution to compute a useful elevation profile or to find
   the exact points where the trail crosses water. If you pick the wrong one,
   GoodToHike rejects the file with a message asking you to export it again as a
   track.

5. Save the `.gpx` file, then upload it. This example uses a sample track from
   this repository:

   ```sh
   curl -X POST http://localhost:8000/v1/routes \
     -F "file=@samples/hikingguy/elevation_added/enchanted-valley.gpx" \
     -F "name=Enchanted Valley"
   ```

   The `name` field is optional. Without it, the route takes the name recorded
   in the file. The response is `201 Created`, with the new route's URL in the
   `Location` header:

   ```json
   {
     "id": 1,
     "name": "Enchanted Valley",
     "source": "gpx",
     "point_count": 780,
     "length_m": 20610.932016594114,
     "created_at": "2026-09-14T14:49:59.682476Z"
   }
   ```

GPX from Gaia GPS, CalTopo, Garmin Connect, Strava, and Komoot works the same
way — any GPX track file is fine.

## Accuracy and limits

Conditions come from the nearest available data, which may describe a different
place and elevation than the point on the trail you care about. Today that
means:

- Weather forecasts cover a National Weather Service grid cell about 2.5 km
  across, and are made for the cell's elevation rather than the trail's. A
  route is forecast about every 25 km and at its highest point, so conditions
  between those places are not shown.
- Elevation missing from an uploaded track is looked up from USGS 3DEP or
  interpolated between known points, so the profile is only as accurate as that
  data.
- Total climb and descent ignore changes smaller than 10 m, so that GPS noise is
  not counted as climbing.
- An upload missing elevation waits for those lookups, which can take tens of
  seconds.

This is planning information, not a safety guarantee. It is meant to tell you
which questions to ask before a trip, not to tell you a crossing is safe. Trail
conditions in the backcountry change faster than any sensor network reports
them.

## Scope

The initial focus is water availability, snow, and closures for trips in the US.
This is a personal project for learning to use the involved technologies, scope
may grow as learning to cotinues.

## Stack

Python 3.14, FastAPI, SQLAlchemy on SQLite, httpx2, gpxpy and uv, checked in CI
with pytest, ruff and pyright. The reasoning behind each choice is in
[docs/decisions/library-choices.md](docs/decisions/library-choices.md).

## Running

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run uvicorn goodtohike.api.app:app --reload
```

The API serves on `http://localhost:8000`, with interactive OpenAPI docs at
`http://localhost:8000/docs`.

To run the tests:

```sh
uv run pytest              # offline suite
uv run pytest -m network   # calls the real upstream services
```

## Configuration

Set with environment variables.

| Variable | Default | Controls |
| --- | --- | --- |
| `GOODTOHIKE_DATABASE_URL` | `sqlite:///goodtohike.db` | Where routes and reports are stored, as a SQLAlchemy database URL |
| `GOODTOHIKE_ELEVATION_FILL` | `hybrid` | How missing elevation is filled |

`GOODTOHIKE_ELEVATION_FILL` accepts one of these, and any other value stops the
app from starting:

| Value | Behaviour |
| --- | --- |
| `hybrid` | Interpolates short gaps and looks long ones up from USGS 3DEP. A track that carries its own elevation makes no lookups. |
| `interpolate` | Uses only the track's own elevation and makes no requests. A track with no elevation at all is rejected. |
| `lookup-gaps` | Looks up every gap in elevation, however short. |
| `lookup-every-point` | Replaces all elevation with one lookup per point. Practical only for short tracks. |

## API conventions

✅ implemented · 🟨 partly implemented · ⬜ planned

| Status | Convention |
| :---: | --- |
| ✅ | `/v1/` prefix from the start |
| ✅ | A consistent error body on every endpoint, following RFC 9457 problem details. Every type is documented in [docs/problems.md](docs/problems.md). |
| ✅ | `201` with a `Location` header on creation |
| ✅ | ISO 8601 timestamps with explicit offsets, UTC internally |
| 🟨 | An OpenAPI document with runnable examples. Generated at `/docs`, without examples yet. |
| ⬜ | Cursor-based pagination rather than offset |
| ⬜ | `429` responses that include `Retry-After`, with documented limits |
| ⬜ | `ETag` and `Cache-Control` on computed results, since profiles and conditions are expensive to derive and cheap to cache |
| ⬜ | Idempotency keys on writes, so a retried request does not duplicate a report |

## Documentation

- [docs/decisions/](docs/decisions/): architecture decision records, with the
  measurements behind each choice.
- [docs/sources/](docs/sources/): how each upstream API actually behaves,
  including quirks its own documentation leaves out.
- [docs/problems.md](docs/problems.md): every error type the API returns, and
  how to fix the request.

## License

MIT
