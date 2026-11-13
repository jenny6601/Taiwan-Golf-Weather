# V32.1 Deployment — Jiaoxi Observation Pilot

## Current scope

- Pilot course: Jiaoxi Golf Course (JIAOXI)
- Course coordinates: 24.8389, 121.7389
- Initial observation datasets:
  - CWA O-A0001-001 (automatic weather station observations)
  - CWA O-A0002-001 (rainfall station observations)
- Candidate station radius: 30 km
- Storage: Supabase PostgreSQL
- Scheduler: GitHub Actions hourly

## Prerequisites

Create GitHub Actions repository secrets:

- CWA_API_KEY
- SUPABASE_URL
- SUPABASE_SECRET_KEY

Never commit API keys or database secrets.

## Apply database migration

1. Open the Supabase project.
2. Open SQL Editor and create a new query.
3. Paste and run `supabase/migrations/202611130001_v32_1_observations.sql`.
4. Confirm tables exist:
   - courses
   - weather_stations
   - station_course_map
   - observation_hourly
   - ingestion_logs
5. Confirm the JIAOXI course row exists.

The migration enables RLS and intentionally creates no anon/public policies. The collector uses the backend Secret Key.

## Manual test

1. Open GitHub Actions.
2. Select "V32.1 CWA Observation Collector".
3. The workflow must first be merged into the repository's default branch before GitHub enables `workflow_dispatch` for it.
4. Select Run workflow and choose the V32.1 branch if it is available in the branch selector.
5. Inspect the run summary and Supabase `ingestion_logs`.
6. Confirm station and observation rows exist.

GitHub scheduled workflows run from the default branch. Do not expect the hourly schedule to start while this workflow exists only on a feature branch.

## Data interpretation notes

- Observation timestamps are stored as timestamptz (UTC representation).
- Missing or sentinel values remain NULL.
- O-A0001-001 and O-A0002-001 are stored as separate dataset rows to avoid rainfall-only records overwriting other variables.
- Station candidates are ranked by straight-line distance only at ingestion. Terrain, elevation, exposure and station type require review before a station is treated as representative of the golf course.
- Precipitation accumulation period must be interpreted by dataset and source field; do not combine different accumulation windows without normalization.
- The current collector is a pilot implementation. Verify actual CWA response fields in ingestion results before using the data for forecast scoring.

## Troubleshooting

- HTTP 401/403: verify CWA API key and platform authorization.
- Empty station list: inspect CWA response structure and dataset availability.
- Supabase 401/403: verify SUPABASE_URL and SUPABASE_SECRET_KEY.
- Table not found: apply the migration before running the workflow.
- No stations within 30 km: inspect coordinates and widen the radius only after review.
