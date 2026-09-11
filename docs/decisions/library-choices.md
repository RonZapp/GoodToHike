# Library choices

## HTTP Client

**Choice:** httpx

**Reason:** Sync and async clients with one API (Requests only has sync clients), upstream clients work unchanged if handlers go async. Built in mock for network-free testing.

## Web framework

**Choice:** FastAPI

**Reason:** Generates the OpenAPI doc from type hints. Request and response validation come from type hints as well. FastAPI's test client is Httpx-based so one HTTP idiom covers tests for both the server and upstream clients.

## Package management

**Choice:** uv

**Reason:** Lockfile for reproducible installs in Docker and CI, one tool for venv, dependencies, and running scripts.

## Tests

**Choice:** pytest

**Reason:** Python community standard.

## Database

**Choice:** SQLite via SQLAlchemy

**Reason:** Long term intention is to use MySQL, SQLite is faster to get running and utilizing it through SQLAlchemy allows us to switch to MySQL later.

## GPX parsing

**Choice:** gpxpy

**Reason:** Handles GPX 1.0 and 1.1, XML namespaces, and the track segment/point nesting. Exposes tracks and routes as separate collections, which lets us reject a route-only export with a clear error instead of silently producing a bad elevation profile.

## ASGI server

**Choice:** uvicorn

**Reason:** FastAPI is a framework and ships no server, but Uvicorn is what FastAPI's own docs assume.
