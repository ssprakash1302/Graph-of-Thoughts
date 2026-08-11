import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import { useEffect } from "react";
import type { GoTEvent, RunResult } from "../types";

type Props = {
  events: GoTEvent[];
  result: RunResult | null;
  graphStats?: { total_nodes: number; active_nodes: number; edge_count: number };
  variant?: "rail" | "hud";
};

function AnimatedInt({ value }: { value: number }) {
  const mv = useMotionValue(0);
  const spring = useSpring(mv, { stiffness: 100, damping: 20 });
  const display = useTransform(spring, (v) => Math.round(v));
  useEffect(() => {
    mv.set(value);
  }, [value, mv]);
  return <motion.span>{display}</motion.span>;
}

export default function MetricsPanel({ events, result, graphStats, variant = "rail" }: Props) {
  const merges = events.filter((e) => e.event === "merge").length;
  const refines = events.filter(
    (e) => e.event === "refine" && (e.path === "llm_fixed" || e.path === "fallback_fixed")
  ).length;
  const scores = events.filter((e) => e.event === "score");
  const bestScore = scores.reduce<number | null>((acc, e) => {
    if (typeof e.score !== "number") return acc;
    if (acc === null || e.score > acc) return e.score;
    return acc;
  }, result?.final_score ?? null);

  const pruneDrops = events.filter(
    (e) =>
      e.event === "prune" &&
      typeof e.nodes_before === "number" &&
      typeof e.nodes_after_active === "number" &&
      e.nodes_before > e.nodes_after_active
  );
  const lastPrune = pruneDrops[pruneDrops.length - 1];
  const llm = result?.llm_usage;
  const elapsed = result?.elapsed_s ?? events[events.length - 1]?.elapsed_s ?? 0;
  const pruneLabel =
    lastPrune?.nodes_before != null
      ? `${lastPrune.nodes_before}→${lastPrune.nodes_after_active}`
      : "—";

  if (variant === "hud") {
    const chips: { label: string; value: React.ReactNode; tone?: string }[] = [
      {
        label: "nodes",
        value: <AnimatedInt value={graphStats?.total_nodes ?? 0} />,
        tone: "ok",
      },
      { label: "active", value: <AnimatedInt value={graphStats?.active_nodes ?? 0} /> },
      { label: "merges", value: <AnimatedInt value={merges} />, tone: "agg" },
      { label: "refines", value: <AnimatedInt value={refines} />, tone: "ref" },
      { label: "best score", value: bestScore ?? "—" },
      { label: "prune", value: pruneLabel },
    ];
    return (
      <div className="stage-hud">
        {chips.map((c, i) => (
          <motion.div
            key={c.label}
            className="hud-chip"
            data-tone={c.tone}
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 * i, type: "spring", stiffness: 260, damping: 22 }}
          >
            <span>{c.label}</span>
            <b>{c.value}</b>
          </motion.div>
        ))}
      </div>
    );
  }

  return (
    <div>
      <div className="section-label">Live metrics</div>
      <div className="metric-stack">
        <div className="metric-cell">
          <div className="k">Nodes / active</div>
          <div className="v">
            <AnimatedInt value={graphStats?.total_nodes ?? 0} />
            <span style={{ color: "var(--fog)", fontSize: "0.85rem" }}>
              {" "}
              / <AnimatedInt value={graphStats?.active_nodes ?? 0} />
            </span>
          </div>
        </div>
        <div className="metric-cell">
          <div className="k">Merges</div>
          <div className="v" style={{ color: "var(--copper-hot)" }}>
            <AnimatedInt value={merges} />
          </div>
        </div>
        <div className="metric-cell">
          <div className="k">Refine fixes</div>
          <div className="v" style={{ color: "var(--ref)" }}>
            <AnimatedInt value={refines} />
          </div>
        </div>
        <div className="metric-cell">
          <div className="k">Best score</div>
          <div className="v">{bestScore ?? "—"}</div>
        </div>
        <div className="metric-cell">
          <div className="k">Last prune</div>
          <div className="v" style={{ fontSize: "1rem" }}>
            {pruneLabel}
          </div>
        </div>
        <div className="metric-cell">
          <div className="k">Time / tokens</div>
          <div className="v" style={{ fontSize: "0.95rem" }}>
            {Number(elapsed).toFixed(1)}s · {llm?.total_tokens ?? 0}
          </div>
        </div>
      </div>
    </div>
  );
}
