# 2. Elevation filling as swappable strategies

Date: 2026-09-12

Status: Accepted

## Context

`build_route` decided on its own how to fill missing elevation: interpolate when the longest gap was under `MAX_ALT_INTERPOLATION_M`, otherwise look it up through an `ElevationFetcher`, raising `ElevationRequired` if none was passed. Only one policy could exist, and all of its settings (`fetch`, `spacing_m`, the threshold) sat on `build_route`'s signature.

We want to choose between policies (interpolation only, interpolation for small gaps with lookups for large ones, lookups for everything) and, separately, between elevation services. `ElevationFetcher` already made the service swappable; the policy was hard-coded. Tracks that already carry elevation need a policy too, since GPS elevation is noisy and a lookup-everything policy may want to replace it.

## Decision

Elevation filling is an `ElevationFiller` Protocol in `elevation.py` with a single method, `fill(points) -> list[Point]`, which guarantees one output point per input point, in the same order, with elevation always present.

Each policy is a frozen dataclass whose fields are its settings. A policy that needs a service takes an `ElevationFetcher` when it is constructed, so policies and services combine rather than multiply.

`build_route(track, filler)` runs the geometry checks and gap filling, then hands every point to the filler. Tracks with complete elevation are not skipped; each strategy decides whether to keep or replace what it is given. `InterpolateOnly` is the first strategy, and keeps recorded elevations unchanged.

The API layer chooses the strategy. It is built once at startup from a setting, stored on the app, and handed to endpoints with `Depends`, so tests can swap it with `dependency_overrides`.

## Alternatives considered

1. Keep the branch in `build_route` behind a `needs_elevation_lookup` predicate. Simplest for one policy, but each new policy grows the branch and the signature, and needs `ElevationRequired` to cover a lookup requested with no fetcher.

2. An abstract base class with `@abstractmethod`. Enforces the method at runtime, but forces inheritance on strategies that share no code, including test fakes.

3. Plain functions configured with `functools.partial`, matching `ElevationFetcher`. Lightest, but settings are hidden inside the partial when debugging.

4. One class per policy and service combination. The class count multiplies with each one added.

5. Skip tracks with complete elevation in `build_route` using `has_full_elevation()`. Saves a pass over the track, but no strategy could ever replace recorded GPS elevation.

## Consequences

`ingest.py` no longer owns elevation settings. `MAX_ALT_INTERPOLATION_M` and the lookup spacing become settings on the strategies that use them, which also removes the second `DEFAULT_SPACING_M` that disagreed with `elevation.py`. `ElevationRequired` is gone, since a strategy that needs a fetcher cannot be constructed without one.

Conformance to the Protocol is only checked by a type checker; a strategy with the wrong method fails only when called. This relies on pyright in standard mode, configured in `pyproject.toml`, and enforced in CI.

Tracks with complete elevation now take an extra pass over the track in `InterpolateOnly`, which is counted in the `InterpolateOnly` row of decision 1. On the 72,339-point Timberline sample, median of five runs, building the route took 42 ms without elevation work and 74 ms with `InterpolateOnly`, against 666 ms to parse. Parsing is still the dominant cost, so decision 1 still holds.

Each new strategy must uphold the `fill` guarantee itself, so each needs its own tests.
