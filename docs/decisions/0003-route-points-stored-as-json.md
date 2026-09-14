# 3. Route points stored as a JSON column

Date: 2026-09-14

Status: Accepted

## Context

A stored route needs its points kept somewhere. One of our samples, Timberline, has 72,339 points. Every planned endpoint that uses points reads the whole route in walked order, or something derived from all of it, such as the forecast grid cells it passes through. No endpoint reads part of a route, filters points by value, or changes a point after upload.

Measured on the Timberline sample with the standard library's `sqlite3` (Python 3.14.7, SQLite 3.53.4), median of five runs against a fresh file database each run. Rows were inserted with `executemany` in one transaction into a table keyed on `(route_id, seq)`. JSON timings include `json.dumps` and `json.loads`.

| Storage | Write | Read |
| --- | --- | --- |
| One row per point | 42.4 ms | 18.3 ms |
| One JSON column | 35.6 ms | 11.2 ms |

The JSON for the route is 2.4 MB. An in-memory database gave the same results to within about 3 ms.

Both are small next to the roughly 640 ms it takes to parse the same file, so storage cost does not decide between them.

## Decision

Store a route's points as a single JSON column on the routes table. Values that are shown without the points, such as name, source, point count and length, are ordinary columns, so looking up a route does not decode its points.

The choice rests on how the data is used rather than on speed. A route is written once and always read whole, which is what a single value is for.

## Alternatives considered

1. One row per point. Measured at about the same cost, but adds a second table, an ordering column and a sort on every read, all to support partial reads and per-point queries that nothing makes.

2. Packed binary, such as three 64-bit floats per point. About 1.7 MB instead of 2.4 MB, but unreadable when inspecting the database, and a missing elevation needs a sentinel value such as NaN. Not worth it until storage size is a measured problem.

## Consequences

The measurements are raw `sqlite3` cost. Through the SQLAlchemy ORM, creating one object per point would add cost to the rows option that was not measured here.

SQLAlchemy does not detect in-place changes inside a JSON column. That is harmless while routes never change after upload, and needs revisiting if they ever do.

A future query on individual points, such as finding every point above an elevation, would need a migration to rows or a database with JSON or spatial querying.

Inferred ranges from gap filling are not stored. Once elevation is filled, a straight-lined point cannot be told apart from a recorded one, so routes stored before a column for them is added will never have them.

JSON columns exist in MySQL as well, so the planned move away from SQLite is unaffected.

Reads in these measurements ran straight after writes, while the data was still in the operating system's cache. A cold read would be slower for both options.
