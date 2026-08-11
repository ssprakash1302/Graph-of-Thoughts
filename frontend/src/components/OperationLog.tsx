import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef } from "react";
import type { GoTEvent } from "../types";

type Props = { events: GoTEvent[] };

function toneClass(ev: GoTEvent): string {
  if (ev.operation) return ev.operation;
  if (ev.event === "merge") return "merge";
  if (ev.event === "refine") return "refine";
  if (ev.event === "score") return "score";
  if (ev.event === "prune") return "prune";
  if (ev.event === "node_created" && ev.operation_type) return String(ev.operation_type);
  return ev.event;
}

function summarize(ev: GoTEvent): string {
  if (ev.message) return String(ev.message);
  if (ev.event === "merge") {
    return `${JSON.stringify(ev.parent_ids)} → ${ev.child_id}`;
  }
  if (ev.event === "refine") {
    return `${ev.thought_id} via ${ev.path}: ${String(ev.error_detected ?? "")}`;
  }
  if (ev.event === "score") {
    return `${ev.thought_id} = ${ev.score} (inv ${ev.inversions ?? "—"})`;
  }
  if (ev.event === "prune") {
    return `keep ${JSON.stringify(ev.kept_ids)} · drop ${JSON.stringify(ev.discarded_ids)}`;
  }
  return "";
}

export default function OperationLog({ events }: Props) {
  const endRef = useRef<HTMLDivElement | null>(null);
  const visible = events.slice(-80);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [events.length]);

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: 0, flex: 1 }}>
      <div className="log-head">
        <h2>Flight recorder</h2>
        <span>{events.length} events</span>
      </div>
      <div className="log-panel">
        {events.length === 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            style={{ color: "var(--fog)", padding: "0.75rem 0.4rem", lineHeight: 1.5 }}
          >
            Engine quiet. Hit <b style={{ color: "var(--paper)" }}>Run GoT</b> and every
            Generate / Aggregate / Refine pulse lands here.
          </motion.div>
        )}
        <AnimatePresence initial={false}>
          {visible.map((ev, i) => (
            <motion.div
              key={`${ev.event}-${ev.elapsed_s}-${i}-${ev.thought_id ?? ""}-${ev.child_id ?? ""}`}
              className={`log-line ${toneClass(ev)}`}
              initial={{ opacity: 0, x: 24, scale: 0.98 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              transition={{ type: "spring", stiffness: 380, damping: 28 }}
              layout
            >
              <span className="ts">[{Number(ev.elapsed_s ?? 0).toFixed(2)}s]</span>{" "}
              <strong>{ev.event}</strong>
              {ev.operation ? `/${ev.operation}` : ""} — {summarize(ev)}
            </motion.div>
          ))}
        </AnimatePresence>
        <div ref={endRef} />
      </div>
    </div>
  );
}
