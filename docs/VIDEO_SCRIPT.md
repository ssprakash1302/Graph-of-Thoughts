# VIDEO_SCRIPT.md — 8–12 min GoT walkthrough

**Target length:** ~10 minutes (hard window 8–12).  
**Tone:** viva / spoken bullets — do **not** read paragraphs aloud.  
**Verified against:** live CLI run `video-sort-demo` (2026-08-13), `backend/engine/*`, `backend/tasks/*`, `frontend/src/components/*`, `backend/README.md` deviations table.

**Hero sorting demo (reproducible):**

```bash
cd got-project/backend
.\.venv\Scripts\Activate.ps1
python run_cli.py --task sorting --list "4,1,3,2,8,5,7,6,9,0,2,1,5,4,3,8" --chunk-size 8 --generate-k 2 --aggregate-k 2 --run-id video-sort-demo
```

| Fact from that run | Value |
|--------------------|--------|
| Elapsed | **~11 s** |
| Input | `[4,1,3,2,8,5,7,6,9,0,2,1,5,4,3,8]` |
| Final / truth | `[0,1,1,2,2,3,3,4,4,5,5,6,7,8,8,9]` · `correct: True` |
| **Merge (hero)** | `Aggregate merge ['84193e80','337b4ed5'] → faec174d (nodes 6 → 8)` |
| Parents | two independent KeepBest winners from chunk 0 and chunk 1 |
| FIDELITY CHECKS | merges **1** · refine corrections **0** · KeepBest active drops **3** |

> **Important (say accurately on camera):** `nodes 6 → 8` is **total graph nodes** after Aggregate adds `k_attempts=2` children. The paper “saving” / efficiency moment is clearer on **KeepBest** lines: e.g. `active 6 → 5`. Still point at the merge line for **two parents → one child** (ToT cannot do that).

**Refine backup:** this short run had **0** refine fixes (LLM sorted both chunks perfectly). Keep `logs/api-d83b4fd9.jsonl` open — it has real `refine` / `llm_fixed` lines (e.g. frequency mismatch Y=1). Or pre-record a full `n=48` UI sorting run (~45–60 s with RPM pacing).

---

## [0:00] Cold open / hook (~20 s)

**[SHOW:** App masthead `Graph of Thoughts` · or IDE title bar over `got-project/`]

Say:

- We implemented **Graph of Thoughts** from Besta et al., **AAAI 2024** — from scratch, no agent framework.
- GoT is graph reasoning: LLM thoughts can **branch and merge** — not just a tree like Tree of Thoughts.
- Multi-parent **Aggregate** is the differentiator.
- In the next ~10 minutes: live engine, paper ops in code, a real merge with logged node counts, then the same engine on other paper tasks, plus our documented deviations.

---

## [0:25] Paper → code mapping (~90 s) — fidelity 30%

**[SHOW:** split IDE — `operations.py` + `graph_of_operations.py`]

Say:

- Paper ops we implement: **Generate, Aggregate, Refine, Score, KeepBest**, driven by a **Graph of Operations (GoO)** controller.
- Point, briefly:

| Paper piece | File · what to highlight |
|-------------|---------------------------|
| Thought node | `engine/thought.py` — `Thought` dataclass: `content`, `parents`, `score`, `active` |
| Graph / GRS | `engine/graph.py` — `add_node` / `add_edge` / `record_merge_counts` |
| Generate | `operations.py` · `class Generate` · `execute` — 1 parent → k children |
| Aggregate | `operations.py` · `class Aggregate` · `execute` — **≥2 parents**, `graph.add_edge` each → child; `logger.merge_event(...)` |
| Refine | `operations.py` · `class Refine` — `detect_error` → LLM → `fallback_fixed` |
| Score | `operations.py` · `class Score` — calls `task.score_details` |
| KeepBest | `operations.py` · `class KeepBest` — prune; logs `active N → M` |
| GoO plan | `graph_of_operations.py` · `build_decompose_merge_plan` — Seed → Gen→Score→Refine→Score→KeepBest → Aggregate ladder |

One line:

- Controller walks a **static plan**; the **graph of thoughts** grows as we execute.

Do **not** linger — cut to live run.

---

## [2:00] Live run #1 — sorting (~2.5 min) — implementation 40% + paper merge bar

### Option A (recommended for pacing) — CLI hero (~11 s)

**[SHOW:** terminal in `backend/` with venv on]

1. Paste the hero command above; hit enter.
2. Narrate while it runs (don’t wait in silence):

