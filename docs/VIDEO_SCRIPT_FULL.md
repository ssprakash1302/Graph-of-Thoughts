# VIDEO_SCRIPT_FULL.md — spoken teleprompter (UI-first)

**Speaking time:** ~9–11 minutes if read at a natural pace. Do at least one full **read-aloud rehearsal** before recording — silent reading always underestimates how long you take.

**Verified facts carried from** `docs/VIDEO_SCRIPT.md` and the live `video-sort-demo` CLI run.  
**Primary path:** live UI at http://127.0.0.1:5173 (uvicorn + `npm run dev`).  
**Hero sorting input (paste into Number list):**

`4, 1, 3, 2, 8, 5, 7, 6, 9, 0, 2, 1, 5, 4, 3, 8`

With **Chunk size 8**, **Generate k 2**, **Aggregate k 2**, that run produces **two seeds**, one multi-parent Aggregate merge, and (in the verified CLI twin) the merge log pattern **nodes 6 → 8**, then KeepBest **active** drops such as **6 → 5**, final **correct: True**, score **16**.

> **Live UI note:** thought **IDs change every run**. Speak the IDs you see in the graph / Flight recorder. The **6 → 8** / **active drop** pattern is structural for this input and k settings — do not invent different numbers.

**Backup if Groq stalls:** cut to a pre-recorded clip of the same UI run (or the CLI twin). Prefer that over dead air.

---

## [0:00] Cold open / hook

**[DOING:** Browser on the app masthead — title **Graph of Thoughts**, LIVE/GoT ring visible. Cursor idle.]

We implemented Graph of Thoughts from Besta and colleagues — the AAAI 2024 paper — completely from scratch. No LangChain, no LangGraph, no agent framework. Graph of Thoughts is a graph-based reasoning pattern: the language model doesn’t just branch like Tree of Thoughts; independent thoughts can also **merge**. That multi-parent merge is Aggregate, and it’s the paper’s main differentiator. In the next roughly ten minutes I’ll show our live engine in this UI, point at the real code that implements Generate, Aggregate, Refine, Score, and KeepBest under a Graph of Operations controller, walk a real sorting run with a logged merge and node counts, prove the same engine drives the other paper tasks, and finish with the deviations we documented on purpose.

---

## [0:25] Paper → code mapping

**[DOING:** Switch to the IDE. Open `backend/engine/operations.py` briefly, scroll to the class names. Then open `backend/engine/graph_of_operations.py` and jump to `build_decompose_merge_plan`. Keep both tabs ready; don’t linger more than ~90 seconds total.]

Here’s how the paper maps onto our code. A Thought is a node — content, parents, score, active flag — in `thought.py`. The graph and graph reasoning state live in `graph.py`. The five operations the paper cares about are all in `operations.py`. Generate takes one parent and creates k children. Aggregate takes at least two parents, creates a child, and draws an edge from every parent into that child — that’s the multi-parent merge Tree of Thoughts cannot express — and it logs a merge event with node counts before and after. Refine detects an error, tries an LLM fix, and if that fails falls back to a deterministic repair. Score is programmatic: it calls the task’s score details, not another LLM judge. KeepBest keeps the top N by score and marks the rest inactive; that’s where the active node count drops. The Graph of Operations controller is `graph_of_operations.py`. The function `build_decompose_merge_plan` builds a static recipe: seed the chunks, then for each chunk Generate, Score, Refine, Score, KeepBest, then a pairwise Aggregate ladder until one thought remains. The controller walks that plan; the graph of thoughts grows as we execute. I’m going to switch to the live UI now and show that plan running.

---

## [2:00] Live sorting run (UI)

### Setup

