# How Keyword Counting, Set Intersection, and Document Merging Are Implemented

**Audience:** teammate / assessor who already knows we implemented Graph of Thoughts (Besta et al., AAAI 2024) for sorting, and needs the other three paper use-cases explained in depth.

**Scope:** these three plugins only. Sorting is mentioned only where the shared engine matters.

**Code map**

| Piece | Path |
|--------|------|
| Plugin contract | `backend/tasks/base_task.py` |
| Registry (name → class) | `backend/tasks/registry.py` |
| Keyword counting §5.3 | `backend/tasks/keyword_counting_task.py` |
| Set intersection §5.2 | `backend/tasks/set_intersection_task.py` |
| Document merging §5.4 | `backend/tasks/document_merging_task.py` |
| Shared GoO controller | `backend/engine/graph_of_operations.py` |
| Generate / Aggregate / Refine / Score / KeepBest | `backend/engine/operations.py` |
| Download / export helpers | `frontend/src/exportResult.ts`, `frontend/src/components/ResultExport.tsx` |
| Multi-file upload (Docs) | `frontend/src/components/RunControls.tsx` |
| Groq pacing + 429 retry | `backend/engine/llm_client.py` |

---

## New features we shipped (read this first)

These landed **on top of** the three plugins. Mention them when you update the team — they are what make the demo feel like a product, not just four Python classes.

### 1. Download the output as `.txt` or `.md`  ← new

After a run finishes (`status === completed` and `final_content` exists):

| Where | What |
|--------|------|
| **Header** (top-right, next to the LIVE ring) | **Download .txt** and **Download .md** |
| **Left rail → Export** | Same two buttons for the **final** thought |
| **Left rail → Export** | **This node .txt** if you have a graph node selected |

**How it works**

- `frontend/src/exportResult.ts`
  - `contentToText()` — strings (and `\\n` → real newlines), arrays as one item per line, objects as pretty JSON
  - `contentToMarkdown()` — wraps with `# GoT <task> · <timestamp>`; if lines already look like bullets, keeps them; otherwise prefixes `- `
  - `exportResult(result, "txt" | "md")` — browser `Blob` + `<a download>`
- Filenames look like `document_merging-merged-2026-08-11-11-20-03.md`

Works for **all four tasks**, not only Docs (sorting downloads the final list, keywords the count JSON, sets the intersection list). Docs is where it matters most for the viva.

**Demo line:** *“We don’t just visualize the merge — you can take the final NDA out as markdown.”*

### 2. Multi-file upload for document merging  ← new

Docs is no longer paste-only.

- Drag-and-drop or click zone (`.txt` / `.md`)
- File chips: name, size, word count, **Remove**
- Caps: 12 files, 80KB each (keeps Groq context sane)
- Payload sent to the API:

```json
{ "documents": [ { "name": "nda-a.txt", "text": "..." }, ... ] }
```

Backend `_normalize_docs()` prefixes `[filename]` so Seeds stay identifiable in the graph.

- Need **≥ 2** files for Aggregate to fire
- Paste-with-`---` still works if you upload nothing
- Sample NDAs: `got-project/samples/nda-confidentiality.txt`, `nda-return-destroy.txt`, `nda-affiliates-publicity.txt`

### 3. Task switcher in the UI

Mission Control has four tiles: **Sorting / Keywords / Set ∩ / Docs**. Each one swaps the input panel and default chunk size. Same engine, different payload. (`RunControls.tsx` + `POST /run` `{ task, payload }`).

### 4. Redesigned live visualizer (assessment video)

Not default Bootstrap. Signal-lab look:

- Unbounded / Manrope / JetBrains Mono
- Copper + cyan + signal-lime (Generate / Aggregate / Refine color-coded)
- Graph-first React Flow stage + MiniMap
- HUD chips with spring count-ups (nodes, merges, refines, prune N→M)
- Merge / Refine **shockwaves** on the stage + node pulse
- Flight recorder: spring-in log lines
- Click a node → inspector (content, score, multi-parent badge)

