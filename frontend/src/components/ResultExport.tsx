import { motion } from "framer-motion";
import type { RunResult } from "../types";
import { contentToText, downloadFile, exportResult } from "../exportResult";
import type { ThoughtNode } from "../types";

type Props = {
  result: RunResult | null;
  selectedNode: ThoughtNode | null;
};

export default function ResultExport({ result, selectedNode }: Props) {
  if (!result?.final_content && !selectedNode) return null;

  return (
    <motion.div
      className="export-bar"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <div className="section-label" style={{ paddingTop: 0 }}>
        Export
      </div>
      {result?.final_content != null && (
        <div className="btn-row" style={{ paddingTop: 0 }}>
          <button type="button" className="btn" onClick={() => exportResult(result, "txt")}>
            Final .txt
          </button>
          <button type="button" className="btn btn-primary" onClick={() => exportResult(result, "md")}>
            Final .md
          </button>
        </div>
      )}
      {selectedNode && (
        <div className="btn-row" style={{ paddingTop: 0 }}>
          <button
            type="button"
            className="btn"
            onClick={() =>
              downloadFile(
                `thought-${selectedNode.id}.txt`,
                contentToText(selectedNode.content),
                "text/plain;charset=utf-8"
              )
            }
          >
            This node .txt
          </button>
        </div>
      )}
    </motion.div>
  );
}
