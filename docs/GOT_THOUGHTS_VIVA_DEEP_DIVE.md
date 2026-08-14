# GoT Thoughts Deep Dive — Viva Guide (All 4 Tasks)

**Audience:** you, the night before viva.  
**Goal:** explain *how thoughts work in our app* clearly enough to score marks — not just recite the paper.  
**Paper:** Besta et al., *Graph of Thoughts*, AAAI 2024 (arXiv:2308.09687).  
**Scope:** Sorting + Keyword Counting + Set Intersection + Document Merging, and the **shared engine**.

**Related docs (do not confuse):**

| Doc | What it is |
|-----|------------|
| **This file** | How Thoughts / GoO / all 4 tasks work — viva explanation |
| `docs/THREE_TASK_PLUGINS.md` | Implementation notes for the three non-sorting plugins + UI features |
| `docs/SUPABASE_EVENT_LOG.md` | Optional remote logging only |

---

## 0. Open with this (30 seconds)

> “We implemented Graph of Thoughts as a hand-written engine — no LangChain. A **Thought** is a node in a graph. A **Graph of Operations** is a static plan we build once, then execute. All four paper-style tasks plug into the same plan. Only prompts, parsers, scoring, and how we split/merge *content* change. Aggregate creates **multi-parent** edges — that is what Tree of Thoughts cannot express.”

If they interrupt: point at React Flow diamonds (two parents → one child) and say “that edge is Aggregate.”

---

## 1. Paper vocabulary → our code (memorize this table)

| Paper | Meaning | Our code |
|-------|---------|----------|
| **G** | Graph of thoughts | `engine/graph.py` — nodes = Thoughts, edges = parent→child |
| **T** | Thought transformations | `Generate`, `Aggregate`, `Refine` in `engine/operations.py` |
| **E** | Evaluator | `Score` + `task.score` / `score_details` |
| **R** | Ranking / selection | `KeepBest` (keep top N by score) |
| **GoO** | Graph of Operations (the *plan*) | `engine/graph_of_operations.py` — list of `GoOStep` |
| **GRS** | Graph Reasoning State | live `Graph` + `registry` of named thought-ID buckets |

**One-liner distinction (high marks):**

- **GoO** = the *recipe* (what to do next: Generate chunk 0, then Score, …).
- **GRS / Graph** = the *working memory* (actual Thought nodes and scores as we run).

---

## 2. What is a Thought in our application?

A Thought is **not** “whatever the LLM said in chat.” It is a structured object:

| Field | Role in viva |
|-------|----------------|
| `id` | Unique node id (shown in UI / logs) |
| `content` | The *payload* — shape depends on task (list, dict, bullets, …) |
| `parents` | List of parent thought ids — **length ≥ 2 after Aggregate** |
| `operation_type` | How it was created: Seed / Generate / Aggregate / Refine / … |
| `score` | Higher is better; set by Score |
| `state_signature` | “Same logical problem piece?” — used for equivalence merge |
| `metadata` | Task context: `source_multiset`, `source_passage`, `set_a`, `source_chunk`, … |
| `active` | `False` after KeepBest discards it (node stays in graph for history) |

**Say this:**  
“Generate produces tree edges (one parent). Aggregate produces **graph** edges (multiple parents into one child). That is GoT.”

---

## 3. The shared GoO (same for all four tasks)

Built by `GraphOfOperations.build_decompose_merge_plan` — **one function**, every task.

### Pattern (say it as a pipeline)

```
Raw input
  └─ Seed: split into chunks                          [no LLM]
  └─ For each chunk:
        Generate(k) → Score → Refine? → Score → KeepBest(N)
  └─ While more than one survivor:
        Pairwise Aggregate(k) → Score → Refine? → Score → KeepBest(N)
  └─ One final Thought → evaluate_result
```

### Demo defaults (know these numbers)

| Knob | Our default | Paper often uses | Why we lowered |
|------|-------------|------------------|----------------|
| Generate `k` | **2** | 3 | Fewer Groq calls / demo cost |
| Aggregate `k_attempts` | **2** | ~10 | Same |
| KeepBest `N` | **1** | 1 | Keep the winner per branch |
| Chunk size | task-dependent (sorting 8, …) | paper-specific | Demo + RPM |

### Odd number of leaves

If a merge level has 3 survivors: pair two, **promote the third unchanged** to the next level. Then merge. (Document merging with 3 files is the clean viva example.)

### Registry vs Graph (easy examiner trap)