### 5. Groq rate-limit handling

Free `llama-3.3-70b-versatile` = **30 RPM**. A full GoT run exceeds that.

- `GROQ_RPM=30` paces ~2s between calls
- HTTP 429: parse “try again in Xs” / `Retry-After`, wait, retry (up to 6)
- Runs are slower; they should **finish** instead of dying mid-Aggregate

### 6. Stability fixes that were real demo-breakers

Worth naming so the team doesn’t think the tasks are flaky:

| Symptom | Task | Cause | Fix |
|---------|------|--------|-----|
| `Aggregate expects at least two input thoughts` | Keywords | Generate k=2 reused one node; KeepBest discarded that same id | Dedupe by id in Generate + KeepBest |
| `'int' object is not iterable` | Set ∩ | `source_chunk` was the chunk **index** | Store the subset **list**; index in `chunk_index` |
| `'dict' object has no attribute 'lower'` | Docs | After KeepBest, `evaluate_result` scored raw `{name,text}` dicts | Normalize to strings first |
| ImportError `OpenAI` | all | System Python’s broken `openai` package | Plain `httpx` Groq client; use the venv |

### 7. CLI / API extras

```bash
python run_cli.py --list-tasks
python run_cli.py --task keyword_counting --chunk-size 2
python run_cli.py --task set_intersection
python run_cli.py --task document_merging
```

- `GET /tasks` — plugin list for the UI
- `POST /run` accepts `task` + `payload` (uploads, sets JSON, keyword text)
- Logs still land in `backend/logs/<run_id>.jsonl` + `.graph.json` + `.result.json`

---

## 1. Why these three tasks exist

The paper’s claim is that GoT is a **general** graph reasoning framework, not a sorting trick. Section 5 gives four workloads that all share the same shape:

1. **Decompose** the problem into subproblems.
2. **Generate** LLM thoughts on each piece.
3. **Score** + **KeepBest** (and **Refine** when wrong).
4. **Aggregate** partial thoughts into a larger one (multi-parent edges — this is what Tree of Thoughts cannot express).

Sorting was the first plugin. These three prove the engine is task-agnostic: **the Graph of Operations does not change**. Only prompts, parsers, scores, and how we split/merge *content* change.

That is the sentence to say in the video / viva: *“GoT is the engine; each paper use-case is a `BaseTask` plugin.”*

---

## 2. Shared architecture (read this once)

### 2.1 `BaseTask` — what every plugin must implement

The engine never imports `KeywordCountingTask` etc. It only calls the interface:

**LLM side**

- `generate_prompt(thought)` — one parent → new thought
- `aggregate_prompt(thoughts)` — k parents → one merged thought
- `refine_prompt(thought, error)` — feedback loop
- `parse_generate` / `parse_aggregate` / `parse_refine` — turn messy LLM text into typed content

**Evaluation / graph**

- `split_input(data, chunk_size)` — how this task decomposes
- `aggregate(thoughts)` — structural merge (signature + metadata); LLM parse overwrites content
- `score` / `score_details` — higher is better; must include `score` and usually `error_scope`
- `detect_error` — `None` if OK, else a human-readable reason (drives Refine)
- `refine` — **deterministic fallback** if the LLM refine reply fails to parse
- `is_equivalent` / `state_signature_for` — merge-detection / reuse
- `seed_metadata` — what we stash on Seed nodes (passage, set A, filenames, …)
- `evaluate_result` — final `correct` / `ground_truth` after the GoO finishes
- `make_demo_input` — CLI/UI demo payload

### 2.2 One Graph of Operations for all four tasks

`GraphOfOperations.build_decompose_merge_plan()` builds the **same static plan** for every plugin:

