export type GoTEvent = {
  event: string;
  run_id?: string;
  message?: string;
  operation?: string;
  thought_id?: string;
  parent_ids?: string[];
  child_id?: string;
  path?: string;
  score?: number;
  inversions?: number;
  error_scope?: number;
  nodes_before?: number;
  nodes_after?: number;
  nodes_after_active?: number;
  kept_ids?: string[];
  discarded_ids?: string[];
  elapsed_s?: number;
  graph_snapshot?: GraphSnapshot;
  content?: unknown;
  parents?: string[];
  operation_type?: string;
  result?: RunResult;
  [key: string]: unknown;
};

export type ThoughtNode = {
  id: string;
  content: unknown;
  score: number | null;
  parents: string[];
  children: string[];
  operation_type: string | null;
  metadata: Record<string, unknown>;
  discarded: boolean;
  active: boolean;
  state_signature?: unknown;
};

export type GraphSnapshot = {
  nodes: Record<string, ThoughtNode>;
  edges: { source: string; target: string }[];
  stats?: {
    total_nodes: number;
    active_nodes: number;
    edge_count: number;
  };
  node_count_history?: unknown[];
};

export type RunResult = {
  task?: string;
  final_content?: unknown;
  final_score?: number;
  correct?: boolean;
  graph_stats?: GraphSnapshot["stats"];
  llm_usage?: {
    calls?: number;
    total_tokens?: number;
    total_latency_s?: number;
    model?: string;
  };
  elapsed_s?: number;
  log_path?: string;
};