| | Graph | Registry |
|-|-------|----------|
| What | Every Thought node ever created | Named buckets: `chunk_0`, `gen_0`, `best_chunk_0`, `agg_L0_0`, … |
| UI | React Flow | Invisible wiring inside the controller |
| Pruned nodes | Still in graph, `active=false` | Not fed into later steps |

---

## 4. Operations — what each one does (engine level)

### Seed

- **Not** an LLM call.
- `task.split_input(raw, chunk_size)` → list of chunks.
- Each chunk becomes a Thought with `task.seed_metadata(...)`.
- Metadata is critical: scoring later needs the **source** (multiset / passage / subset B / document).

### Generate (`Generate(t, k)`)

- Exactly **one** parent.
- Calls LLM **k times** (temperature ~0.7 so imperfect answers appear → Refine can fire).
- `task.generate_prompt` → Groq → `task.parse_generate`.
- Creates **k child nodes**, each with `parents = [parent.id]`.
- May reuse an equivalent existing node (same signature + same content) to avoid duplicates.

### Score

- Deterministic. No LLM.
- `task.score_details(thought)` → writes `thought.score` and logs X/Y or error_scope.

### Refine

- Path in our code (paper-aligned):
  1. `detect_error(thought)` → if `None`, skip (pass through).
  2. Else LLM `refine_prompt` → `parse_refine`.
  3. If LLM fails / still needed: **deterministic** `task.refine()` fallback.
- Logged paths: `llm_fixed` or `fallback_fixed`.
- New child node; parent remains in history.

### KeepBest(N)

- Sort active inputs by score (higher better).
- Keep top N; mark others `active=false`.
- **Does not delete** nodes — graph still shows pruned attempts (good for viva demo).

### Aggregate (the GoT signature)

- Expects **≥ 2** parent thoughts.
- LLM merges them (`aggregate_prompt` / `parse_aggregate`), with `k_attempts` candidates.
- Child has `parents = [id1, id2, …]` → **multi-parent edge**.
- Structural `task.aggregate(...)` also builds metadata (combined source scope).

---

## 5. What the plugin owns vs what the engine owns

| Engine owns (unchanged across tasks) | Plugin owns (`BaseTask`) |
|--------------------------------------|---------------------------|
| GoO plan shape | `split_input`, `seed_metadata` |
| Generate / Aggregate / Refine / Score / KeepBest classes | All `*_prompt` + `parse_*` |
| Graph + registry + logging | `score`, `detect_error`, `refine` fallback |
| Groq client + RPM pacing | `state_signature` / `is_equivalent` |
| FastAPI SSE + frontend | `evaluate_result` (final correctness) |

**Viva line:**  
“GoT is the engine; each paper use-case is a `BaseTask` plugin registered in `tasks/registry.py`.”

---

## 6. Task 1 — Sorting (§5.1)

### What a thought *is*

- **Content:** `list[int]` — same numbers (multiset), hopefully sorted.
- **Source of truth for scoring:** `metadata["source_multiset"]` (the original unsorted chunk, or concat after merges).

### Split

- Contiguous slices of length `chunk_size` (default **8** for demo; paper-style 48 numbers → 6 chunks).

### Generate

- Prompt: sort this list ascending; **preserve frequencies** (duplicates matter).
- Output: sorted list (parsed from LLM text).

### Aggregate

- Prompt: merge-sort style merge of two **already sorted** lists.
- Metadata: `source_multiset` = concatenation of both parents’ sources.
- Graph: **two parents → one child**.

### Score (paper-style error scope)

We implement:

- **X** = adjacent inversions (out-of-order neighboring pairs).
- **Y** = frequency mismatch vs source multiset (wrong counts / missing / extras).
- `error_scope ≈ X + Y`.
- Score rises when error falls (roughly length − error for the demo).

### Refine

- Fires when `error_scope > 0`.
- LLM asked to fix given the error description.
- **Fallback:** `sorted(source_multiset)` — exact correct sort of the true bag of numbers.

### Final check

- `evaluate_result`: compare final content to `sorted(raw_input)` → `correct: true/false`.

### Tiny dry run (memorize)

Input: `[4, 1, 3, 2, 8, 5, 7, 6]`, `chunk_size=4`, `k=2`.

1. **Seed:** S0=`[4,1,3,2]`, S1=`[8,5,7,6]`.
2. **Generate on S0:** G0a=`[1,2,3,4]` (good), G0b=`[1,3,2,4]` (inversion) → Score/Refine/KeepBest → keep G0a.
3. Same on S1 → best1=`[5,6,7,8]`.
4. **Aggregate:** parents best0 + best1 → child `[1,2,3,4,5,6,7,8]` (multi-parent).
5. Final = sorted full list; `correct=true`.