**[DOING:** Back to http://127.0.0.1:5173. Left rail → **Mission control**. Click the **Sorting** tile (blurb: Chunk → sort → merge ladder). In **Number list**, replace whatever is there with the hero list: `4, 1, 3, 2, 8, 5, 7, 6, 9, 0, 2, 1, 5, 4, 3, 8`. Set **Chunk size** to **8**. Under **Generate k · Aggregate k**, set both to **2**. Glance at the legend: Generate teal, Aggregate orange, Refine yellow, Score blue, KeepBest lime.]

I’m on Mission control with the Sorting tile selected — that’s paper section 5.1 in our demo. I’ve pasted a sixteen-number list and set chunk size to eight, so the engine will create two seeds of eight numbers each. Generate k is two, so each seed gets two LLM sort attempts before KeepBest. Aggregate k is also two, which means when those two chunk winners meet, we’ll try the merge twice and KeepBest will keep one. I’m about to hit **Run GoT**. While it streams, watch three places: the center graph, the HUD chips above it — nodes, active, merges, refines, best score, and prune — and the Flight recorder on the right, which prints the same engine events as our JSONL log.

**[DOING:** Click **Run GoT**. Button label becomes **Reasoning…**. Status ring goes LIVE.]

### While it runs (speak through the wait — ~10–20 s for this short list; longer if Groq paces)

**[DOING:** Eyes on the graph as Seed then Generate nodes appear. Point at HUD as numbers tick. Scroll Flight recorder with the mouse if needed so new lines stay visible.]

Okay — first you should see Seed nodes: those are just the unsorted chunks, no LLM yet. Then Generate fans out from each seed. With Generate k equals two you’ll get two teal Generate children per chunk. Score writes a numeric score; for a clean eight-element chunk you’ll often see score eight. Refine only fires if the detector finds an error — on a short perfect run it may skip entirely, and that’s okay; I’ll show a real Refine from a longer log later if we need it. KeepBest then keeps one winner per chunk and discards the other — watch the HUD **prune** chip flip to something like four goes to three — that’s active count shrinking, not deleting history from the graph. You’ll also notice short pauses if the client says it’s pacing Groq; free tier is about thirty requests per minute, so a sleep is expected, not a hang.

### Hero merge moment

**[DOING:** When an orange Aggregate node appears with badge **2 parents → merge**, pause. In **Flight recorder**, find the line whose message looks like `Aggregate merge […] → … (nodes 6 → 8)`. Point at that line, then at the Aggregate node. Then find a nearby KeepBest / prune line with `active … → …`.]

Here’s the paper minimum bar on screen. Two independent branches — the KeepBest winner from chunk zero and the winner from chunk one — converge into one Aggregate child. That’s a genuine multi-parent merge; both parents point into the same orange node, and the badge literally says two parents, merge. Look at the logged node counts on that merge line. In our verified twin of this exact input, it read nodes six goes to eight. I need to be precise about what that means: that is **total graph nodes** after Aggregate adds its candidates. Because Aggregate k is two, the engine creates two merge attempts, so the total count goes **up** by two — six to eight — it is not a reduction at the merge moment. The efficiency or “saving” story in our implementation shows up on KeepBest: for example active six goes to five when the weaker Aggregate candidate is pruned. So: merge line proves multi-parent convergence and logs before/after totals; prune line proves the active set shrinking. That pairing is what we want the assessor to see.

### Inspect the Aggregate node

**[DOING:** Click the Aggregate node with the **2 parents → merge** badge. Left rail → **Node inspector** updates.]

I’m opening Node inspector. You can see the thought id, the op Aggregate, the score — for the full sixteen-element merge that should land around sixteen if the multiset is clean — and under parents, two ids with the note multi-parent merge. Content is the merged sorted list. State will say active if this is the KeepBest survivor, or discarded if it lost. That’s the GRS view of one node.

### Result + export

**[DOING:** Wait until status completes. Header may show **Final thought matches ground truth**. Optionally click header **Download .md** or rail **Export** → **Final .md** / **Final .txt**.]

When the run finishes we get a correctness verdict against ground truth for sorting. On the verified twin, final content matched the sorted input, correct true, score sixteen. I’m also clicking Download markdown — or Final .md under Export — so this isn’t only a graph exercise; you can take the final thought out of the demo. If you have a node selected, Export also offers **This node .txt**.

### If Refine stayed at zero

**[DOING:** Only if HUD **refines** is still 0. Briefly open `backend/logs/api-d83b4fd9.jsonl` in the IDE, search `refine`, point at one `llm_fixed` line, then return to the UI.]

On this short run Refine may show zero corrections because the model sorted both chunks cleanly. That’s honest. Here’s a prior full run where Refine fired llm_fixed on a frequency mismatch — before and after content differ — so the path is real even when today’s hero didn’t need it.

---

## [4:30] Architecture / code quality

**[DOING:** Switch to IDE file tree. Expand `backend/engine/` and `backend/tasks/`. Open `tasks/base_task.py` (abstract methods visible) and `tasks/registry.py` (TASK_REGISTRY with four ids).]

Quick code quality beat. Everything under engine is task-agnostic: Thought, Graph, the five operations, the GoO controller, the Groq client, the logger. Everything under tasks is a plugin. The contract is BaseTask — generate prompt, aggregate prompt, refine prompt, parsers, score, detect error, deterministic refine, split input, and so on. The registry maps string ids — sorting, keyword_counting, set_intersection, document_merging — to classes. We can add another paper workload without rewriting the Graph of Operations. Same recipe; different thought algebra. Back to the UI to prove that.

---

## [5:30] Prove generality — other tasks

### Keywords

**[DOING:** Mission control → **Keywords** tile (Passages → counts → Aggregate). Leave the demo **Passage text** (or click **Reset** to restore the built-in demo). Chunk size should snap to **2**. Keep Generate k / Aggregate k at **2**. Click **Run GoT**. Narrate while Seeds/Generates/Aggregates stream.]

Same engine, different content. Keywords splits the passage into sentence groups — chunk size two means about two sentences per seed — Generate counts countries into a JSON object, and Aggregate **sums** those count dictionaries by key. So if one passage says France once and another says France once, the merge should add to two. Watch merges tick on the HUD and click a final Aggregate or the result content in Node inspector when it finishes. We’re not re-explaining the whole ladder; we’re showing Aggregate means something different here: addition of histograms, not merging sorted lists.

### Set ∩

**[DOING:** Click **Set ∩** (Split B → ∩A → union). The **Sets JSON** box already has a demo `set_a` / `set_b`. Leave it or tweak slightly. Chunk size **8**. **Run GoT**. When an Aggregate with **2 parents → merge** appears, click it.]

Set intersection keeps set A whole and chunks set B. Generate computes A intersect each subset of B. Aggregate here is the **union** of those partial intersections — not intersecting the partials again — because A intersect B equals the union over i of A intersect B_i. Node inspector on an Aggregate should show a sorted unique list and two parents. Again: same GoO, different merge algebra.

### Docs (third task — keep if time; skip if already past ~8:00)

**[DOING:** Click **Docs**. Either paste with `---` separators already in the box, or **Drop files here** / file picker and upload at least two from `got-project/samples/` — for example `nda-confidentiality.txt` and `nda-return-destroy.txt`. Hint must say files ready. **Run GoT**. After completion, optional header **Download .md**.]

Document merging needs at least two documents or Aggregate never pairs. Generate turns each excerpt into obligation bullets; Aggregate **dedupe-merges** those drafts into one coherent clause list. Scoring here is heuristic — duplicates and coverage — because there’s no single gold NDA string. If the run completes, I’ll grab Download .md so the merged clauses leave with us.

---

## [8:00] Documented deviations from the paper

**[DOING:** Optional glance at `backend/README.md` “Design notes / deviations” while speaking — or stay on the UI and speak from memory. Do not invent extras beyond that table.]

Before we close, the fidelity choices we documented. We default Generate k to two, not the paper’s typical three, to cut Groq calls on a timed assessment — and it’s overridable in this UI. Aggregate attempts default to two, not something like ten, for the same cost reason — also overridable. KeepBest N is one, which matches common paper KeepBest-one usage. Our sorting demos often use forty-eight numbers with chunk eight; today I used sixteen with chunk eight on purpose so the merge is fast and readable on camera. Document merging scores are heuristic — duplicates plus coverage — because there’s no unique gold answer. We call Groq over plain HTTP with httpx, not the paper’s original model stack. And we use no agent frameworks at all; the assessment wants a hand-written GoO and GRS. What we did **not** drop is the structure: decompose, Generate, Score, Refine, KeepBest, then multi-parent Aggregate, with sorting still using error-scope X plus Y — adjacent inversions and frequency mismatch.

---

## [9:00] What would break if we removed Refine

**[DOING:** Stay on a finished sorting graph if possible, or briefly show `operations.py` class Refine. Optionally flash the `api-d83b4fd9` refine line again.]

If we removed Refine, anything Generate or Aggregate got wrong with error scope greater than zero would simply stay wrong into KeepBest. KeepBest only compares scores; it does not repair content. So a slightly higher-scoring but incorrect sort could win, or two bad candidates would compete with no correction step. In our code Refine is detect error, try the LLM, then fall back to sorting the true source multiset deterministically. Without that path, frequency and order bugs ride into later Aggregates and you’re much more likely to finish with correct false. The alternate punchline, if someone asks: remove Aggregate and the graph collapses toward Tree-of-Thoughts trees — no multi-parent convergence, and the paper claim fails on screen.

---

## [9:45] Wrap-up

**[DOING:** Cursor back on the app masthead / final sorting graph. Stop after this paragraph.]

So to close: we showed a real Graph of Thoughts engine — Generate, Aggregate, Refine, Score, and KeepBest under a Graph of Operations — including a live multi-parent merge with logged node counts, explained accurately. The same engine drives sorting, keyword count sums, set-intersection unions, and document dedupe-merges; it’s not a sorting trick. Our deviations are explicit and justified, and the core paper mechanism is intact.

---

## Grading coverage map

| Criterion | Where in this script |
|-----------|----------------------|
| Working E2E (40%) | [2:00] UI sorting → ground-truth verdict / correct |
| Fidelity (30%) | [0:25] ops + GoO · [2:00] merge + node counts · [8:00] deviations |
| Code quality (20%) | [4:30] engine vs tasks · BaseTask · registry |
| Explanation | Full spoken script · [9:00] remove Refine |

---

## Pre-recording checklist (UI-primary)

1. **Backend:** `backend/.env` has a valid `GROQ_API_KEY`; venv on; `uvicorn api.server:app --reload --host 127.0.0.1 --port 8000`.
2. **Frontend:** `npm run dev` → http://127.0.0.1:5173. Confirm **Mission control** tiles: **Sorting / Keywords / Set ∩ / Docs**.
3. **Primary hero:** UI sorting with the **16-number** list, chunk **8**, Generate k **2**, Aggregate k **2**. Dry-run once; confirm Flight recorder shows an Aggregate merge and a KeepBest active drop; confirm verdict / correct.
4. **IDs:** Expect new thought ids every run — speak what is on screen. Expect merge **total nodes** to rise with Aggregate k (verified pattern **6 → 8**); do **not** call that a reduction.
5. **CLI twin = backup only:** `python run_cli.py --task sorting --list "4,1,3,2,8,5,7,6,9,0,2,1,5,4,3,8" --chunk-size 8 --generate-k 2 --aggregate-k 2 --run-id video-sort-demo` if the UI dies mid-take.
6. **Refine backup:** `logs/api-d83b4fd9.jsonl` (short UI hero often has **refines: 0**).
7. **Pre-record** one clean UI sorting take (and optional Keywords / Set ∩) for cutaway if live RPM pacing blows the clock.
8. **IDE tabs queued:** `operations.py`, `graph_of_operations.py` (`build_decompose_merge_plan`), `base_task.py`, `registry.py`, README deviations.
9. **Docs samples:** `got-project/samples/*.txt` (≥2 files). Or use the built-in paste-with-`---` demo.
10. **Screen hygiene:** hide `.env`; zoom UI so HUD chips and Flight recorder merge lines are readable.
11. **Supabase:** skip unless spare time; if shown, filter by `run_id`.
12. **Rehearse read-aloud once** with a stopwatch; trim Docs section first if over 11 minutes.
13. **Remember:** Reset on Sorting loads a **random 48-list** — do **not** rely on Reset for the hero; paste the sixteen numbers manually.
