# How Supabase Event Logging Is Implemented

**Audience:** teammate / assessor who already knows the GoT engine and JSONL logs, and needs the optional remote log explained end to end.

**Scope:** Supabase only. Local `backend/logs/<run_id>.jsonl` is still the source of truth. This is a **mirror**, not a second logger.

**Code map**

| Piece | Path |
|--------|------|
| Schema + RLS | `supabase/schema.sql` |
| Sink (queue + REST insert) | `backend/supabase_log/sink.py` |
| Package export | `backend/supabase_log/__init__.py` |
| Hook point | `backend/engine/logger.py` → `GoTLogger.__init__` |
| Env template | `backend/.env.example` |
| Keys (never commit) | `backend/.env` |

---

## What we built (one sentence)

Every event `GoTLogger` already writes to JSONL is **also** POSTed to a Supabase table `got_events`, on a **background queue**, only if `SUPABASE_URL` + a key are in `.env`. No CLI. No frontend SDK. No extra event types.

**Demo line:** *“Same events as the JSONL file — Table Editor is just a shared view of the run.”*

---

## What we deliberately did **not** do

| Temptation | Why we skipped it |
|------------|-------------------|
| `supabase` Python SDK / JS client | One `httpx` POST is enough; we already depend on `httpx` for Groq |
| Supabase CLI / migrations / local Docker | Assessment setup is: paste SQL once in the dashboard |
| Realtime subscriptions in the UI | The UI already has SSE from FastAPI |
| Logging from the frontend | Keys stay on the backend |
| Replacing JSONL | Disk logs still work with keys missing or Supabase down |
| Service-role key required | Anon + RLS insert/select is enough for the demo |

---

## Why it exists

JSONL is per-machine (`backend/logs/`). For the assessment we wanted:

1. A place a teammate can open **without** cloning logs off disk.
2. Filter by `run_id`, scan `event` types (`llm_call`, `merge`, `refine`, `prune`, …).
3. Zero change to the engine’s event vocabulary.

If env vars are missing, `attach_supabase_sink` returns `False` and the run is identical to before.

---

## Setup (dashboard only — no CLI)

