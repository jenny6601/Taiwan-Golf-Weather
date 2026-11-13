-- V32.1: Jiaoxi pilot observation ingestion
-- Apply this migration in Supabase SQL Editor before running GitHub Actions.
-- All timestamps are stored as timestamptz (UTC internally).

create extension if not exists pgcrypto;

create table if not exists public.courses (
  id text primary key,
  name text not null,
  county text,
  address text,
  latitude double precision not null,
  longitude double precision not null,
  elevation_m double precision,
  timezone text not null default 'Asia/Taipei',
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint courses_latitude_range check (latitude between -90 and 90),
  constraint courses_longitude_range check (longitude between -180 and 180)
);

create table if not exists public.weather_stations (
  id uuid primary key default gen_random_uuid(),
  provider text not null,
  station_code text not null,
  station_name text not null,
  latitude double precision not null,
  longitude double precision not null,
  elevation_m double precision,
  station_type text,
  active boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  unique(provider, station_code),
  constraint station_latitude_range check (latitude between -90 and 90),
  constraint station_longitude_range check (longitude between -180 and 180)
);

create table if not exists public.station_course_map (
  id uuid primary key default gen_random_uuid(),
  course_id text not null references public.courses(id) on delete cascade,
  station_id uuid not null references public.weather_stations(id) on delete cascade,
  distance_km double precision not null,
  elevation_difference_m double precision,
  representativeness text not null default 'candidate'
    check (representativeness in ('candidate','accepted','rejected','pending_review')),
  notes text,
  updated_at timestamptz not null default now(),
  unique(course_id, station_id)
);

-- Keep separate source datasets separate. This prevents a rainfall-only dataset
-- from overwriting temperature/wind values collected from the hourly dataset.
create table if not exists public.observation_hourly (
  id bigserial primary key,
  station_id uuid not null references public.weather_stations(id) on delete cascade,
  provider text not null,
  dataset_code text not null,
  observed_at timestamptz not null,
  source_updated_at timestamptz,
  temperature_c double precision,
  relative_humidity_pct double precision,
  precipitation_mm double precision,
  wind_speed_ms double precision,
  wind_gust_ms double precision,
  wind_direction_deg double precision,
  quality_status text not null default 'pending'
    check (quality_status in ('pending','passed','suspect','missing')),
  quality_flags jsonb not null default '[]'::jsonb,
  raw_data jsonb not null default '{}'::jsonb,
  collected_at timestamptz not null default now(),
  unique(station_id, provider, dataset_code, observed_at)
);

create table if not exists public.ingestion_logs (
  id bigserial primary key,
  provider text not null,
  dataset_code text,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null check (status in ('running','success','partial','failed')),
  records_received integer not null default 0,
  stations_saved integer not null default 0,
  observations_saved integer not null default 0,
  error_message text,
  metadata jsonb not null default '{}'::jsonb
);

create index if not exists idx_weather_stations_location
  on public.weather_stations(latitude, longitude);
create index if not exists idx_station_course_map_course
  on public.station_course_map(course_id, distance_km);
create index if not exists idx_observation_station_time
  on public.observation_hourly(station_id, observed_at desc);
create index if not exists idx_observation_dataset_time
  on public.observation_hourly(provider, dataset_code, observed_at desc);
create index if not exists idx_ingestion_logs_started
  on public.ingestion_logs(started_at desc);

-- V32.1 writes through the backend Secret Key. RLS is enabled and no public
-- policies are created; browser access remains closed until a later read-only
-- frontend policy is deliberately designed.
alter table public.courses enable row level security;
alter table public.weather_stations enable row level security;
alter table public.station_course_map enable row level security;
alter table public.observation_hourly enable row level security;
alter table public.ingestion_logs enable row level security;

insert into public.courses
  (id, name, county, address, latitude, longitude, timezone, active)
values
  ('JIAOXI', '礁溪高爾夫球場', '宜蘭縣',
   '宜蘭縣礁溪鄉林美村林尾路156號',
   24.8389, 121.7389, 'Asia/Taipei', true)
on conflict (id) do update set
  name = excluded.name,
  county = excluded.county,
  address = excluded.address,
  latitude = excluded.latitude,
  longitude = excluded.longitude,
  timezone = excluded.timezone,
  active = true,
  updated_at = now();

comment on table public.observation_hourly is
  'V32.1 station observations. Rows are separated by provider and dataset_code; missing values remain NULL.';
comment on column public.observation_hourly.observed_at is
  'Observation valid time, stored as timestamptz.';
comment on column public.observation_hourly.precipitation_mm is
  'Precipitation amount exactly as defined by the source dataset/time window; consult dataset_code before comparing.';
