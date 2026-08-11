import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { GraphSnapshot, ThoughtNode } from "../types";

type Props = {
  graph: GraphSnapshot | null;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  mergePulse: number;
  refinePulse: number;
  lastMergeChildId?: string | null;
  lastRefineId?: string | null;
};

const OP_COLOR: Record<string, string> = {
  Seed: "#8b97a8",
  Generate: "#2ec4b6",
  Aggregate: "#e08a3c",
  Refine: "#f2c14e",
  Score: "#6ea8fe",
  KeepBest: "#d6ff3f",
};

function scoreColor(score: number | null, nHint = 8): string {
  if (score == null) return "#5a6878";
  const t = Math.max(0, Math.min(1, score / Math.max(nHint, 1)));
  const r = Math.round(255 * (1 - t) * 0.85 + 40);
  const g = Math.round(90 + 150 * t);
  const b = Math.round(90 + 40 * (1 - t));
  return `rgb(${r},${g},${b})`;
}

function GotNodeView({ data, selected }: NodeProps) {
  const d = data as {
    thought: ThoughtNode;
    pulse?: "merge" | "refine" | null;
  };
  const op = d.thought.operation_type ?? "?";
  const n = Array.isArray(d.thought.content) ? d.thought.content.length : 8;
  const multi = d.thought.parents.length > 1;

  return (
    <div
      className={`got-node ${selected ? "selected" : ""} ${
        d.pulse === "merge" ? "merge-pulse" : ""
      } ${d.pulse === "refine" ? "refine-pulse" : ""}`}
      style={{
        opacity: d.thought.discarded ? 0.4 : 1,
        borderColor: OP_COLOR[op] ?? "rgba(232,238,246,0.16)",
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0.35 }} />
      <div className="nid">{d.thought.id}</div>
      <div className="op" style={{ color: OP_COLOR[op] ?? "var(--paper)" }}>
        {op}
      </div>
      <div className="score" style={{ color: scoreColor(d.thought.score, n) }}>
        score {d.thought.score == null ? "—" : d.thought.score}
      </div>
      {multi && <div className="parents-badge">{d.thought.parents.length} parents → merge</div>}
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0.35 }} />
    </div>
  );
}

const nodeTypes = { got: GotNodeView };

function layout(graph: GraphSnapshot): { nodes: Node[]; edges: Edge[] } {
  const thoughts = Object.values(graph.nodes);
  const depth = new Map<string, number>();
  const visiting = new Set<string>();

  function getDepth(id: string): number {
    if (depth.has(id)) return depth.get(id)!;
    if (visiting.has(id)) return 0;
    visiting.add(id);
    const t = graph.nodes[id];
    const d =
      !t || t.parents.length === 0 ? 0 : 1 + Math.max(...t.parents.map((p) => getDepth(p)));
    depth.set(id, d);
    visiting.delete(id);
    return d;
  }

  thoughts.forEach((t) => getDepth(t.id));
  const byLayer = new Map<number, ThoughtNode[]>();
  thoughts.forEach((t) => {
    const d = depth.get(t.id) ?? 0;
    if (!byLayer.has(d)) byLayer.set(d, []);
    byLayer.get(d)!.push(t);
  });

  const nodes: Node[] = [];
  [...byLayer.entries()]
    .sort((a, b) => a[0] - b[0])
    .forEach(([layer, items]) => {
      items.forEach((t, i) => {
        const xSpread = Math.max(items.length, 1);
        nodes.push({
          id: t.id,
          type: "got",
          position: {
            x: i * 178 - ((xSpread - 1) * 178) / 2 + 420,
            y: layer * 138 + 70,
          },
          data: { thought: t, pulse: null },
          style: { opacity: 0 },
        });
      });
    });

  const edges: Edge[] = graph.edges.map((e, idx) => {
    const target = graph.nodes[e.target];
    const multi = (target?.parents.length ?? 0) > 1;
    return {
      id: `e-${e.source}-${e.target}-${idx}`,
      source: e.source,
      target: e.target,
      animated: multi || target?.operation_type === "Aggregate",
      style: {
        stroke: multi ? "#e08a3c" : "#3a4a5a",
        strokeWidth: multi ? 2.6 : 1.5,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: multi ? "#e08a3c" : "#3a4a5a",
      },
    };
  });

  return { nodes, edges };
}

export default function GraphVisualizer({
  graph,
  selectedId,
  onSelect,
  mergePulse,
  refinePulse,
  lastMergeChildId,
  lastRefineId,
}: Props) {
  const [flash, setFlash] = useState<"merge" | "refine" | null>(null);

  useEffect(() => {
    if (!mergePulse) return;
    setFlash("merge");
    const t = setTimeout(() => setFlash(null), 900);
    return () => clearTimeout(t);
  }, [mergePulse]);

  useEffect(() => {
    if (!refinePulse) return;
    setFlash("refine");
    const t = setTimeout(() => setFlash(null), 900);
    return () => clearTimeout(t);
  }, [refinePulse]);

  const { nodes, edges } = useMemo(() => {
    if (!graph) return { nodes: [] as Node[], edges: [] as Edge[] };
    const laid = layout(graph);
    return {
      nodes: laid.nodes.map((n) => ({
        ...n,
        selected: n.id === selectedId,
        style: { opacity: 1, transition: "opacity 0.35s ease" },
        data: {
          ...n.data,
          pulse:
            n.id === lastMergeChildId ? "merge" : n.id === lastRefineId ? "refine" : null,
        },
      })),
      edges: laid.edges,
    };
  }, [graph, selectedId, lastMergeChildId, lastRefineId]);

  const empty = !graph || Object.keys(graph.nodes).length === 0;

  return (
    <div className="graph-stage" style={{ height: "100%", width: "100%" }}>
      <AnimatePresence>
        {flash && (
          <motion.div
            key={`${flash}-${mergePulse}-${refinePulse}`}
            className={`shockwave ${flash}`}
            initial={{ opacity: 0.85, scale: 0.92 }}
            animate={{ opacity: 0, scale: 1.08 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {empty && (
          <motion.div
            className="empty-stage"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98 }}
          >
            <h3>
              Waiting for <em style={{ color: "var(--cyan-hot)", fontStyle: "normal" }}>thoughts</em>
            </h3>
            <p>
              The reasoning graph builds live — Generate fans out, Aggregate collapses parents into
              one child, Refine flashes gold when a correction lands.
            </p>
          </motion.div>
        )}
      </AnimatePresence>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.22 }}
        onNodeClick={(_, n) => onSelect(n.id)}
        onPaneClick={() => onSelect(null)}
        minZoom={0.15}
        maxZoom={1.7}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={36} color="rgba(232,238,246,0.05)" />
        <MiniMap
          pannable
          zoomable
          maskColor="rgba(8,12,16,0.72)"
          nodeColor={(n) => {
            const op = (n.data as { thought?: ThoughtNode })?.thought?.operation_type;
            return OP_COLOR[op ?? ""] ?? "#5a6878";
          }}
          style={{ background: "rgba(10,14,20,0.9)", border: "1px solid rgba(232,238,246,0.1)" }}
        />
        <Controls />
      </ReactFlow>
    </div>
  );
}
