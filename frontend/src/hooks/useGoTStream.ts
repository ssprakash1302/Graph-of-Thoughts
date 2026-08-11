import { useCallback, useEffect, useRef, useState } from "react";
import type { GoTEvent, GraphSnapshot, RunResult } from "../types";

export type StreamStatus = "idle" | "starting" | "running" | "completed" | "error";

type StartPayload = {
  task?: string;
  numbers?: number[];
  n?: number;
  payload?: Record<string, unknown>;
  chunk_size?: number;
  seed?: number;
  generate_k?: number;
  aggregate_k?: number;
};

export function useGoTStream() {
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [runId, setRunId] = useState<string | null>(null);
  const [events, setEvents] = useState<GoTEvent[]>([]);
  const [graph, setGraph] = useState<GraphSnapshot | null>(null);
  const [result, setResult] = useState<RunResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mergePulse, setMergePulse] = useState(0);
  const [refinePulse, setRefinePulse] = useState(0);
  const sourceRef = useRef<EventSource | null>(null);

  const reset = useCallback(() => {
    sourceRef.current?.close();
    sourceRef.current = null;
    setEvents([]);
    setGraph(null);
    setResult(null);
    setError(null);
    setRunId(null);
    setStatus("idle");
  }, []);

  const start = useCallback(async (payload: StartPayload) => {
    reset();
    setStatus("starting");
    try {
      const res = await fetch("/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        throw new Error(`POST /run failed: ${res.status}`);
      }
      const data = (await res.json()) as { run_id: string };
      setRunId(data.run_id);
      setStatus("running");

      const es = new EventSource(`/stream/${data.run_id}`);
      sourceRef.current = es;

      const onAny = (raw: MessageEvent) => {
        let ev: GoTEvent;
        try {
          ev = JSON.parse(raw.data) as GoTEvent;
        } catch {
          return;
        }
        setEvents((prev) => [...prev, ev]);
        if (ev.graph_snapshot) {
          setGraph(ev.graph_snapshot);
        }
        if (ev.event === "merge") {
          setMergePulse((n) => n + 1);
        }
        if (ev.event === "refine" && (ev.path === "llm_fixed" || ev.path === "fallback_fixed")) {
          setRefinePulse((n) => n + 1);
        }
        if (ev.event === "run_end" && ev.result) {
          setResult(ev.result as RunResult);
        }
        if (ev.event === "stream_end") {
          setStatus(ev.status === "error" ? "error" : "completed");
          es.close();
        }
        if (ev.event === "error") {
          setError(String(ev.message ?? "Unknown error"));
          setStatus("error");
        }
      };

      // sse-starlette sends named events; also listen to generic message
      [
        "message",
        "run_start",
        "goo_plan",
        "goo_step",
        "operation_start",
        "operation_end",
        "node_created",
        "merge",
        "refine",
        "score",
        "prune",
        "llm_call",
        "info",
        "warning",
        "error",
        "run_end",
        "stream_end",
      ].forEach((name) => es.addEventListener(name, onAny as EventListener));

      es.onerror = () => {
        // Browser retries SSE; only mark error if already completed/failed server-side
      };
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("error");
    }
  }, [reset]);

  useEffect(() => () => sourceRef.current?.close(), []);

  return {
    status,
    runId,
    events,
    graph,
    result,
    error,
    mergePulse,
    refinePulse,
    start,
    reset,
  };
}