- Two **Seeds** — chunks of 8: `[4,1,3,2,8,5,7,6]` and `[9,0,2,1,5,4,3,8]`.
- **Generate k=2** per chunk → Score → Refine (may no-op if perfect) → **KeepBest** keeps one winner per chunk.
- Watch for **Pacing Groq** sleeps — free tier ~30 RPM; expected, not a hang.

3. **Hero moment — freeze / scroll to merge line:**

```
Aggregate merge ['84193e80', '337b4ed5'] → faec174d (nodes 6 → 8)
```

Say explicitly:

- Two **independent** branch winners (`84193e80` from chunk 0, `337b4ed5` from chunk 1) converge into **one** Aggregate child.
- Logged **node count before/after** on that merge: **6 → 8** (total nodes; Aggregate created two candidates because `aggregate_k=2`).
- Immediately show a KeepBest prune, e.g. `active 6 → 5` — that’s where the active set shrinks.

4. Scroll to end:

```
FIDELITY CHECKS
  multi-parent Aggregate merges: 1
  refine corrections:            0
  KeepBest active-count drops:   3
RESULT … correct: True  score=16.0
```

5. Optional 10 s: open `logs/video-sort-demo.graph.json` or click the Aggregate node in the UI if you mirrored the same list — show **`N parents → merge`** badge on multi-parent nodes (`GraphVisualizer.tsx`).

### Option B (UI, longer) — only if you want the visual graph live