1. Create a project at [https://supabase.com/dashboard](https://supabase.com/dashboard).
2. **SQL Editor** → paste `supabase/schema.sql` → **Run**.
3. **Project Settings → API** → copy:
   - Project URL → `SUPABASE_URL`
   - `anon` `public` key → `SUPABASE_ANON_KEY`
4. Put both in `backend/.env` (see `.env.example`). Restart uvicorn.
5. Next **Run GoT** should emit `Supabase event sink attached (async)` as the first JSONL line.
6. Dashboard → **Table Editor → `got_events`**. Filter `run_id` `eq` `api-xxxxxxxx` (or sort `id` / `ts` **descending**). The table default is first ~100 rows by `id` ascending — older runs sit on page 1.

Optional: `SUPABASE_SERVICE_ROLE_KEY` in `.env` is used **instead of** the anon key if set. Prefer anon for the demo. Never put either key in the frontend.

---

## Schema

```sql
public.got_events (
  id         bigint generated always as identity primary key,
  run_id     text not null,          -- e.g. api-d83b4fd9
  event      text not null,          -- same names as JSONL
  elapsed_s  double precision,       -- seconds since GoTLogger start
  ts         timestamptz not null,
  message    text,                   -- human line from the logger
  payload    jsonb not null default '{}'
)
```

Indexes: `run_id`, `ts desc`.

**RLS** is on. Two policies for `anon` and `authenticated`:

- `INSERT` … `with check (true)`
- `SELECT` … `using (true)`

That is intentional for a short-lived assessment project. It is **not** a production permission model. There is no `UPDATE` / `DELETE` policy for anon — Table Editor (as the project owner) can still delete rows.

`schema.sql` is idempotent (`create table if not exists`, `drop policy if exists` then recreate).

---

## How the hook works

`GoTLogger` always writes JSONL first. Then, if a callback is set, it fans the **same dict** out (SSE for the UI, and now Supabase).

```
GoTLogger.__init__
  └─ try: attach_supabase_sink(self)   # silent if keys missing or import fails
  └─ _emit("run_start", ...)

_emit(event)
  ├─ append to self.events
  ├─ append line to logs/<run_id>.jsonl
  ├─ print to console
  └─ event_callback(event)             -- SSE  AND  supabase sink
```

`attach_supabase_sink`:

1. Returns immediately if `SUPABASE_URL` or key is missing.
2. Builds the PostgREST URL: `{SUPABASE_URL}/rest/v1/got_events`.
3. Starts one daemon thread + `queue.Queue`.
4. Wraps `logger.event_callback` so the previous callback (SSE `on_event`) still runs, then `sink(event)`.
5. Logs `Supabase event sink attached (async)` — that line itself is the first queued insert.

Attach exceptions are swallowed in `logger.py` so a bad import can never kill a run.

---

## Why the sink is async (this mattered)

**First version** POSTed inside `event_callback`, on the **same thread** as Generate / Aggregate / Refine.

A sorting run is ~250–300 events. Each `httpx.post` to Supabase is a network round-trip. That turned a ~47s run into **~319s**. The extra time was **not** Groq.

**Current version** (`sink.py`):

- `sink()` only `put_nowait`s a trimmed row.
- A daemon worker `httpx.Client` drains the queue and POSTs with `Prefer: return=minimal`.
- First 400 / exception is printed once (`[supabase] insert failed …` or `sink offline`) so a dead project does not spam the console.
- HTTP failures never raise into the engine.

The run stays Groq-bound. Rows may lag the UI by a second or two; after `run_end` the worker keeps draining while uvicorn is up.

---

## What is stored vs what is dropped

Each row is a **thin** copy of the JSONL event:

| Column | From the event |
|--------|----------------|
| `run_id` | `event["run_id"]` |
| `event` | `event["event"]` (`run_start`, `goo_step`, `llm_call`, `node_created`, `merge`, `refine`, `score`, `prune`, `run_end`, `info`, …) |
| `elapsed_s` | `event["elapsed_s"]` |
| `ts` | `event["ts"]` |
| `message` | `message` or `summary` |
| `payload` | everything else, trimmed |

**Dropped from `payload`** (keep the table small / avoid dumping prompts):

- `prompt`
- `response`
- `graph_snapshot` (those live in `logs/<run_id>.graph.json`)

Strings longer than 400 chars are cut with `…`. Lists longer than 40 items are cut. Full text is still on disk in JSONL.

---

## End-to-end path (one Run click)

```
UI  POST /run
  → FastAPI starts a daemon thread (_execute_run)
  → GoTLogger(run_id=api-…)
       attach_supabase_sink  (if .env has keys)
  → GoO / operations emit events
  → JSONL + SSE (live graph)
  → queue → worker POST /rest/v1/got_events
  → Table Editor shows the same run_id
```

CLI runs (`python run_cli.py`) use the same `GoTLogger`, so they log to Supabase too if keys are set. We did **not** add a CLI flag; env on/off is the switch.

---

## How to verify a run actually landed

Do not trust page 1 of Table Editor after several runs.

1. JSONL first line is `Supabase event sink attached (async)`.
2. In Table Editor: filter `run_id` = that run (from the UI / `logs/api-*.jsonl` filename).
3. Row count should be in the same ballpark as JSONL line count (JSONL has the attach + `run_start` + every engine event).

If the filter is empty:

- Keys missing → no attach line in JSONL.
- `schema.sql` never run → worker prints `[supabase] insert failed (404)` once.
- RLS / wrong key → `401` / `403` once in the uvicorn console.
- Looking at an old page of ids → sort `id` descending.

---

## Failure modes we accepted

| Situation | Behaviour |
|-----------|-----------|
| No env vars | Local JSONL only. No error. |
| Import / attach throws | Swallowed. Run continues. |
| Insert 4xx/5xx | Printed once. Queue keeps draining. |
| Network timeout (8s) | Same — one warning, engine unaffected. |
| uvicorn `--reload` mid-run | In-flight queue dies with the worker process. Re-run. |
| Anon key in a public repo | **Don’t.** `.env` is local; only `.env.example` is committed. |

---

## Files a teammate should read (in order)

1. This doc.
2. `supabase/schema.sql` — table + RLS (30 lines).
3. `backend/supabase_log/sink.py` — queue + POST (the whole feature).
4. `backend/engine/logger.py` — the four-line hook in `__init__`.

That is the entire implementation. Everything else (Groq, GoO, React Flow) is unchanged.