```
for each chunk from task.split_input():
    Seed
    Generate(k)          # default k=2 (paper often uses 3)
    Score
    Refine               # skipped if error_scope == 0
    Score
    KeepBest(N=1)

while more than one surviving branch:
    pairwise Aggregate(k_attempts=2)   # paper often uses 10
    Score → Refine → Score → KeepBest
```

That ladder is the paper’s “mirrored tree” / merge-sort-shaped GoO. Demo k=2/2 is a documented cost tradeoff (`GOT_GENERATE_K`, `GOT_AGGREGATE_K`), not a different algorithm.

**Graph edges**

- Generate: 1 parent → k children
- Aggregate: **2+ parents → 1 child** (logged as `merge`)
- Refine: parent → corrected child, parent marked discarded
- KeepBest: lower-scoring siblings marked discarded (active count N → M)

### 2.3 How a run is wired (CLI / API / UI)

```
UI or CLI
  → task id + payload
  → tasks.registry.create_task(task_id, raw_input)
  → GraphOfOperations(task=..., llm=Groq, logger=...)
  → goo.run(raw_input, chunk_size)
```

| Task id | Default chunk | Meaning of chunk |
|---------|---------------|------------------|
| `keyword_counting` | 2 | sentences per passage |
| `set_intersection` | 8 | elements of set B per subset |
| `document_merging` | 1 | one uploaded file / doc per seed |

CLI:

```bash
python run_cli.py --task keyword_counting --chunk-size 2
python run_cli.py --task set_intersection
python run_cli.py --task document_merging
```

API: `POST /run` with `{ "task": "...", "payload": { ... }, "chunk_size": ... }`.

### 2.4 What the LLM actually does vs what Python does

| Step | LLM | Python |
|------|-----|--------|
| Split | no | `split_input` |
| Generate | yes — produce partial answer | parse + attach metadata |
| Score | no | deterministic `score_details` |
| Refine | yes first, then fallback | `detect_error` decides; `refine()` is exact local fix |
| Aggregate | yes — merge partials | `aggregate()` builds multi-parent thought + signature |
| KeepBest | no | rank by score, discard losers |

We do **not** call `sorted()` / set intersection / word counts as the *solution path*. Those functions exist as **scorers and fallbacks**, same spirit as the paper’s local scoring for sorting.

---

## 3. Keyword counting (paper §5.3)

**File:** `backend/tasks/keyword_counting_task.py`  
**Class:** `KeywordCountingTask`  
**Name:** `keyword_counting`

### 3.1 Paper idea

Split a document into passages, count keywords (countries, in the paper and here) in each passage with the LLM, then **Aggregate by summing counts**. Score = total absolute deviation from true counts.

### 3.2 Input

```json
{ "text": "...", "keywords": ["France", "Germany", ...] }
```

If `keywords` is omitted, we use a fixed 15-country list (`DEFAULT_KEYWORDS`). Demo text is `DEMO_TEXT` (several sentences that mention those countries, including repeats — so summing actually matters).

UI: textarea of prose. CLI: `--task keyword_counting` uses the demo text.

### 3.3 Decomposition

`split_input`:

1. Split on sentence boundaries: `(?<=[.!?])\s+`
2. Group `chunk_size` sentences into one passage (default **2**)

Each passage becomes a **Seed** thought. Content = the passage string. Metadata:

```python
role = "passage"
source_passage = chunk   # used later for local ground truth
keywords = [...]
```

### 3.4 Generate

Prompt: count each country in **this passage only**; return JSON `{ "France": 2, ... }`; omit zeros.

Parse (`_parse_counts`):

- Extract `{...}` from the reply
- `json.loads`, else `ast.literal_eval`
- Canonicalize keys via case-insensitive map (`france` → `France`)
- Drop zero counts

Thought **content type:** `dict[str, int]`.

**State signature** for a generated thought: `("passage", source_passage)` — two attempts on the same passage are equivalent *scopes*. If they also have identical content, Generate **reuses** the node (node-count savings). That reuse is why KeepBest must dedupe by id (see §7).

### 3.5 Score (paper-style error-scope)

