# Graph of Thoughts — Implementation Plan (Plan Mode)

**Artifact:** implementation-ready plan (how to build)  
**Companion spec:** `docs/REQUIREMENTS.md` (what to build)  
**Status:** kickoff plan — written in future tense, as if no repository exists yet  
**Paper:** Besta et al., AAAI 2024, [arXiv:2308.09687](https://arxiv.org/abs/2308.09687)

An implementer should be able to execute this plan phase by phase without inventing architecture. Deviations from the paper that we **choose in advance** are listed in §7; later operational surprises (rate-limit tuning, sink performance) are **not** part of this kickoff plan.

---

## 1. Problem frame

Build a graded Graph of Thoughts demo: a hand-written engine, four paper tasks as plugins, CLI + FastAPI/SSE + React Flow UI, structured logs that make a **multi-parent Aggregate merge** and **node counts** visible.

**In scope:** FR1–FR7 in `docs/REQUIREMENTS.md`.  
**Out of scope:** agent frameworks, production SaaS, paper benchmark tables, frontend LLM keys.

---

## 2. Target architecture

```
Operator
  ├─ CLI  run_cli.py
  └─ UI   Vite :5173  ──POST /run──►  FastAPI :8000
                         EventSource /stream/{id}
                                │
                                ▼
                     GraphOfOperations.run()
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
         Graph (GRS)      Operations T/E/R     BaseTask plugin
         Thought nodes     Generate            prompts / parse
         multi-parent      Aggregate           score / refine
         edges             Refine              split_input
                           Score / KeepBest
                                │
                                ▼
                     GoTLogger → logs/<run_id>.jsonl
                                 (+ SSE callback)
                                 (+ optional Supabase sink)
```

**Paper mapping**

| Paper | Code we will write |
|-------|-------------------|
| G — graph of thoughts | `backend/engine/graph.py` + `thought.py` |
| T — transformations | Generate, Aggregate, Refine in `operations.py` |
| E — evaluator | Score + `task.score_details` |
| R — ranking | KeepBest |
| GoO | `graph_of_operations.py` — static step list |
| GRS | live `Graph` + named `registry` of thought ids |

**Rule:** `engine/` imports `BaseTask` only. Concrete tasks live in `tasks/` and are resolved by `registry.py`.

---

## 3. Planned repository layout

```
got-project/
  backend/
    engine/          # Thought, Graph, operations, GoO, Groq client, logger
    tasks/           # BaseTask + four plugins + registry
    api/             # FastAPI + SSE
    run_cli.py
    requirements.txt
    .env.example
    logs/            # runtime artifacts
  frontend/
    src/components/  # RunControls, GraphVisualizer, MetricsPanel,
                     # NodeInspector, OperationLog, ResultExport
    src/hooks/       # useGoTStream
    vite.config.ts   # proxy API paths → 127.0.0.1:8000
  samples/           # NDA .txt for Docs demos
  supabase/          # optional schema.sql
  docs/              # this plan + later write-ups
```

---

## 4. Locked implementation choices

From the spec (D1–D9). Repeat here so the builder does not “improve” them away:

- Groq HTTP via `httpx` (not the `openai` SDK if the system install is broken).
- Generate k=2, Aggregate k=2, KeepBest(1), sorting n=48 / chunk 8 — overridable by env/CLI/UI.
- Refine = detect → LLM → deterministic fallback.
- SSE for live events.
- React Flow, not a custom canvas.
- Sorting error-scope X+Y → positive score `max(n − error_scope, 0)`.

---

## 5. Build sequence (execute in this order)

Each phase has an exit gate. Do not start the next phase until the gate passes.

### Phase 0 — Skeleton

**Create:** venv, `requirements.txt` (`httpx`, `python-dotenv`, `fastapi`, `uvicorn`, `pydantic`, `sse-starlette`), `.env.example`, empty package dirs.

**Gate:** `python -c "import httpx"` inside venv.

### Phase 1 — Engine core (sorting only)

**Files**

| File | Responsibility |
|------|----------------|
| `backend/engine/thought.py` | Thought dataclass |
| `backend/engine/graph.py` | add_node / add_edge / active set / merge count history |
| `backend/engine/llm_client.py` | Groq chat completions |
| `backend/engine/logger.py` | JSONL + event callback |
| `backend/engine/operations.py` | Generate, Aggregate, Refine, Score, KeepBest |
| `backend/engine/graph_of_operations.py` | `build_decompose_merge_plan` + `run` |
| `backend/tasks/base_task.py` | Abstract contract |
| `backend/tasks/sorting_task.py` | First plugin |
| `backend/tasks/registry.py` | `"sorting"` only at this stage |
| `backend/run_cli.py` | `--task sorting`, `--numbers`, `--chunk-size`, `--list` |

**Behaviour**

- `split_input` slices the list by `chunk_size`.
- Generate sorts a chunk (temperature high enough that imperfect sorts can appear).
- Aggregate merge-sorts two lists; **must** call `graph.add_edge` for each parent.
- `logger.merge_event(parent_ids, child_id, nodes_before, nodes_after)`.
- KeepBest logs `active N → M`.
- CLI prints FIDELITY CHECKS (merge count, refine count, prune drops).

**Gate:** `python run_cli.py --task sorting --list "4,1,3,2,8,5,7,6,9,0,2,1,5,4,3,8" --chunk-size 8` finishes; log contains at least one `event: merge` with **two** `parent_ids`; `.jsonl` / `.graph.json` / `.result.json` exist.

**Check (smallest):** assert merge event has `len(parent_ids) >= 2`.

### Phase 2 — API + SSE

**Files:** `backend/api/schemas.py`, `backend/api/server.py`

**Endpoints**

| Method | Path |
|--------|------|
| GET | `/health` |
| GET | `/tasks` |
| POST | `/run` |
| GET | `/stream/{run_id}` |
| GET | `/runs/{run_id}` |
| GET | `/runs/{run_id}/graph` |
| GET | `/runs/{run_id}/log` |

Run execution in a **daemon thread** so SSE can flush while Groq is blocking. Attach logger `event_callback` to the asyncio queue.

**Gate:** `curl POST /run` then `GET /stream/{id}` receives events through `stream_end`.

### Phase 3 — Frontend visualizer

**Stack:** Vite + React + `@xyflow/react`. Proxy `/run`, `/stream`, `/runs`, `/tasks`, `/health` to port 8000. **No frontend `.env`.**

**Components**

| UI | Role |
|----|------|
| `RunControls` | Mission control: task tiles, inputs, chunk / k, **Run GoT** |
| `GraphVisualizer` | React Flow; badge when `parents.length > 1` |
| `MetricsPanel` | HUD: nodes, active, merges, refines, prune |
| `OperationLog` | Flight recorder of events |
| `NodeInspector` | id, op, score, parents, content, active/discarded |
| `ResultExport` | Final `.txt` / `.md`; selected node `.txt` |
| `useGoTStream` | `POST /run` then `EventSource(/stream/{id})` |

**Gate:** browser at `http://127.0.0.1:5173`, Sorting **Run GoT**, graph grows, inspector shows two parents on an Aggregate node.

### Phase 4 — Remaining paper tasks (generality)

Add plugins; **do not change GoO shape**.

| Plugin | Default chunk | Aggregate semantics | Extra UI |
|--------|---------------|---------------------|----------|
| `keyword_counting` | 2 sentences | **sum** JSON counts | passage textarea |
| `set_intersection` | 8 (on B) | **union** of A∩Bᵢ | sets JSON |
| `document_merging` | 1 doc/seed | **dedupe-merge** bullets | ≥2 file upload or `---` paste |

Register in `registry.py` + `list_tasks()`. Docs scoring may be heuristic (duplicates + coverage) — that is an accepted deviation (spec §7).

**Metadata trap (call out before coding set ∩):** `source_chunk` must be the **subset list**, never the integer index — scoring uses `set(source_chunk)`.

**Gate:** `--list-tasks` returns four ids; each CLI task completes; UI tiles **Sorting / Keywords / Set ∩ / Docs** each start a run.

### Phase 5 — Demo hardening

- Groq **RPM pacing** + 429 retry (`GROQ_RPM` default 30).
- Header **Download .txt / .md** when a run completes.
- Sample NDAs under `samples/`.
- README covering clone → venv → `.env` → CLI → API+UI, plus **design notes / deviations**.

**Gate:** stranger-clone path in README works; a 429 does not kill the run.

### Phase 6 — Optional Supabase mirror

Only after JSONL is solid.

- `supabase/schema.sql` — `got_events` + RLS insert/select for anon.
- `backend/supabase_log/` — attach on logger init if env present.
- **Must not block** Generate/Aggregate (queue + background worker). A sink failure never stops a run.

**Gate:** without keys, behaviour unchanged; with keys, first JSONL line notes sink attached; Table Editor shows rows for that `run_id`.

---

## 6. Implementation units (for the builder)

| Unit | Depends on | Primary files |
|------|------------|---------------|
| U1 Thought + Graph | — | `thought.py`, `graph.py` |
| U2 Logger | U1 | `logger.py` |
| U3 LLM client | — | `llm_client.py` |
| U4 Operations | U1–U3, BaseTask | `operations.py` |
| U5 GoO controller | U4 | `graph_of_operations.py` |
| U6 Sorting plugin | U5 | `sorting_task.py`, `registry.py` |
| U7 CLI | U5–U6 | `run_cli.py` |
| U8 API/SSE | U5 | `api/server.py`, `schemas.py` |
| U9 Frontend | U8 | `frontend/src/**` |
| U10 Three plugins | U5 | `keyword_counting_task.py`, `set_intersection_task.py`, `document_merging_task.py` |
| U11 Polish | U9–U10 | `llm_client` pacing, export, README |
| U12 Optional Supabase | U2 | `supabase_log/sink.py`, `supabase/schema.sql` |

---

## 7. Documented deviations (plan these; put in README)

| Choice | vs paper | Why |
|--------|----------|-----|
| Generate k=2 | typical k=3 | Groq cost / time |
| Aggregate k=2 | often ~10 attempts | same |
| KeepBest N=1 | common KeepBest(1) | keep one winner per step |
| Sorting 48 / chunk 8 | paper-scale demo | full Aggregate ladder under RPM |
| Docs score heuristic | no unique gold NDA | still Refine on dupes/coverage |
| Groq + httpx | original model stack | available API |
| No frameworks | — | assessment rule |

**Unchanged:** decompose → Generate → Score → Refine → KeepBest → pairwise multi-parent Aggregate; sorting X+Y error-scope.

---

## 8. Risks (known at kickoff)

| Risk | Mitigation |
|------|------------|
| Groq 30 RPM / 429 | Pace + Retry-After; smaller k; 16-number demo for video |
| LLM sorts perfectly → no Refine on camera | Keep a longer-run log; fallback still exists in code |
| Aggregate logged totals **increase** when k_attempts>1 | Video script: merge proves multi-parent; KeepBest proves active-set shrink |
| Sync HTTP per event stalls the run | JSONL first; if remote sink exists, it **must** be async |
| Docs with 1 file | Require ≥2 documents so Aggregate can pair |
| System Python / broken `openai` package | Use venv + raw `httpx` |

---

## 9. Test scenarios (minimum)

Not a test framework — one runnable check per unit is enough.

| ID | Scenario | Pass if |
|----|----------|---------|
| T1 | Sorting 16 nums, chunk 8, k=2 | `merge` event with 2 parents; `correct` vs `sorted(input)` |
| T2 | Generate k=2 | two children from one seed (or equivalence reuse logged) |
| T3 | KeepBest | prune line `active N → M` with M < N |
| T4 | Refine fallback | if LLM refine fails, content becomes `sorted(source_multiset)` |
| T5 | Keywords | Aggregate sums two passage dicts |
| T6 | Set ∩ | Aggregate unions partial intersections; `source_chunk` is a list |
| T7 | Docs | two files → at least one Aggregate; <2 files raises |
| T8 | SSE | UI graph updates before `run_end` |
| T9 | No Supabase env | CLI/UI identical; no crash |

---

## 10. Video / viva (plan the evidence, not the script)

Must be visible on screen:

1. Named operations + GoO file.
2. Live UI sorting run.
3. One merge with two parents + logged node counts (honest about 6→8 totals vs active drop).
4. Two other tasks (sum / union / dedupe-merge).
5. README deviations spoken.
6. “If we removed Refine, wrong thoughts stay wrong through KeepBest.”

Scripts can be written later (`docs/VIDEO_SCRIPT.md`). This plan only requires the **engine to produce** that evidence.

---

## 11. Definition of done

- [ ] Phases 0–5 gates pass.
- [ ] Four tasks in the registry and UI.
- [ ] README is the stranger-clone guide + deviations table.
- [ ] At least one recorded run shows `event: merge` with `nodes_before` / `nodes_after`.
- [ ] Phase 6 optional; JSONL works without it.

---

## 12. What this plan deliberately does not include

- Exact Groq latency or token counts (execution-time).
- Pixel-level UI styling.
- Team member names / contribution split (fill in outside this repo).
- Post-hoc bug diaries. Those belong in commit messages or a later write-up, not in a kickoff plan.
