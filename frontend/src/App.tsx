import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import GraphVisualizer from "./components/GraphVisualizer";
import MetricsPanel from "./components/MetricsPanel";
import NodeInspector from "./components/NodeInspector";
import OperationLog from "./components/OperationLog";
import ResultExport from "./components/ResultExport";
import RunControls from "./components/RunControls";
import { exportResult } from "./exportResult";
import { useGoTStream } from "./hooks/useGoTStream";

export default function App() {
  const got = useGoTStream();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const lastMergeChildId = useMemo(() => {
    for (let i = got.events.length - 1; i >= 0; i--) {
      if (got.events[i].event === "merge") return String(got.events[i].child_id ?? "");
    }
    return null;
  }, [got.events]);

  const lastRefineId = useMemo(() => {
    for (let i = got.events.length - 1; i >= 0; i--) {
      const e = got.events[i];
      if (e.event === "refine" && (e.path === "llm_fixed" || e.path === "fallback_fixed")) {
        return String(e.thought_id ?? "");
      }
    }
    return null;
  }, [got.events]);

  const selectedNode =
    selectedId && got.graph?.nodes[selectedId] ? got.graph.nodes[selectedId] : null;

  const verdict =
    got.result?.correct === true
      ? { cls: "ok", text: "Final thought matches ground truth" }
      : got.result?.correct === false
        ? { cls: "bad", text: "Final thought diverges — inspect Refine / Score" }
        : null;

  return (
    <div className="app-shell">
      <motion.header
        className="masthead"
        initial={{ opacity: 0, y: -18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
      >
        <div className="brand-block">
          <div className="brand-kicker">Besta et al. · AAAI 2024 · Groq</div>
          <h1 className="brand">
            Graph of <em>Thoughts</em>
          </h1>
          <p className="brand-sub">
            Watch networked reasoning assemble — Generate fans out, Aggregate merges parents,
            Refine corrects, KeepBest prunes. Four task plugins. One engine.
          </p>
        </div>

        <div className="status-cluster">
          {got.result?.final_content != null && got.status === "completed" && (
            <div className="btn-row" style={{ padding: 0, margin: 0 }}>
              <button type="button" className="btn" onClick={() => exportResult(got.result!, "txt")}>
                Download .txt
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => exportResult(got.result!, "md")}
              >
                Download .md
              </button>
            </div>
          )}
          {verdict && (
            <motion.div
              className={`verdict ${verdict.cls}`}
              initial={{ opacity: 0, scale: 0.92 }}
              animate={{ opacity: 1, scale: 1 }}
            >
              {verdict.text}
            </motion.div>
          )}
          <div
            className={`live-ring ${got.status}`}
            title={got.status}
            aria-label={`Status ${got.status}`}
          >
            <span>{got.status === "running" || got.status === "starting" ? "LIVE" : "GoT"}</span>
          </div>
        </div>
      </motion.header>

      <div className="workspace">
        <aside className="rail">
          <RunControls
            status={got.status}
            error={got.error}
            runId={got.runId}
            onRun={(payload) => got.start(payload)}
          />
          <MetricsPanel
            events={got.events}
            result={got.result}
            graphStats={got.graph?.stats}
            variant="rail"
          />
          <ResultExport result={got.result} selectedNode={selectedNode} />
          <NodeInspector node={selectedNode} />
        </aside>

        <main className="stage-wrap">
          <MetricsPanel
            events={got.events}
            result={got.result}
            graphStats={got.graph?.stats}
            variant="hud"
          />
          <GraphVisualizer
            graph={got.graph}
            selectedId={selectedId}
            onSelect={setSelectedId}
            mergePulse={got.mergePulse}
            refinePulse={got.refinePulse}
            lastMergeChildId={lastMergeChildId}
            lastRefineId={lastRefineId}
          />
        </main>

        <aside className="ticker">
          <OperationLog events={got.events} />
        </aside>
      </div>
    </div>
  );
}