Local truth: regex `\bkeyword\b` on the passage (or full text if no `source_passage`).

```
error_scope = Σ_k |predicted[k] − truth[k]|
score       = max(total_true_mentions − error_scope, 0)
```

Higher score = better. `error_scope == 0` ⇒ Refine is skipped.

### 3.6 Refine

- LLM path: “these counts are wrong; recompute JSON for this passage.”
- Fallback: `ground_truth_counts(passage)` — exact local recount.

Logged as `llm_fixed` or `fallback_fixed`.

### 3.7 Aggregate (the GoT part)

Pairwise merge of count dicts.

- LLM is asked to **sum** the two JSON objects.
- Structural `aggregate()` does `Counter` addition for signature/metadata.
- Child has **two parents** → orange merge edges in the UI.
- After the ladder, one dict should equal full-document counts.

Final `evaluate_result`: `pred == ground_truth_counts(full_text)`.

### 3.8 What to show a teammate / assessor

- Several Seed passages, not one blob.
- Generate nodes whose content is JSON counts, not the original sentence.
- At least one Aggregate with **two parent IDs**.
- Metrics: merges > 0; if the model miscounts a passage, a Refine flash.

### 3.9 Known footgun (fixed)

Generate k=2 often returns the **same** JSON twice. We reused one node and passed `[A, A]` into KeepBest(N=1), which discarded `A` (the duplicate slot). The next Aggregate then saw &lt; 2 live parents. **Fix:** unique-by-id in Generate outputs and KeepBest.

---

## 4. Set intersection (paper §5.2)

**File:** `backend/tasks/set_intersection_task.py`  
**Class:** `SetIntersectionTask`  
**Name:** `set_intersection`

### 4.1 Paper idea

Intersection of A and B is hard for LLMs on long lists (missing/extra elements). GoT **splits B** into subsets, intersects each subset with **full A**, then **Aggregates by union**. Score = extras + missing (+ duplicates in the paper; we unique on parse).

### 4.2 Input

```json
{ "set_a": [1, 2, 5, ...], "set_b": [2, 9, 5, ...] }
```

Demo (`make_demo_input`): universe `0..79`, sample n=32 for A, B is ~50% overlap with A plus random outsiders, then shuffled.

UI: JSON textarea. Must be an **object with both keys**, not a bare array.

### 4.3 Decomposition

`split_input` **only chunks `set_b`**. `set_a` is copied onto every seed:

```python
role = "subset_b"
set_a = [...full A...]
source_chunk = [this slice of B]   # MUST be the list, not the index
```

Default chunk size 8 ⇒ e.g. 12-element B → 2 seeds.

### 4.4 Generate

Prompt: `A ∩ this subset of B`. Output a sorted JSON array, no dupes.

Parse: first `[...]` in the reply → unique + sorted.

Thought **content type:** `list` (the partial intersection).

**Signature:** `("intersect_scope", sorted(A), sorted(subset_B))` so two attempts on the same subset are the same problem.

### 4.5 Score

Paper-ish:

```
extra   = |pred − truth|
missing = |truth − pred|
error_scope = extra + missing
score = max(|truth| − error_scope, 0)
```

`truth` is **local**: `A ∩ source_chunk` for Generate/Refine nodes. After Aggregate, `source_chunk` is absent ⇒ truth is full `A ∩ B`.

### 4.6 Refine

- LLM: fix the array; if a subset is present, only that intersection.
- Fallback: exact `A ∩ scope` (or full intersection).

### 4.7 Aggregate

LLM: **union** the partial intersection lists, unique, sorted.

Python `aggregate()`: `set.union` of parent contents. Child parents = both partials. After the ladder, content should equal `sorted(set(A) & set(B))`.

`evaluate_result` compares that to `true_intersection()`.

### 4.8 What to show