**If they ask “why not just sorted()?”**  
“The demo *uses* deterministic fallback inside Refine, but the *reasoning structure* — decompose, generate alternatives, score, refine, aggregate with multi-parent merges — is what we are graded on. Sorting is the clearest paper workload to show that structure.”

---

## 7. Task 2 — Keyword counting (§5.3)

### What a thought *is*

- **Content:** `dict[str, int]` — e.g. `{"France": 2, "Germany": 1}` (zeros omitted).
- **Source:** `metadata["source_passage"]` for local scoring; full text for final eval.

### Split

- Split prose into sentences; group ~`chunk_size` sentences per passage.

### Generate

- Count listed countries (keywords) in **this passage only** → JSON object.

### Aggregate

- **Sum** counts for the same keys: `{France:1} + {France:1,Germany:1} → {France:2,Germany:1}`.

### Score / Refine

- Ground truth: regex word-boundary counts on the passage (`\bFrance\b`, …).
- `error_scope = Σ |predicted − truth|` over keys.
- Refine if any mismatch.
- **Fallback:** recompute exact counts with the same regex.

### Tiny dry run

Passages:

- P0: “France grew. Germany declined.” → truth `{France:1, Germany:1}`
- P1: “France recovered. Spain rose.” → truth `{France:1}`

Generate → KeepBest each → Aggregate sums → `{France:2, Germany:1}`.

**Viva tip:** Emphasize Aggregate is **addition of histograms**, not concatenation of text.

---

## 8. Task 3 — Set intersection (§5.2)

### What a thought *is*

- **Content:** sorted unique list — elements in the intersection.
- **Critical metadata:**
  - `set_a` — full set A (copied onto every seed).
  - `source_chunk` — the **subset of B** for this leaf (must be the **list**, not the chunk index).

### Split

- Chunk **set B** into subsets; A stays whole in metadata.

### Why chunking B is valid (say this)

\[
A \cap B = \bigcup_i (A \cap B_i)
\]

So:

- **Generate** = compute \(A \cap B_i\) for one subset.
- **Aggregate** = **union** of partial intersections (then unique + sort) — *not* intersect-the-partials.

### Score / Refine

- Expected = `set(A) ∩ set(source_chunk)` at leaves; full \(A\cap B\) at the end.
- `error_scope = |extra| + |missing|`.
- **Fallback:** exact set arithmetic.

### Tiny dry run

- A = `[1,2,3,4,5]`
- B = `[2,4,6,8,3,9]`, `chunk_size=3`
- B0=`[2,4,6]` → Generate → `[2,4]` (6∉A)
- B1=`[8,3,9]` → Generate → maybe wrongly `[3,8]` → Refine → `[3]`
- Aggregate → `{2,4} ∪ {3}` = `[2,3,4]`

**Bug we fixed (good marks if mentioned briefly):**  
Early bug stored chunk **index** in `source_chunk` → `'int' object is not iterable` during scoring. Fix: always store the subset **list**.

---

## 9. Task 4 — Document merging (§5.4)

### What a thought *is*

- **Content:** plain-text **bullet list** string (`- clause\n- clause`).
- **Source:** document text in `source_passage` / `all_documents`.

### Split

- Each uploaded `.txt`/`.md` is typically one seed (`chunk_size=1`).
- UI requires **≥ 2** files so Aggregate can fire.
- Filenames prefixed (`[nda-a.txt] …`) so seeds stay identifiable.

### Generate

- Rewrite one NDA excerpt into distinct obligation bullets (legal meaning preserved).

### Aggregate

- Merge two drafts: remove duplicated ideas, keep unique points → one coherent clause list.
- Multi-parent merge of documents = “combine partial NDAs into one.”

### Score / Refine

- Soft metrics (text is subjective):
  - **duplicates** among normalized bullets,
  - **coverage** of source content-words in the merge.
- Refine if duplicates > 0 or coverage &lt; ~0.55.
- **Fallback:** deterministic near-duplicate line collapse.

### Tiny dry run (3 files — shows odd-leaf promotion)

1. Seeds D0, D1, D2 (three NDAs).
2. Generate → E0, E1, E2 (bullet drafts).
3. Aggregate L0: E0+E1 → M01; **E2 promoted** (no pair).
4. Aggregate L1: M01+E2 → final merged NDA bullets.

**Viva tip:** Point at the graph: first diamond (2 docs), then second diamond pulls in the third.

