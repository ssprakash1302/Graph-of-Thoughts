# Graph of Thoughts (GoT)

From-scratch university implementation of **Graph of Thoughts** (Besta et al., AAAI 2024, [arXiv:2308.09687](https://arxiv.org/abs/2308.09687)): one shared graph-reasoning engine (**Generate / Aggregate / Refine / Score / KeepBest** under a **Graph of Operations** controller) driving four interchangeable task plugins — `sorting`, `keyword_counting`, `set_intersection`, and `document_merging`. No LangChain / LangGraph / CrewAI / AutoGen. LLM calls go to **Groq** via its OpenAI-compatible HTTP API. This file is the project README (kept at `backend/README.md` for assessment layout) and covers backend CLI, FastAPI, and the React frontend.

---

## Architecture overview

The **backend** owns the engine (`backend/engine/`), task plugins (`backend/tasks/`), CLI (`backend/run_cli.py`), and FastAPI + SSE (`backend/api/`). The **frontend** (`frontend/`) is a Vite + React app that starts a run with `POST /run`, streams events over SSE (`/stream/{run_id}`), and renders the live thought graph with React Flow. Task-specific logic (prompts, parsers, scores, `split_input`) lives only under `tasks/`; the GoO plan and operations stay task-agnostic via `BaseTask`.

```
got-project/
  backend/
    api/                 # FastAPI schemas + server (SSE)
    engine/              # Thought, Graph, Operations, GoO, Groq client, logger
    tasks/               # sorting, keyword_counting, set_intersection, document_merging
    supabase_log/        # optional async mirror of events → Supabase
    run_cli.py           # CLI runner (no frontend)
    requirements.txt
    .env.example
    logs/                # JSONL + graph/result artifacts (created at runtime)
  frontend/
    src/
      components/        # RunControls, GraphVisualizer, MetricsPanel, …
      hooks/             # useGoTStream (POST /run + EventSource)
    vite.config.ts       # proxies /run, /stream, /runs, /tasks, /health → :8000
  samples/               # sample NDA .txt files for document_merging UI demos
  supabase/
    schema.sql           # optional got_events table + RLS
  docs/                  # deeper write-ups (not required to run)
```

---

## Prerequisites

| Tool | Notes |
|------|--------|
| **Python 3.11+** | Not pinned in-repo; syntax uses `str \| None` / `list[…]`. **3.12** verified in development. |
| **Node.js + npm** | Not pinned in `frontend/package.json` (`engines` absent). **Node 18+** recommended (Vite 6); **22.x** verified. |
| **Groq API key** | Required. Create one at [https://console.groq.com/](https://console.groq.com/). |
| **Supabase project** | **Optional.** Only needed if you want remote event mirroring (see § Optional: Supabase). |

---

## Setup — Backend

From a clean clone, in a terminal:

```bash
cd got-project/backend
python -m venv .venv
```

Activate the venv (required — bare system `python` often fails imports):

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

`requirements.txt` installs: `httpx`, `python-dotenv`, `fastapi`, `uvicorn[standard]`, `pydantic`, `sse-starlette`.

Configure environment:

```powershell
# Windows
copy .env.example .env
```

```bash
# macOS / Linux
cp .env.example .env
```

Edit `backend/.env`. Variables match `.env.example` exactly:

| Variable | Required? | Purpose |
|----------|-----------|---------|
| `GROQ_API_KEY` | **Yes** | Groq API key |
| `GROQ_BASE_URL` | No (has default) | Default `https://api.groq.com/openai/v1` |
| `GROQ_MODEL` | No | Default `llama-3.3-70b-versatile` |
| `GROQ_RPM` | No | Default `30` (client pacing) |
| `GOT_DEFAULT_NUMBERS` | No | Default `48` (sorting demo length) |
| `GOT_CHUNK_SIZE` | No | Present in `.env.example` (default `8`); **not read by current code** — chunk size comes from CLI `--chunk-size`, API `chunk_size`, or per-task defaults in `tasks/registry.py` |
| `GOT_GENERATE_K` | No | Default `2` |
| `GOT_AGGREGATE_K` | No | Default `2` |
| `SUPABASE_URL` | Optional | Project URL for event mirroring |
| `SUPABASE_ANON_KEY` | Optional | Anon key (or set `SUPABASE_SERVICE_ROLE_KEY` instead) |
| `SUPABASE_SERVICE_ROLE_KEY` | Optional | If set, used instead of the anon key |

Minimum to run:

```env
GROQ_API_KEY=your_groq_api_key_here
```

Do not commit `.env`.

---

## Setup — Frontend

No frontend `.env` is required. Vite proxies API paths to `http://127.0.0.1:8000` (see `frontend/vite.config.ts`).

```bash
cd got-project/frontend
npm install
```

Dev server (after the API is up — see § Running it — Full app):

```bash
npm run dev
```

Other scripts from `package.json`: `npm run build` (`tsc -b && vite build`), `npm run preview`.

---

## Running it — CLI (no frontend needed)

Work from `got-project/backend` with the venv activated and `.env` set.

**List registered tasks:**

```bash
python run_cli.py --list-tasks
```

Prints JSON for: `sorting`, `keyword_counting`, `set_intersection`, `document_merging`.

**Default / demo sorting run** (random length from `GOT_DEFAULT_NUMBERS` / `--numbers`, default chunk 8):

```bash
python run_cli.py --task sorting --numbers 48 --chunk-size 8
```

**Another task with a non-default chunk size:**

```bash
python run_cli.py --task keyword_counting --chunk-size 2
```

**Further working examples** (flags from `run_cli.py`):

```bash
python run_cli.py --task set_intersection --chunk-size 8
python run_cli.py --task document_merging --chunk-size 1
python run_cli.py --task sorting --list 4,1,3,2,8,5,7,6 --chunk-size 4
python run_cli.py --task sorting --generate-k 2 --aggregate-k 2 --seed 42
```

Optional: `--input-json path/to/input.json` overrides demo input; `--log-dir` and `--run-id` override log location / id.

**Where CLI output lands**

| Artifact | Path pattern |
|----------|----------------|
| Event trace | `backend/logs/<run_id>.jsonl` |
| Graph snapshot | `backend/logs/<run_id>.graph.json` |
| Result summary | `backend/logs/<run_id>.result.json` |

CLI `run_id` defaults to `cli-` + 8 hex chars (e.g. `cli-67dd2c00`). Stderr shows a live operation trace; stdout prints the final result JSON. End-of-run fidelity lines count multi-parent Aggregate merges, Refine corrections, and KeepBest active-count drops.

---

## Running it — Full app (backend API + frontend UI)

**Terminal 1 — API** (from `got-project/backend`, venv on):

```bash
uvicorn api.server:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — UI** (from `got-project/frontend`):

```bash
npm run dev
```

Open **http://127.0.0.1:5173** (Vite default port from `vite.config.ts`).

### What you can do in the UI

Verified against `frontend/src/components/` + `App.tsx`:

- **RunControls** — task tiles (`Sorting` / `Keywords` / `Set ∩` / `Docs`), chunk size, generate-k / aggregate-k, seed; sorting list / keyword text / set JSON editors; Docs multi-file `.txt`/`.md` upload; **Run GoT**
- **GraphVisualizer** — live React Flow thought graph (nodes + multi-parent Aggregate edges)
- **MetricsPanel** — HUD / rail counts (nodes, merges, refines, …)
- **OperationLog** — streaming event ticker
- **NodeInspector** — selected node content / score / parents
- **ResultExport** + header buttons — download final (or selected) result as `.txt` / `.md`

### API surface (for curl / debugging)

| Method | Path | Role |
|--------|------|------|
| `GET` | `/health` | `{"status":"ok"}` |
| `GET` | `/tasks` | `{"tasks":[…]}` from the registry |
| `POST` | `/run` | Start a run; body = `RunRequest` |
| `GET` | `/stream/{run_id}` | SSE engine events until `stream_end` |
| `GET` | `/runs/{run_id}` | Status + result / error |
| `GET` | `/runs/{run_id}/graph` | Graph snapshot JSON |
| `GET` | `/runs/{run_id}/log` | Events from JSONL or memory |

`POST /run` body fields (`api/schemas.py`): `task` (default `sorting`), optional `numbers`, `n` (default 48), `payload` (non-sorting input object), `chunk_size`, `seed`, `generate_k`, `aggregate_k`. Response: `{ run_id, status, message, task }` with `run_id` like `api-d83b4fd9`.

Example:

```bash
curl -X POST http://127.0.0.1:8000/run ^
  -H "Content-Type: application/json" ^
  -d "{\"task\":\"sorting\",\"n\":48,\"chunk_size\":8}"
```

```bash
# macOS / Linux
curl -X POST http://127.0.0.1:8000/run \
  -H "Content-Type: application/json" \
  -d '{"task":"sorting","n":48,"chunk_size":8}'
```

Then connect to `GET /stream/<run_id>` or use the UI.

**Sample inputs for Docs:** `got-project/samples/nda-confidentiality.txt`, `nda-return-destroy.txt`, `nda-affiliates-publicity.txt` (upload ≥2 in the Docs task). Additional NDA text also exists under `got-project/data/input/`.

---

## Optional: Supabase run mirroring

The app runs fully **without** Supabase. Local JSONL under `backend/logs/` is the source of truth. If `SUPABASE_URL` and `SUPABASE_ANON_KEY` (or `SUPABASE_SERVICE_ROLE_KEY`) are set, the same engine events are also inserted asynchronously into table `got_events`.

1. Create a project at [https://supabase.com/dashboard](https://supabase.com/dashboard).
2. **SQL Editor** → paste and run `got-project/supabase/schema.sql`.
3. **Project Settings → API** → copy Project URL → `SUPABASE_URL`, and `anon` `public` key → `SUPABASE_ANON_KEY` in `backend/.env`.
4. Restart uvicorn (or the next CLI process) so env is reloaded.
5. Confirm: first line of the new `logs/<run_id>.jsonl` includes `Supabase event sink attached (async)`. In Table Editor → `got_events`, filter by `run_id` (or sort `id` descending).

Details: `docs/SUPABASE_EVENT_LOG.md`.

---

## Where outputs / logs live

All runs write under **`backend/logs/`** (CLI default; API always uses this directory):

| File | Produced by | Contents |
|------|-------------|----------|
| `<run_id>.jsonl` | `GoTLogger` on every emit | Structured events (`run_start`, `goo_step`, `llm_call`, `node_created`, `merge`, `refine`, `score`, `prune`, `run_end`, …) |
| `<run_id>.graph.json` | CLI after `run` / API after completion | Full graph snapshot (nodes, edges, stats) |
| `<run_id>.result.json` | Same | Final content, score, `ground_truth` / `correct` when defined, LLM usage, GoO step count |

`run_id` patterns: `cli-<8 hex>` (CLI) or `api-<8 hex>` (API).

---

## Design notes / deviations from the paper

Verified against code / `.env.example` / task plugins:

| Deviation | In this repo | Justification |
|-----------|--------------|---------------|
| Generate branching factor | Default **k=2** (`GOT_GENERATE_K`), not paper’s typical **k=3** | Fewer Groq calls for a timed assessment demo; overridable via env / `--generate-k` / API |
| Aggregate attempts | Default **k=2** (`GOT_AGGREGATE_K`), not paper’s larger Aggregate width (often ~10) | Same cost/time tradeoff; overridable |
| KeepBest | **N=1** after each Generate/Aggregate pipeline | Matches common paper KeepBest(1) usage; hardcoded default on the controller |
| Sorting length / chunk | Demo **48** numbers, chunk **8** (6 leaves) | Paper §5.1-scale demo that still shows a full Aggregate ladder under RPM limits |
| Document merging score | Heuristic (bullet duplicates + lexical coverage); no single gold string | NDA merge has no unique ground-truth document; Refine uses soft thresholds |
| LLM provider | **Groq** OpenAI-compatible HTTP (`httpx`), not the paper’s original model stack | Course constraint / available API |
| Agent frameworks | None | Assessment requires a hand-written GoO + GRS |

Unchanged relative to the paper’s *structure*: decompose → Generate → Score → Refine → KeepBest → pairwise Aggregate with **multi-parent** edges; sorting error-scope **X (adjacent inversions) + Y (frequency mismatch)** as `max(n - error_scope, 0)`.

---

## Known limitations

- **Groq free-tier RPM (~30 for `llama-3.3-70b-versatile`)** — `LLMClient` paces calls and retries on HTTP 429. Sorting demos with many Generate/Aggregate steps are intentionally slower (~tens of seconds), not hung.
- **Document merging needs ≥2 documents** — `split_input` raises if fewer than two; the UI also expects ≥2 uploads (or paste with `---` separators) so Aggregate can pair.
- **API run store is in-memory** — process restart loses `/runs/{id}` state; JSONL / `.graph.json` / `.result.json` on disk remain.
- **Equivalence / KeepBest** — discarded thoughts stay in the graph with `active=false` (history), but are not fed to later steps.
- **Supabase is best-effort** — insert failures are logged once and never block the engine; check Table Editor filters if new rows are not on page 1.

---

## Troubleshooting

- **`GROQ_API_KEY is not set`** — copy `.env.example` → `.env` and set the key; restart the process.
- **Import errors (`engine` / `tasks`)** — run from `backend/` with the venv activated.
- **UI `POST /run` fails** — ensure uvicorn is on `127.0.0.1:8000`; Vite only proxies while `npm run dev` is running.
- **No Refine events** — the model may have scored perfectly on every candidate; try another `--seed` or inspect longer Aggregate merges.
- **429 / slow runs** — expected under free RPM; lower `GOT_GENERATE_K` / `GOT_AGGREGATE_K`, or raise `GROQ_RPM` / change `GROQ_MODEL` if your Groq tier allows.