- Seeds whose content is a **slice of B**, not A.
- Generate nodes that are shorter lists (only the overlap in that slice).
- Aggregate children with two parents whose lists **union** toward the full intersection.
- Inspector: `set_a` still on metadata.

### 4.9 Known footgun (fixed)

Generate used to write `source_chunk = chunk_index` (an **int**). Score then did `set(0)` → `'int' object is not iterable`. **Fix:** `source_chunk` is the actual subset list; index lives in `chunk_index`. `_expected_for` only intersects if `source_chunk` is a list/tuple/set.

---

## 5. Document merging (paper §5.4)

**File:** `backend/tasks/document_merging_task.py`  
**Class:** `DocumentMergingTask`  
**Name:** `document_merging`

### 5.1 Paper idea

Merge overlapping documents (NDAs in the paper) into one text: **minimize duplication, maximize information retained**. There is no single gold document, so scoring is heuristic (duplication + coverage), not exact equality like sort/sets.

### 5.2 Input (two shapes)

**Paste / demo**

```json
{ "documents": ["NDA-A: ...", "NDA-B: ..."] }
```

**Upload (UI)**

```json
{ "documents": [
    { "name": "nda-a.txt", "text": "..." },
    { "name": "nda-b.txt", "text": "..." }
]}
```

`_normalize_docs()` turns `{name, text}` into `"[filename]\n..."`. That is what Seeds see.

UI: drag/drop or click, `.txt` / `.md`, max 12 files, 80KB each. Need ≥2 files for a real merge. Sample files: `got-project/samples/*.txt`.

Chunk size default **1** = one file per Seed. Raising it concatenates consecutive docs into one seed (usually leave at 1).

### 5.3 Generate

Prompt: rewrite **this** excerpt as `- ` bullets of distinct clauses. Keep legal meaning. No preamble.

Parse (`_parse_bullets`): strip `-*•`, drop short “Here is…” preambles, force `- ` prefix.

Thought **content type:** `str` (markdown-ish bullet list).

### 5.4 Score (heuristic — say this out loud)

Not paper X+Y on numbers. Two terms:

1. **Duplicates:** identical normalized bullets (lowercase, punctuation stripped).
2. **Coverage:** fraction of source content-words (length ≥ 4) that appear in the merge.

```
error_scope = duplicates + round((1 − coverage) × 10)
score       = max(2 × n_bullets − error_scope, 0)
```

`detect_error` fires only if `duplicates > 0` or `coverage < 0.55` — otherwise Refine would fire on every decent draft.

Final `correct` in `evaluate_result`: `duplicates == 0` and `coverage >= 0.5`. There is **no** gold NDA; `ground_truth` is a note + source doc count.

### 5.5 Refine

- LLM: dedupe near-identical bullets, keep unique obligations.
- Fallback: `_deterministic_dedupe` (normalize line, drop exact and near-substring dupes).

### 5.6 Aggregate

LLM: merge two clause drafts into **one** list; delete duplicated ideas; keep unique points.

Python `aggregate()` concatenates then runs the same deterministic dedupe (structural hint). LLM parse replaces content. Child has **two parents** — this is “combining articles into a coherent summary” from the paper’s Figure 2, NDA flavour.

After the pairwise ladder, one bullet list should cover all uploads without repeating “Delaware / 3 years” four times.

### 5.7 Export / download (new feature — call this out)

This is the feature the team asked for after upload: **don’t leave the merge trapped in the graph**.

When the Docs run (or any task) completes:

1. Header buttons **Download .txt** / **Download .md**
2. Rail **Export** panel — same, plus **This node .txt** for the selected thought

Implementation is client-side only (no extra API): `exportResult.ts` builds a `Blob` from `result.final_content`. Markdown gets a title heading; bullet lists stay as markdown lists. Literal `\n` sequences from the model are turned into real line breaks so the downloaded file is readable.

Tell the teammate: *upload 3 NDAs → watch Aggregate → download the merged `.md`.* That loop is the Docs story.

### 5.8 What to show

