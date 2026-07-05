# API Reference

## Health

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/healthz` | Liveness probe — returns 200 if the process is alive |
| GET | `/readyz` | Readiness probe — returns 200 if the service is ready to accept traffic |

## Endpoints

### Progress

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/v1/progress/summary` | Current user's daily goal, streaks, 45-day activity heatmap, and next milestone |
| GET | `/api/v1/progress/packs/{slug}` | Current user's per-activity progress for a pack |
| POST | `/api/v1/progress/completions` | Record an activity completion for the current user |
| DELETE | `/api/v1/progress/packs/{slug}` | Reset current user's progress for a pack |

`GET /api/v1/progress/summary` accepts optional
`tz_offset_minutes` (`-900` to `900`), matching JavaScript
`new Date().getTimezoneOffset()`, so streaks and heatmap buckets use the
learner's local day.
