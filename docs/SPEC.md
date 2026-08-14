# Graph of Thoughts — Requirements Specification

**Artifact:** product contract (what to build)  
**Mode:** Plan Mode / kickoff — written as if no code exists yet  
**Paper:** Besta et al., *Graph of Thoughts*, AAAI 2024 ([arXiv:2308.09687](https://arxiv.org/abs/2308.09687))  
**Assessment type:** university implementation + live demo + video walkthrough  

This file is the **WHAT**. The companion **HOW** is `docs/PLAN.md`.

---

## 1. Problem

Chain-of-Thought is a single path. Tree of Thoughts (ToT) can **branch** (one parent → many children) but a child still has **one** parent, so two independent partial answers cannot be combined except by discarding one path.

Graph of Thoughts (GoT) treats intermediate LLM outputs as vertices in a **directed graph**. An **Aggregate** transformation creates a child with **two or more parents**. That multi-parent merge is the paper’s differentiator and the bar this project must make visible.

The paper also defines a **Graph of Operations (GoO)**: a static plan of transformations, executed over a **Graph Reasoning State (GRS)** — the live graph plus scores.

## 2. Goal

Ship a **from-scratch** GoT engine (no LangChain, LangGraph, CrewAI, AutoGen, or Semantic Kernel) that:

1. Implements Generate, Aggregate, Refine, Score, and KeepBest under a GoO controller.
2. Runs **four paper-style tasks** through the **same** engine, proving GoT is not “just sorting.”
3. Exposes the engine via CLI and a live web UI (SSE + graph visualization).
4. Logs every engine event so a merge’s **node count before/after** can be shown on camera.

## 3. Users and context

| User | Need |
|------|------|
| Assessor / viva panel | Run from a clean clone; see a real merge; hear paper→code mapping |
| Student team | Swap tasks without rewriting the engine |
| Demo operator | Start a run, watch the graph grow, export the final thought |

No multi-tenant production, no auth, no cloud deploy requirement.

## 4. Locked decisions (do not reopen during build)

These are product constraints, not implementation guesses.

| ID | Decision | Rationale |
|----|----------|-----------|
| D1 | **Groq** via OpenAI-compatible HTTP (`https://api.groq.com/openai/v1`). Env: `GROQ_API_KEY`, `GROQ_MODEL` default `llama-3.3-70b-versatile`. | Course/API availability. Not OpenRouter, not Grok. |
| D2 | **No agent frameworks.** Hand-written GoO + GRS in Python. | Graded fidelity + code quality. |
| D3 | **React Flow** for the live thought graph. | Directed graph with multi-parent edges is the demo. |
| D4 | Demo defaults: **48** numbers (sorting), **chunk 8**, **Generate k=2**, **Aggregate k=2**, **KeepBest N=1**. | Paper often uses larger k; we cut Groq cost. Overridable. |
| D5 | Sorting score = paper **error-scope X + Y** (adjacent inversions + frequency mismatch), exposed as `max(n − error_scope, 0)`. Log inversions as secondary. | Fidelity to §5.1 scoring idea. |
| D6 | Refine path: **detect error → LLM refine → deterministic fallback**. | Paper-style correction with a guaranteed repair. |
| D7 | Live UI via **Server-Sent Events** from FastAPI, not polling. | Graph must update as operations fire. |
| D8 | Monorepo: `backend/` + `frontend/`. Official README at `backend/README.md`. | Assessment layout. |
| D9 | Engine is **task-agnostic**. Tasks are plugins behind a `BaseTask` contract + registry. | Generality / code quality marks. |

## 5. Functional requirements

### FR1 — Engine (must)

- Represent a **Thought** as a graph node: id, content, parents, score, metadata, active/discarded.
- Represent a **Graph**: nodes, directed parent→child edges, node-count history.
- **Generate(t, k):** one parent → k LLM children.
- **Aggregate(t1…tn, k_attempts):** ≥2 distinct parents → k_attempts children, each with edges from **every** parent. Log merge with `nodes_before` / `nodes_after`.
- **Score:** programmatic `task.score` / `score_details`. Not an LLM-as-judge.
- **Refine:** skip if `detect_error` is none; else LLM then fallback.
- **KeepBest(N):** keep top N by score; mark losers inactive (do not delete — history stays in the graph).
- **GoO controller:** build a decompose-merge plan once, then execute it, wiring step outputs through a named **registry**.
- Shared plan shape: Seed chunks → per chunk Generate → Score → Refine → Score → KeepBest → pairwise Aggregate ladder until one thought remains. Odd leftover **promotes unchanged**.

### FR2 — Task plugins (must)

| Registry id | Paper | Split | Generate | Aggregate |
|-------------|-------|-------|----------|-----------|
| `sorting` | §5.1 | number slices | sort chunk | merge-sort lists |
| `keyword_counting` | §5.3 | sentence groups | count keywords → JSON | **sum** counts |
| `set_intersection` | §5.2 | chunk **B**; A in metadata | A ∩ subset(B) | **union** of partial ∩ |
| `document_merging` | §5.4 | documents | extract bullets | **dedupe-merge** drafts |

Each plugin owns: `split_input`, prompts, parsers, score, `detect_error`, refine fallback, `evaluate_result`.

### FR3 — CLI (must)

- Run any registered task without the frontend.
- List tasks.
- Configurable chunk size, generate-k, aggregate-k, seed, explicit sorting list.
- Write `logs/<run_id>.jsonl`, `.graph.json`, `.result.json`.
- Print a short **fidelity** summary: merge count, refine corrections, KeepBest active-count drops.

### FR4 — API (must)

- `POST /run` starts a run (does not block until completion).
- `GET /stream/{run_id}` SSE of engine events until `stream_end`.
- `GET /tasks`, `GET /runs/{id}`, graph + log fallbacks, `GET /health`.
- CORS open for local Vite.

### FR5 — Frontend (must)

- Task switcher for all four plugins.
- Controls: chunk size, generate k, aggregate k, task-specific input (list / text / JSON / file upload).
- Live graph (React Flow), metrics HUD, operation log, node inspector.
- After completion: download final thought as `.txt` / `.md`.
- Document merging: upload ≥2 `.txt`/`.md` files (or paste with `---` separators).

### FR6 — Logging (must)

- JSONL is the source of truth on disk.
- Events include at least: `run_start`, `goo_step`, `llm_call`, `node_created`, `merge`, `refine`, `score`, `prune`, `run_end`.
- Merge events must include parent ids, child id, `nodes_before`, `nodes_after`.

### FR7 — Optional remote log (should, not must-to-run)

- If `SUPABASE_URL` + anon (or service) key are set, mirror trimmed events to table `got_events`.
- App must run fully without Supabase.
- Dashboard-only setup (paste SQL). No Supabase CLI required.

## 6. Non-functional requirements

| ID | Requirement |
|----|-------------|
| NFR1 | Python 3.11+ backend; Node 18+ frontend. |
| NFR2 | Groq free-tier ~30 RPM: **pace** calls and retry on HTTP 429. Runs may be tens of seconds; must not look “hung.” |
| NFR3 | Secrets only in `backend/.env` (never frontend, never committed). |
| NFR4 | Smallest engine that is still paper-faithful. No extra abstractions. |
| NFR5 | A stranger can clone, set `GROQ_API_KEY`, and run CLI + UI from the README. |

## 7. Out of scope

- Reproducing the paper’s original model stack or published accuracy tables.
- Production auth, multi-user persistence, Kubernetes.
- Replacing JSONL with a database as the primary log.
- Frontend calling Groq or holding API keys.
- Dynamic GoO (plan is static once chunks are known).

## 8. Acceptance (assessment bar)

The implementation is done when all of the following are true:

1. **Working E2E:** a live sorting run finishes with a scored final thought; UI graph shows the run.
2. **Paper fidelity:** Generate / Aggregate / Refine / Score / KeepBest exist as named operations; GoO controller walks a plan; at least one **merge** has two independent parents and logged before/after node counts.
3. **Generality:** at least two non-sorting plugins run on the same engine (all four preferred).
4. **Code quality:** `engine/` does not import a concrete task class; plugins implement `BaseTask`.
5. **Honest deviations:** README lists k=2 vs paper k=3/k≈10, Groq, heuristic docs score — with one-line justifications.

## 9. Traceability

| Requirement | Planned home |
|-------------|----------------|
| FR1 | `backend/engine/` |
| FR2 | `backend/tasks/` |
| FR3 | `backend/run_cli.py` |
| FR4 | `backend/api/` |
| FR5 | `frontend/src/` |
| FR6 | `backend/engine/logger.py` |
| FR7 | `backend/supabase_log/` + `supabase/schema.sql` |
| NFR2 | `backend/engine/llm_client.py` |
| D1–D9 | README “design notes” + `.env.example` |
