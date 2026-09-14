# GoodToHike

It's easy to find hiking trails online. But are they actually hikeable *right
now*?

GoodToHike is an API that answers whether your trail will try to kill you. (And 
more benign things like road and campground closures.)

Give it a route and it pulls together current conditions from public data
sources — streamflow, snowpack, weather, closures, fire activity — and returns a
trip brief you can read before you lose signal.

## Why

Finding a trail on a platform like AllTrails is easy. Knowing its current state
is not.

Is the creek at mile 14 fordable? Is that spring we are depending on to refill
our water still running? How far down does the snow go on the north side of the
pass? Is the road to the trailhead open?

The underlying data mostly exists. USGS runs thousands of real-time stream
gauges. NRCS runs automated snow telemetry stations. The Park Service publishes
closures. It is all public and free. It is just scattered across a dozen
agencies, in a dozen formats, indexed by station or park rather than by the
route you are actually walking.

GoodToHike does that join so you don't have to. It maps a route's geometry
against the sensors near it and produces one document.

## Data sources

All public. Most require no authentication.

✅ implemented · 🟨 partly implemented · ⬜ planned

| Status | Source | Provides | Auth |
| :---: | --- | --- | --- |
| ⬜ | OpenStreetMap (Overpass) | Trail geometry, water features, surface tags | None |
| ⬜ | USGS Water Services | Real-time streamflow at gauge stations | None |
| ⬜ | NRCS SNOTEL | Snow depth and water equivalent | None |
| ✅ | National Weather Service | Gridded point forecasts | None |
| ⬜ | Open-Meteo | Historical precipitation and temperature | None |
| ✅ | USGS 3DEP | Elevation for profile computation | None |
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
| ⬜ | `GET` | `/v1/water-sources/{id}/reports` | Report history for a water source |

Writes:

| Status | Method | Path | Does |
| :---: | --- | --- | --- |
| ✅ | `POST` | `/v1/routes` | Ingest a GPX file or OSM relation. GPX only so far. |
| ⬜ | `POST` | `/v1/routes/{id}/plans` | Create a plan from dates and pace |
| ⬜ | `PATCH` | `/v1/plans/{id}` | Change a plan's dates or pace |
| ⬜ | `POST` | `/v1/water-sources/{id}/reports` | Field report: flowing, trickle, dry |
| ⬜ | `POST` | `/v1/trail-reports` | Snow depth, blowdown, or ford at a location |

## Getting a route in

GoodToHike accepts a route two ways: an OpenStreetMap relation ID, or an
uploaded GPX file.

### From OpenStreetMap

If the trail is a named route in OSM, pass its relation ID directly. Search for
the trail on [openstreetmap.org](https://www.openstreetmap.org), open the
relation, and take the number from the URL.

### From AllTrails

Most people have a route in mind on AllTrails already. Exporting it is
straightforward but well hidden:

1. Open the trail page on **alltrails.com** in a browser, or the trail in the
   mobile app.
2. Click the **three-dot menu** in the top right of the trail page.
3. Choose **Export route file**. Older versions of the interface label this
   **Download route** — same thing.
4. In the format list, choose **GPX Track**.

   This part matters. AllTrails offers both *GPX Track* and *GPX Route*. A track
   is a dense series of recorded points that follows the trail's actual shape. A
   route is a sparse set of waypoints with straight lines between them. Only a
   track has enough resolution to compute a useful elevation profile or to find
   the exact points where the trail crosses water. If you pick the wrong one,
   GoodToHike will accept the file but the output will be poor.

5. Save the `.gpx` file, then upload it:

```
   curl -X POST http://localhost:8000/v1/routes \
     -F "file=@lawson-peak.gpx" \
     -F "name=Lawson Peak"
```

GPX from Gaia GPS, CalTopo, Garmin Connect, Strava, and Komoot works the same
way — any GPX track file is fine.

## Accuracy and limits

Conditions are inferred from the nearest available sensors, which may be miles
away and at a different elevation than the point they are describing. Snow line
estimates interpolate between SNOTEL stations. Streamflow at a crossing is
approximated from the nearest gauge on the same waterway, which may be well
upstream or downstream.

This is planning information, not a safety guarantee. It is meant to tell you
which questions to ask before a trip, not to tell you a crossing is safe. Trail
conditions in the backcountry change faster than any sensor network reports
them.

## Scope

The initial focus is water availability, snow, and closures for trips in the US.
This is a personal project for learning to use the involved technologies, scope
may grow as learning to cotinues.

## Stack

Python 3.14, FastAPI, MySQL, Docker Compose.

## Running

```
cp .env.example .env
docker compose up
```

## Implementation goals

- `/v1/` prefix from the start for versioning

## Status

Early. Schema design and route ingest in progress. Nothing here works yet.

## Roadmap

- [ ] Route ingest: GPX parsing and OSM relation import
- [ ] Elevation profile from 3DEP sampling
- [ ] Water feature extraction from route geometry
- [ ] USGS gauge and SNOTEL station matching
- [ ] Conditions synthesis endpoint
- [ ] Trip plan generation
- [ ] Field reports and confidence scoring
- [ ] Test suite with mocked upstream responses
- [ ] OpenAPI document and CI

## License

MIT