**[SHOW:** http://127.0.0.1:5173 · uvicorn + `npm run dev`]

- Mission control → **Sorting** tile (`RunControls`).
- Paste the same 16 numbers; chunk **8**; Generate k **2** / Aggregate k **2** → **Run GoT**.
- Narrate HUD chips: **nodes / active / merges / refines / prune** (`MetricsPanel`).
- Click Aggregate node → **Node inspector**: parents length **2**, op `Aggregate`.
- **Backup:** if Groq is slow, cut to a pre-recorded ~11 s CLI clip of Option A (same numbers).

### If Refine didn’t fire

**[SHOW:** `logs/api-d83b4fd9.jsonl` search `refine`]

- “On this short perfect run Refine didn’t need to fix anything — corrections **0**. Here’s a prior full run where Refine fired `llm_fixed` on a frequency mismatch.” Point at one real line, then move on.

---

## [4:30] Architecture / code quality (~60 s) — code quality 20%

**[SHOW:** explorer `backend/engine/` vs `backend/tasks/` · open `base_task.py` + `registry.py`]

Say:

- **`engine/`** never imports a concrete task by name for the plan — operations take a `BaseTask`.
- **`tasks/`** = plugins: prompts, parsers, score, `split_input`, Refine fallback.
- Concrete clean-structure example: abstract **`BaseTask`** (`generate_prompt`, `aggregate_prompt`, `score`, `detect_error`, `refine`, `split_input`, …).
- Registry maps string ids → classes: `sorting`, `keyword_counting`, `set_intersection`, `document_merging` — add a task without rewriting GoO.

One line:

- Same GoO; different “thought algebra.”

---

## [5:30] Prove generality — other tasks (~2 min)

Stay in the UI. Don’t full-narrate a 48-number ladder again.

### Keywords (~40 s)

**[SHOW:** task tile **Keywords** · leave demo passage]

- Same engine. Aggregate for this task = **sum count dictionaries** (`keyword_counting_task.aggregate` / Aggregate prompt: merge JSON by summing keys).
- Hit **Run GoT** (or cut to a 20–30 s sped clip). Point at final JSON in inspector / result; HUD **merges** > 0.

### Set ∩ (~40 s)

**[SHOW:** **Set ∩** · demo JSON from “Load demo” / default]

- Chunk **B**; intersect each subset with **A**; Aggregate = **union of partial intersections** (`scope: union_of_partial_intersections` in code).
- One sentence: \(A\cap B=\bigcup_i(A\cap B_i)\).
- Brief run or clip; click a multi-parent Aggregate node.

### Docs (~40 s) — optional third if time; else swap with Set

**[SHOW:** **Docs** · upload ≥2 from `got-project/samples/`  
`nda-confidentiality.txt`, `nda-return-destroy.txt`, (`nda-affiliates-publicity.txt`)]

- Aggregate = **dedupe-merge clause drafts** into one bullet list (LLM + deterministic dedupe hint).
- Need **≥2** files or Aggregate never pairs.
- After run: header **Download .md** if you want a 5 s product beat.

**Cut rule:** 2 tasks minimum for generality; 3 if still under ~8:00.

---

## [8:00] Documented deviations (~45 s)

**[SHOW:** `backend/README.md` § Design notes / deviations — do not invent extras]

Spoken (one breath each):

- Generate **k=2** not paper’s typical **k=3** — fewer Groq calls for the assessment; overridable.
- Aggregate attempts **k=2** not ~**10** — same cost tradeoff; overridable.
- KeepBest **N=1** — matches common paper KeepBest(1).
- Sorting demo often **48 / chunk 8**; today’s hero used **16 / 8** for a fast merge on camera.
- Document merging score is **heuristic** (duplicates + coverage) — no single gold NDA.
- LLM = **Groq** via httpx — course/API choice, not the paper’s original stack.
- **No** LangChain etc. — hand-written GoO/GRS required.

Then:

- Structure unchanged: decompose → Generate → Score → Refine → KeepBest → multi-parent Aggregate; sorting still uses error-scope **X+Y**.

---

## [9:00] “What would break if we removed X” (~45 s)

**Pick: Refine** (true from `operations.py` + `sorting_task.detect_error` / `refine`).

Say:

- If we **removed Refine**, imperfect Generate/Aggregate thoughts with `error_scope > 0` would **stay wrong** through to KeepBest.
- KeepBest only compares scores — it does **not** fix content. A bad sort with a slightly higher score could win, or two bad candidates compete without correction.
- Our Refine path is: detect → LLM fix → deterministic **`sorted(source_multiset)`** fallback — without that path, frequency/order bugs persist into Aggregate and the final `correct: false` risk rises.
- (Optional 5 s) Point at `api-d83b4fd9` refine line: before wrong frequencies → after `llm_fixed`.

**Alt if asked:** remove **Aggregate** → graph becomes ToT-like trees; no multi-parent convergence; paper claim fails on screen.

---

## [9:45] Wrap-up (~20 s)

Say:

- We showed a real GoT engine: Generate / Aggregate / Refine / Score / KeepBest under a GoO, with a logged multi-parent merge and node counts.
- Same engine drives sorting, keyword sums, set unions, and document merges — not a sorting trick.
- Deviations are explicit and justified; core paper mechanism is intact.

**[Optional team line — only if natural]**  
“Implementation and walkthrough by our team — engine/tasks split, UI, and logging as in the repo.”

End. Stop recording.

---

## Grading coverage map (for your own check)

| Criterion | Where in this script |
|-----------|----------------------|
| Working E2E (40%) | [2:00] live sort → `correct: True` |
| Fidelity (30%) | [0:25] ops+files · [2:00] merge+counts · [8:00] README deviations |
| Code quality (20%) | [4:30] engine vs tasks · BaseTask |
| Explanation | Whole script · [9:00] remove Refine |

---

## Pre-recording checklist

1. **Backend:** `backend/.env` has a valid `GROQ_API_KEY`; venv activated; `uvicorn` on `127.0.0.1:8000` if using UI.
2. **Frontend:** `npm run dev` → http://127.0.0.1:5173; confirm Mission control tiles: Sorting / Keywords / Set ∩ / Docs.
3. **Dry-run hero once:** run the exact `video-sort-demo` command; confirm merge line and `correct: True` (~11 s). If merge fails (Aggregate skipped), you don’t have ≥2 distinct parents — re-run; don’t invent numbers.
4. **Refine backup ready:** `logs/api-d83b4fd9.jsonl` (or a fresh `n=48` recording) — short demo often has **0** refines.
5. **Pre-record backup clip** of the 11 s CLI sort (and optionally one keyword + one set run) in case live Groq 429/pacing blows the clock. Prefer cut-to-clip over dead air.
6. **IDE windows queued:** `operations.py` (Aggregate + Refine), `graph_of_operations.py` (`build_decompose_merge_plan`), `base_task.py`, `registry.py`, `README.md` deviations table.
7. **Samples path:** `got-project/samples/*.txt` for Docs (≥2 files).
8. **Screen hygiene:** close unrelated tabs; zoom terminal to ~120% so `nodes 6 → 8` and FIDELITY CHECKS are readable; hide `.env` secrets if sharing screen.
9. **Supabase:** skip unless you have ≥30 s spare — if shown, filter Table Editor by `run_id` (don’t rely on page-1 ascending ids).
10. **Decide hero merge in advance:** use the CLI 16-number run (fast, one clear merge). Use UI `n=48` only if you accept ~45–60 s and a pre-recorded cutaway.
11. **Do not claim** Aggregate reduces total node count on the merge line — our logger records **total nodes after adding candidates**. Pair merge (multi-parent) + KeepBest **active** drop for the efficiency story.
12. **Stopwatch:** cold open ≤20 s; leave ≥45 s for deviations + “remove Refine” + wrap.
