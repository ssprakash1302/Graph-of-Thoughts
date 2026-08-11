import { AnimatePresence, motion } from "framer-motion";
import { useMemo, useRef, useState } from "react";
import type { StreamStatus } from "../hooks/useGoTStream";

type UploadedDoc = { name: string; size: number; text: string };

const MAX_DOC_BYTES = 80_000;
const MAX_DOCS = 12;

async function readTextFiles(fileList: FileList | File[]): Promise<UploadedDoc[]> {
  const files = Array.from(fileList);
  const out: UploadedDoc[] = [];
  for (const f of files) {
    if (!/\.(txt|md)$/i.test(f.name)) {
      throw new Error(`${f.name} is not a .txt or .md file`);
    }
    if (f.size > MAX_DOC_BYTES) {
      throw new Error(`${f.name} is over ${MAX_DOC_BYTES / 1000}KB — keep excerpts short for Groq`);
    }
    const text = (await f.text()).trim();
    if (!text) {
      throw new Error(`${f.name} is empty`);
    }
    out.push({ name: f.name, size: f.size, text });
  }
  return out;
}

export type TaskId =
  | "sorting"
  | "keyword_counting"
  | "set_intersection"
  | "document_merging";

type Props = {
  status: StreamStatus;
  error: string | null;
  runId: string | null;
  onRun: (payload: Record<string, unknown>) => void;
};

const TASKS: { id: TaskId; label: string; blurb: string; chunk: number }[] = [
  { id: "sorting", label: "Sorting", blurb: "Chunk → sort → merge ladder", chunk: 8 },
  {
    id: "keyword_counting",
    label: "Keywords",
    blurb: "Passages → counts → Aggregate",
    chunk: 2,
  },
  {
    id: "set_intersection",
    label: "Set ∩",
    blurb: "Split B → ∩A → union",
    chunk: 8,
  },
  {
    id: "document_merging",
    label: "Docs",
    blurb: "Upload .txt files → Aggregate merge",
    chunk: 1,
  },
];

function randomList(n: number, seed = Date.now() % 100000): number[] {
  let s = seed;
  const next = () => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return s;
  };
  return Array.from({ length: n }, () => next() % 10);
}

const DEMO_TEXT =
  "France and Germany signed a trade note. Later, Italy and Spain joined talks. " +
  "A report mentioned Canada and Brazil as observers. In Asia, Japan and India " +
  "expanded cooperation while China watched closely. Australia and Mexico sent " +
  "delegates. Egypt and Kenya hosted a side event; Norway and Sweden published " +
  "a joint statement. France appeared again in the appendix.";

const DEMO_DOCS = [
  "NDA-A: Keep Confidential Information secret for 3 years. Delaware law. Need-to-know disclosure allowed.",
  "NDA-B: Do not disclose Confidential Information for three years. Return/destroy on request. Delaware.",
  "NDA-C: Residuals from unaided memory excluded. Affiliates OK under equivalent obligations. Term: 36 months.",
  "NDA-D: No public announcement without consent. Injunctive relief available. Delaware governs.",
];