- Four Seed nodes named after files.
- Generate = per-doc clause lists.
- Aggregate pulses when two lists become one.
- Download the merged NDA.
- Inspector on the final Aggregate: multiple parents.

### 5.9 Known footgun (fixed)

After KeepBest, `evaluate_result` used to assign `self.documents = raw_input["documents"]` (still **dicts**). Coverage then called `doc.lower()` → `'dict' object has no attribute 'lower'`. The graph was already done; only the final grade crashed. **Fix:** always `_normalize_docs` before scoring; coerce dicts in `_coverage_keys`.

---

## 6. Side-by-side (use this table in the report / slides)

| | Keyword counting | Set intersection | Document merging |
|--|------------------|------------------|------------------|
| Paper | §5.3 | §5.2 | §5.4 |
| Split | sentences → passages | **B** into subsets | one doc / file per seed |
| Generate content | `{country: count}` | `list` of overlap | bullet `str` |
| Aggregate means | **sum** counts | **union** of partial ∩ | **deduped clause merge** |
| Local score | L1 vs regex counts | extras + missing | dupes + coverage |
| Gold final? | yes (full-text counts) | yes (`A ∩ B`) | no (heuristic) |
| Default chunks | 2 sentences | 8 elements of B | 1 file |
| Extra UI | textarea | JSON `{set_a,set_b}` | multi-file upload + download |

All three use the **same** GoO ops. If someone asks “is this just three separate apps?” the answer is no — one controller, three `BaseTask`s.

---

## 7. Bugs we hit on these tasks (so the teammate does not re-litigate them)

1. **KeepBest + equivalent Generate (keywords)**  
   Same thought id twice → discarded the keeper → Aggregate “needs ≥2 thoughts”.  
   Fixed in `operations.py` (dedupe Generate outputs + KeepBest).

2. **`source_chunk` was an int (sets)**  
   Generate overwrote the subset list with `chunk_index`. Score did `set(0)`.  
   Fixed: keep the list in `source_chunk`, index in `chunk_index`.

3. **Upload dicts in `evaluate_result` (docs)**  
   `.lower()` on `{name, text}`.  
   Fixed: normalize to strings before coverage.

4. **Groq 429 (all tasks)**  
   30 RPM on `llama-3.3-70b-versatile`. Client now paces (`GROQ_RPM`) and waits on 429. Runs are slower; they should finish.

---

## 8. How to add a fourth plugin (for the teammate)

1. New file `backend/tasks/foo_task.py` implementing `BaseTask`.
2. Register in `TASK_REGISTRY` + `list_tasks()` + `create_task()` + `default_chunk_size()`.
3. Decide: what is a Seed? what does Generate return? what does Aggregate **combine** (sum / union / merge text)?
4. Write a **local** `score_details` + `detect_error` so Refine has something to do.
5. UI: add a tab in `RunControls.tsx` and a payload shape. **Do not touch** `engine/` unless you need a new operation type.

That last point is the design goal: engine stays a GoT machine; tasks stay interchangeable.

---

## 9. Suggested 90-second walkthrough for your teammate

1. Open the UI, pick **Keywords**, Run. Point at passage Seeds → count JSON → Aggregate sum. Mention §5.3.
2. Pick **Set ∩**, show `{set_a, set_b}`, Seeds = slices of B, Generate = local ∩, Aggregate = union. Mention §5.2 and the int/`source_chunk` bug if they ask why we were careful with metadata.
3. Pick **Docs**, drop `samples/*.txt` (upload chips appear), Run, click the final Aggregate (two parents), hit **Download .md** / **Download .txt** in the header or Export rail. Mention §5.4: no gold doc, score = dupes + coverage, and that export is a product feature on top of the paper.
4. If anyone asks about 429s: we pace Groq at 30 RPM; the run is slow on purpose.
5. One line: *same GoO, three plugins, multi-parent Aggregate is the GoT differentiator; upload + download is what we added so Docs is a real workflow.*
