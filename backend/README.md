# Graph of Thoughts — Backend

Implementation of **Graph of Thoughts (GoT)** from Besta et al., *Graph of Thoughts: Solving Elaborate Problems with Large Language Models*, AAAI 2024 ([arXiv:2308.09687](https://arxiv.org/abs/2308.09687)).

This backend is the graded pattern core: a hand-written Graph of Operations (GoO), thought transformations (**Generate / Aggregate / Refine / Score / KeepBest**), multi-parent graph merges, and structured JSONL logs. No LangChain / LangGraph / CrewAI / AutoGen / Semantic Kernel.

LLM calls go to **Groq** via its OpenAI-compatible API (`https://api.groq.com/openai/v1`).

---

## Prerequisites

- Python **3.11+** (3.12 tested)
- A [Groq](https://console.groq.com/) API key
- (Optional) Node 20+ if you also run the React frontend

---

## Install

```bash
cd got-project/backend
python -m venv .venv

# Windows PowerShell — always activate this before running
.\.venv\Scripts\Activate.ps1

# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
```

> **Important:** use the venv interpreter (`.\.venv\Scripts\python` or an activated shell).
> Bare `python run_cli.py` often hits a different global site-packages and breaks imports.

---

## Configure environment

```bash
copy .env.example .env   # Windows
# cp .env.example .env   # macOS / Linux
```

Edit `.env`:

```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_RPM=30

GOT_DEFAULT_NUMBERS=48
GOT_CHUNK_SIZE=8
GOT_GENERATE_K=2
GOT_AGGREGATE_K=2
```

Never commit `.env`. Keys are read only from the environment / `.env` file.

---

## Paper fidelity vs demo defaults

The paper’s sorting GoO often uses **Generate k=3** and **Aggregate k=10** (then KeepBest).  
This repo ships **Generate k=2** and **Aggregate k=2** with KeepBest(1) as a **cost/time tradeoff for a timed class assessment**. Multi-parent Aggregate merges, Refine feedback, Score (paper error-scope X+Y), and KeepBest pruning are unchanged. Raise `GOT_GENERATE_K` / `GOT_AGGREGATE_K` (or pass `--generate-k` / `--aggregate-k`) for a larger demo.

Scoring follows §5.1: `error_scope = X + Y` (adjacent inversions + frequency mismatch), exposed as positive score `max(n - error_scope, 0)`. Adjacent inversion count is also logged as a secondary metric.

---

## Available task plugins

| `--task` | Default chunk | What it does |
|----------|---------------|--------------|
| `sorting` | 8 | Paper §5.1 — chunked sort + pairwise merge |
| `keyword_counting` | 2 sentences | Paper §5.3 — count countries per passage, Aggregate sums |
| `set_intersection` | 8 | Paper §5.2 — split B, intersect with A, Aggregate union |
| `document_merging` | 1 | Paper §5.4 — merge NDA excerpts, dedupe via Aggregate/Refine |

```bash
python run_cli.py --list-tasks
python run_cli.py --task sorting --numbers 48 --chunk-size 8
python run_cli.py --task keyword_counting --chunk-size 2
python run_cli.py --task set_intersection
python run_cli.py --task document_merging
```

New plugins: implement `BaseTask` under `tasks/`, register in `tasks/registry.py`. Engine code stays untouched.

### What you should see

Console (stderr) prints a live trace of GoO steps, LLM calls, merges, scores, refines, and KeepBest prunes.

Artifacts land in `backend/logs/`:

| File | Contents |
|------|----------|
| `logs/<run_id>.jsonl` | Structured event log (video walkthrough source) |
| `logs/<run_id>.graph.json` | Final graph snapshot (nodes + multi-parent edges) |
| `logs/<run_id>.result.json` | Final sorted list, score, LLM usage |

**Fidelity checks** printed at the end:

- ≥1 **Aggregate merge** (`parent_ids → child_id`, multi-parent edges)
- ≥1 **Refine** correction (`llm_fixed` or `fallback_fixed`) when the model errs
- **KeepBest** lines with active node count **before → after**

---

## Run the API server

```bash
cd got-project/backend
.\.venv\Scripts\Activate.ps1
uvicorn api.server:app --reload --host 127.0.0.1 --port 8000
```

Endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/run` | Start a GoT sorting run |
| `GET` | `/stream/{run_id}` | SSE live engine events |
| `GET` | `/runs/{run_id}` | Status + result |
| `GET` | `/runs/{run_id}/graph` | Graph snapshot JSON |
| `GET` | `/runs/{run_id}/log` | Full structured log |
| `GET` | `/health` | Liveness |

Example:

```bash
curl -X POST http://127.0.0.1:8000/run -H "Content-Type: application/json" -d "{\"n\":48,\"chunk_size\":8}"
```

Then open `GET /stream/<run_id>` (or use the frontend).

---

## Frontend (optional)

```bash
cd got-project/frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173 — Vite proxies API calls to port 8000.

---

## Project layout

```
backend/
  engine/          # Thought, Graph, Operations, GoO controller, Groq client, logger
  tasks/           # Pluggable tasks (SortingTask today; drop-in BaseTask later)
  api/             # FastAPI + SSE
  run_cli.py       # Standalone end-to-end runner
  logs/            # JSONL + graph/result artifacts
```

Engine code never imports a task by name except through the `BaseTask` interface — a second task plugin can live under `tasks/` without editing `engine/`.

---

## Troubleshooting

- **`GROQ_API_KEY is not set`** — create `backend/.env` from `.env.example`.
- **Rate limits / 429** — Groq free `llama-3.3-70b-versatile` is **30 requests/minute**. The client now paces (~2s between calls) and waits on 429. Runs take longer but should finish. To go faster: raise `GROQ_RPM` if you upgraded tier, or switch `GROQ_MODEL` to a higher-limit model. Lower `GOT_GENERATE_K` / `GOT_AGGREGATE_K` to cut total calls.
- **No refine events** — the model sorted every chunk perfectly; re-run with another `--seed`, or inspect Aggregate stages (merges of length 16+ err more often). Refine always logs `llm_fixed` vs `fallback_fixed` when a correction runs.
- **Import errors** — run commands from `backend/` with the venv activated so `engine` / `tasks` / `api` resolve on `sys.path`.