---

## 10. Side-by-side cheat sheet (print / keep open)

| | Sorting | Keywords | Set ∩ | Docs |
|-|---------|----------|-------|------|
| Content | `list[int]` | `{kw: count}` | sorted list | bullet string |
| Chunk | number slices | sentence groups | subsets of **B** | documents |
| Generate | sort | count in passage | A∩Bi | extract clauses |
| Aggregate | merge-sort lists | **sum** counts | **union** partial ∩ | dedupe-merge text |
| Score core | inversions + freq | count L1 error | extra+missing | dupes + coverage |
| Fallback | `sorted(source)` | regex recount | set math | line dedupe |
| Final “correct?” | exact vs `sorted(input)` | vs full-text counts | vs `A∩B` | softer / coverage |

---

## 11. End-to-end path when you click Run

```
Frontend POST /run { task, payload, … }
  → FastAPI starts background thread
  → GoTLogger (JSONL + SSE + optional Supabase)
  → LLMClient (Groq, 30 RPM pacing, 429 retry)
  → create_task(task) → BaseTask plugin
  → GraphOfOperations.run
       build_decompose_merge_plan
       for each GoOStep: execute → update registry
  → evaluate_result → run_end
  → UI React Flow + metrics + download .txt/.md
```

You can say: “The live UI is SSE of the same events we write to JSONL.”

---

## 12. Likely viva questions — short model answers

**Q: How is this Graph of Thoughts, not Tree of Thoughts?**  
A: ToT = tree (one parent). We create **Aggregate** nodes with **multiple parents**. The React Flow graph shows those diamonds.

**Q: Is the plan dynamic?**  
A: No. GoO is built **once** from the number of chunks (static sequence). The *graph of thoughts* grows as we execute. Controller walks the plan and fills the GRS.

**Q: Why Refine if you have a deterministic fallback?**  
A: Paper pattern: detect error → try LLM fix → fall back. Fallback guarantees progress when the model fails; LLM path shows the transformation.

**Q: Where does scoring happen — LLM judge?**  
A: No. Scoring is **programmatic** per task (`score_details`). The LLM proposes; the evaluator ranks.

**Q: Why k=2 not paper’s larger k?**  
A: Cost and Groq free-tier RPM (30). Structure is identical; k is a parameter.

**Q: What if Aggregate gets one input?**  
A: Plan pairs keys; odd one is promoted. Aggregate step itself expects ≥2 thoughts when it runs on a pair.

**Q: Did you use an agent framework?**  
A: No. Pure Python + FastAPI + httpx Groq + React Flow.

**Q: How do the four tasks share code?**  
A: One GoO builder + one operations module + `BaseTask` plugins in a registry.

**Q: What breaks if metadata is wrong?**  
A: Scoring. Example: set ∩ needs `source_chunk` as the subset list; we hit that bug and fixed it.

---

## 13. What to demo live (2–3 minutes)

1. **Sorting** — run small n; show Generate branches, KeepBest prune, Aggregate diamond, final list.  
2. **Set ∩ or Keywords** — show Aggregate semantics (union vs sum) in the node inspector.  
3. **Docs** — upload 3 sample NDAs; show odd-leaf promotion then final merge; download `.md`.  
4. Optional: Table Editor `got_events` filtered by `run_id` — same events as JSONL.

---

## 14. Code map (if they ask “where?”)

| Piece | Path |
|-------|------|
| Thought | `backend/engine/thought.py` |
| Graph | `backend/engine/graph.py` |
| Operations | `backend/engine/operations.py` |
| GoO controller / plan | `backend/engine/graph_of_operations.py` |
| Logger / SSE events | `backend/engine/logger.py` |
| Plugin contract | `backend/tasks/base_task.py` |
| Registry | `backend/tasks/registry.py` |
| Sorting | `backend/tasks/sorting_task.py` |
| Keywords | `backend/tasks/keyword_counting_task.py` |
| Set ∩ | `backend/tasks/set_intersection_task.py` |
| Docs | `backend/tasks/document_merging_task.py` |
| API | `backend/api/server.py` |
| Live graph UI | `frontend/src/components/GraphVisualizer.tsx` |

---

## 15. Closing sentence (use at the end of your answer)

> “Across all four tasks the **reasoning structure is identical** — decompose, generate alternatives, score, refine, keep best, aggregate with multi-parent merges — and only the **thought content algebra** changes: sorted lists, count dictionaries, set unions, or merged clause text.”

That sentence is the thesis. Everything above is evidence.
