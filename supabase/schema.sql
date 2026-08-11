-- Paste this once in Supabase → SQL Editor → Run.
-- Table used by backend/supabase_log (mirrors GoT JSONL events).

create table if not exists public.got_events (
  id bigint generated always as identity primary key,
  run_id text not null,
  event text not null,
  elapsed_s double precision,
  ts timestamptz not null default now(),
  message text,
  payload jsonb not null default '{}'::jsonb
);

create index if not exists got_events_run_id_idx on public.got_events (run_id);
create index if not exists got_events_ts_idx on public.got_events (ts desc);

alter table public.got_events enable row level security;

drop policy if exists got_events_insert on public.got_events;
drop policy if exists got_events_select on public.got_events;

-- Assessment demo: backend uses the anon (or service) key to insert/read.
create policy got_events_insert on public.got_events
  for insert to anon, authenticated
  with check (true);

create policy got_events_select on public.got_events
  for select to anon, authenticated
  using (true);
