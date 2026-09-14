# 1. Route distance computed per-stage

Date: 2026-09-12

Status: Accepted

## Context

Distance along the route is calculated across the entire track multiple times during the ingestion pipeline. `check_continuity` and `fill_gaps` each compute the distance between every consecutive pair of points, and every elevation filler except `LookUpEveryPoint` rebuilds cumulative distance over the whole track once.

Measured on the 72,339-point Timberline sample, median of five runs, with a stand-in fetcher that answers instantly. Passes and timings are the same whether or not the track carries elevation:

| Filler | Passes over the track | Build route | Parse GPX |
| --- | --- | --- | --- |
| `InterpolateOnly`, `HybridFill`, `LookUpGaps` | 3 | 70–72 ms | 638 ms |
| `LookUpEveryPoint` | 2 | 48 ms | 638 ms |

Even with 3 separate passes, parsing the GPX file immediately beforehand takes about 9x as long.

## Decision

Leaving it as-is after evaluating the performance impact as minimal compared to the parsing that happens immediately before it. At 72 ms in the worst case, it is also acceptable on its own for a single upload.

This decision should be revisited when the profile endpoint is built, since it will need distance at every point as well, or when routes start being built from points that were not just parsed and thus no longer have their performance bottlenecked on parsing.

## Alternatives considered

1. Compute once and pass around from function to function as an argument. Would still have to be computed twice due to current encapsulation (before and after `fill_gaps`), and introduces the challenge of managing a calculated set of distances that may no longer be accurate after various functions alter the underlying data in the track.

2. Add distances as a `functools.cached_property` on our data classes. An attribute on the data class allows the information to stay attached to the object it is describing, and implementing that attribute as a cached property would allow lazy calculation. However, it introduces a weakness to mutation if the points in a track are altered in place without the cached distances being recalculated. Not chosen now because the measured cost does not justify the change, but it is the likely direction once the profile endpoint needs distances too.

## Consequences

It may be tougher to address this later after other components are built that rely on our current design.

This decision leans on GPX parsing being the slower step that happens right before route building. If routes are built from points that were not just parsed, such as rebuilding stored routes after tuning the thresholds in `gaps.py`, that comparison no longer applies and route building becomes the main cost. Rebuilding many stored routes at once is where this would add up.

Cost also grows with the number of points in a track, so a track much larger than our largest sample could make this a noticeable part of upload time.
