import { AnimatePresence, motion } from "framer-motion";
import type { ThoughtNode } from "../types";

type Props = { node: ThoughtNode | null };

export default function NodeInspector({ node }: Props) {
  return (
    <div className="inspector">
      <div className="section-label">Node inspector</div>
      <AnimatePresence mode="wait">
        {!node ? (
          <motion.div
            key="empty"
            className="inspector-empty"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
          >
            Click any thought in the graph. You’ll see content, score, parents — and whether it
            survived KeepBest.
          </motion.div>
        ) : (
          <motion.div
            key={node.id}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ type: "spring", stiffness: 280, damping: 24 }}
          >
            <dl>
              <dt>id</dt>
              <dd>{node.id}</dd>
              <dt>op</dt>
              <dd style={{ color: "var(--cyan-hot)" }}>{node.operation_type ?? "—"}</dd>
              <dt>score</dt>
              <dd>{node.score == null ? "—" : node.score}</dd>
              <dt>parents</dt>
              <dd>
                {node.parents.length ? (
                  <span style={{ color: node.parents.length > 1 ? "var(--copper-hot)" : undefined }}>
                    {node.parents.join(" · ")}
                    {node.parents.length > 1 ? "  ← multi-parent merge" : ""}
                  </span>
                ) : (
                  "—"
                )}
              </dd>
              <dt>state</dt>
              <dd>{node.active && !node.discarded ? "active" : "discarded"}</dd>
            </dl>
            <div className="section-label" style={{ paddingLeft: 0 }}>
              content
            </div>
            <pre>{JSON.stringify(node.content, null, 2)}</pre>
            {node.metadata?.refine_path != null && (
              <>
                <div className="section-label" style={{ paddingLeft: 0, paddingTop: "0.7rem" }}>
                  refine path
                </div>
                <pre>{String(node.metadata.refine_path)}</pre>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