export default function RunControls({ status, error, runId, onRun }: Props) {
  const [task, setTask] = useState<TaskId>("sorting");
  const [sortText, setSortText] = useState(() => randomList(48, 42).join(", "));
  const [kwText, setKwText] = useState(DEMO_TEXT);
  const [setJson, setSetJson] = useState(
    () =>
      JSON.stringify(
        {
          set_a: [1, 2, 3, 5, 8, 13, 21, 34, 40, 41, 42, 50],
          set_b: [2, 3, 8, 9, 13, 15, 21, 30, 34, 41, 55, 60],
        },
        null,
        2
      )
  );
  const [docsText, setDocsText] = useState(DEMO_DOCS.join("\n---\n"));
  const [uploadedDocs, setUploadedDocs] = useState<UploadedDoc[]>([]);
  const [docError, setDocError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [chunkSize, setChunkSize] = useState(8);
  const [generateK, setGenerateK] = useState(2);
  const [aggregateK, setAggregateK] = useState(2);

  const running = status === "running" || status === "starting";
  const meta = useMemo(() => TASKS.find((t) => t.id === task)!, [task]);

  const addDocs = async (fileList: FileList | File[] | null) => {
    if (!fileList || running) return;
    setDocError(null);
    try {
      const next = await readTextFiles(fileList);
      setUploadedDocs((prev) => {
        const byName = new Map(prev.map((d) => [d.name, d]));
        for (const d of next) byName.set(d.name, d);
        return [...byName.values()].slice(0, MAX_DOCS);
      });
    } catch (e) {
      setDocError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <motion.div initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.45 }}>
      <div className="section-label">Mission control</div>

      <div className="task-tabs">
        {TASKS.map((t, idx) => (
          <motion.button
            key={t.id}
            type="button"
            className={`task-tab ${task === t.id ? "active" : ""}`}
            disabled={running}
            onClick={() => {
              setTask(t.id);
              setChunkSize(t.chunk);
            }}
            whileTap={{ scale: 0.97 }}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: idx * 0.05 }}
          >
            <strong>{t.label}</strong>
            <span>{t.blurb}</span>
          </motion.button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={task}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.22 }}
        >
          {task === "sorting" && (
            <div className="field">
              <label>Number list</label>
              <textarea
                rows={4}
                value={sortText}
                onChange={(e) => setSortText(e.target.value)}
                disabled={running}
              />
              <div className="hint">{meta.blurb} · paper §5.1</div>
            </div>
          )}
          {task === "keyword_counting" && (
            <div className="field">
              <label>Passage text</label>
              <textarea rows={5} value={kwText} onChange={(e) => setKwText(e.target.value)} disabled={running} />
            </div>
          )}
          {task === "set_intersection" && (
            <div className="field">
              <label>Sets JSON</label>
              <textarea rows={7} value={setJson} onChange={(e) => setSetJson(e.target.value)} disabled={running} />
            </div>
          )}
          {task === "document_merging" && (
            <div className="field">
              <label>Upload .txt / .md</label>
              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.md,text/plain"
                multiple
                hidden
                disabled={running}
                onChange={(e) => {
                  void addDocs(e.target.files);
                  e.target.value = "";
                }}
              />
              <div
                className={`dropzone ${dragOver ? "over" : ""}`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                  void addDocs(e.dataTransfer.files);
                }}
                onClick={() => fileInputRef.current?.click()}
              >
                <strong>Drop files here</strong>
                <span>or click to choose · 2+ docs · .txt / .md</span>
              </div>
              <AnimatePresence>
                {uploadedDocs.map((d) => (
                  <motion.div
                    key={d.name}
                    className="file-chip"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, x: -8 }}
                    layout
                  >
                    <div>
                      <b>{d.name}</b>
                      <span>
                        {(d.size / 1024).toFixed(1)} KB · {d.text.split(/\s+/).length} words
                      </span>
                    </div>
                    <button
                      type="button"
                      className="btn"
                      style={{ padding: "0.25rem 0.5rem", fontSize: "0.72rem" }}
                      disabled={running}
                      onClick={(e) => {
                        e.stopPropagation();
                        setUploadedDocs((prev) => prev.filter((x) => x.name !== d.name));
                      }}
                    >
                      Remove
                    </button>
                  </motion.div>
                ))}
              </AnimatePresence>
              {docError && <div className="err-banner" style={{ margin: "0.4rem 0 0" }}>{docError}</div>}
              <div className="hint">
                {uploadedDocs.length >= 2
                  ? `${uploadedDocs.length} files ready — Run GoT to Aggregate them.`
                  : "Need at least two files. Sample NDAs live in got-project/samples/."}
              </div>
              {uploadedDocs.length === 0 && (
                <>
                  <label style={{ marginTop: "0.55rem" }}>Or paste (--- between docs)</label>
                  <textarea
                    rows={5}
                    value={docsText}
                    onChange={(e) => setDocsText(e.target.value)}
                    disabled={running}
                  />
                </>
              )}
            </div>
          )}
        </motion.div>
      </AnimatePresence>

      <div className="field">
        <label>Chunk size</label>
        <input
          type="number"
          min={1}
          max={32}
          value={chunkSize}
          onChange={(e) => setChunkSize(Number(e.target.value))}
          disabled={running}
        />
      </div>
      <div className="field">
        <label>Generate k · Aggregate k</label>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <input
            type="number"
            min={1}
            max={5}
            value={generateK}
            onChange={(e) => setGenerateK(Number(e.target.value))}
            disabled={running}
          />
          <input
            type="number"
            min={1}
            max={10}
            value={aggregateK}
            onChange={(e) => setAggregateK(Number(e.target.value))}
            disabled={running}
          />
        </div>
      </div>

      <div className="btn-row">
        <button
          className="btn"
          type="button"
          disabled={running}
          onClick={() => {
            if (task === "sorting") setSortText(randomList(48).join(", "));
            if (task === "keyword_counting") setKwText(DEMO_TEXT);
            if (task === "document_merging") {
              setDocsText(DEMO_DOCS.join("\n---\n"));
              setUploadedDocs([]);
              setDocError(null);
            }
          }}
        >
          Reset
        </button>
        <motion.button
          type="button"
          className={`btn btn-primary ${running ? "running" : ""}`}
          disabled={running}
          whileHover={{ scale: running ? 1 : 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={() => {
            const base = {
              task,
              chunk_size: chunkSize,
              generate_k: generateK,
              aggregate_k: aggregateK,
            };
            try {
              if (task === "sorting") {
                const numbers = sortText
                  .split(/[,\s]+/)
                  .map((x) => x.trim())
                  .filter(Boolean)
                  .map((x) => Number(x));
                if (numbers.some((n) => Number.isNaN(n))) {
                  alert("List must be comma-separated integers");
                  return;
                }
                onRun({ ...base, numbers });
                return;
              }
              if (task === "keyword_counting") {
                onRun({ ...base, payload: { text: kwText } });
                return;
              }
              if (task === "set_intersection") {
                onRun({ ...base, payload: JSON.parse(setJson) });
                return;
              }
              if (uploadedDocs.length >= 2) {
                onRun({
                  ...base,
                  payload: {
                    documents: uploadedDocs.map((d) => ({ name: d.name, text: d.text })),
                  },
                });
                return;
              }
              const documents = docsText
                .split(/\n---\n/)
                .map((d) => d.trim())
                .filter(Boolean);
              if (documents.length < 2) {
                setDocError("Upload or paste at least two documents");
                return;
              }
              onRun({ ...base, payload: { documents } });
            } catch (e) {
              alert(e instanceof Error ? e.message : String(e));
            }
          }}
        >
          {running ? "Reasoning…" : "Run GoT"}
        </motion.button>
      </div>

      <div className="op-legend">
        <span>
          <i style={{ background: "var(--gen)" }} />
          Generate
        </span>
        <span>
          <i style={{ background: "var(--agg)" }} />
          Aggregate
        </span>
        <span>
          <i style={{ background: "var(--ref)" }} />
          Refine
        </span>
        <span>
          <i style={{ background: "var(--score)" }} />
          Score
        </span>
        <span>
          <i style={{ background: "var(--keep)" }} />
          KeepBest
        </span>
      </div>

      {runId && (
        <div className="hint" style={{ padding: "0 1rem 0.75rem" }}>
          run · {runId}
        </div>
      )}
      {error && <div className="err-banner">{error}</div>}
    </motion.div>
  );
}
