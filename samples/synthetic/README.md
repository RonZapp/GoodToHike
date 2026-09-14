# Synthetic fixtures

Hand-built GPX files, each isolating one decision the ingest pipeline makes.
Real sample tracks live elsewhere; these exist so a behaviour can be
tested without depending on a real file happening to contain the right shape.

| File | Exercises | Expected |
| --- | --- | --- |
| `one-clean-walk.gpx` | Baseline | Accepted, nothing inserted |
| `paused-recording-two-tracks.gpx` | `MAX_TRACK_JOIN_M`, stationary pause | Accepted, 20 m join, GPS drift |
| `late-restart-50m-gap.gpx` | `MAX_TRACK_JOIN_M`, walked before restarting | Accepted, 50 m join, real unrecorded trail |
| `walk-with-annotation-track.gpx` | `MAX_TRACK_JOIN_M`, the failing case | Rejected, tracks do not chain |
| `drive-mid-track.gpx` | `MAX_HOP_M` within a segment | Rejected |
| `drive-between-segments.gpx` | `MAX_HOP_M` across a segment boundary | Rejected |

Each file's `<metadata><desc>` repeats its purpose, so the file explains itself
when opened on its own.

## Why so much rejection

The pipeline prefers turning away a valid file over producing a confidently
wrong trip brief from one it misread. GPX has no type for anything but
waypoints, routes and tracks, so a hazard zone, a closure and the walk itself
all arrive as tracks and nothing in the format tells them apart. Rather than
guess which is the route, the pipeline checks whether the tracks chain
end-to-start and rejects the file when they do not.
