"""Structured JSON-lines logger for GoT engine events.

Every node create / operation / merge / refine / score / prune is recorded
to a log file and optionally pushed to a live event callback (SSE).
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


EventCallback = Callable[[dict[str, Any]], None]


class GoTLogger:
    def __init__(
        self,
        run_id: str,
        log_dir: str | Path = "logs",
        event_callback: EventCallback | None = None,
        also_console: bool = True,
    ) -> None:
        self.run_id = run_id
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_dir / f"{run_id}.jsonl"
        self.event_callback = event_callback
        self.also_console = also_console
        self.events: list[dict[str, Any]] = []
        self.started_at = time.time()
        try:
            from supabase_log import attach_supabase_sink

            attach_supabase_sink(self)
        except Exception:
            pass
        self._emit(
            "run_start",
            message=f"GoT run {run_id} started",
        )

    def _emit(self, event_type: str, **payload: Any) -> dict[str, Any]:
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "elapsed_s": round(time.time() - self.started_at, 3),
            "run_id": self.run_id,
            "event": event_type,
            **payload,
        }
        self.events.append(event)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")
        if self.also_console:
            self._print(event)
        if self.event_callback is not None:
            self.event_callback(event)
        return event

    def _print(self, event: dict[str, Any]) -> None:
        et = event.get("event", "?")
        msg = event.get("message") or event.get("summary") or ""
        extras = {
            k: v
            for k, v in event.items()
            if k
            not in {
                "ts",
                "elapsed_s",
                "run_id",
                "event",
                "message",
                "summary",
                "prompt",
                "response",
            }
        }
        line = f"[{event['elapsed_s']:7.2f}s] {et:<18} {msg}"
        if extras:
            # keep console readable — truncate long values
            short = {
                k: (str(v)[:80] + "…") if len(str(v)) > 80 else v
                for k, v in extras.items()
            }
            line += f"  |  {short}"
        print(line, file=sys.stderr)

    # ---- typed helpers (rich logs for video walkthrough) ------------------

    def operation_start(
        self,
        op_type: str,
        input_ids: list[str],
        **extra: Any,
    ) -> dict[str, Any]:
        return self._emit(
            "operation_start",
            operation=op_type,
            input_ids=input_ids,
            message=f"{op_type} starting on {input_ids}",
            **extra,
        )

    def operation_end(
        self,
        op_type: str,
        input_ids: list[str],
        output_ids: list[str],
        **extra: Any,
    ) -> dict[str, Any]:
        return self._emit(
            "operation_end",
            operation=op_type,
            input_ids=input_ids,
            output_ids=output_ids,
            message=f"{op_type} → {output_ids}",
            **extra,
        )

    def node_created(self, thought_dict: dict[str, Any], **extra: Any) -> dict[str, Any]:
        return self._emit(
            "node_created",
            thought_id=thought_dict["id"],
            operation_type=thought_dict.get("operation_type"),
            content=thought_dict.get("content"),
            score=thought_dict.get("score"),
            parents=thought_dict.get("parents"),
            message=f"node {thought_dict['id']} created via {thought_dict.get('operation_type')}",
            **extra,
        )

    def merge_event(
        self,
        parent_ids: list[str],
        child_id: str,
        nodes_before: int,
        nodes_after: int,
        **extra: Any,
    ) -> dict[str, Any]:
        return self._emit(
            "merge",
            parent_ids=parent_ids,
            child_id=child_id,
            nodes_before=nodes_before,
            nodes_after=nodes_after,
            message=(
                f"Aggregate merge {parent_ids} → {child_id} "
                f"(nodes {nodes_before} → {nodes_after})"
            ),
            **extra,
        )

    def refine_event(
        self,
        thought_id: str,
        error_detected: str,
        before_content: Any,
        after_content: Any,
        path: str,
        **extra: Any,
    ) -> dict[str, Any]:
        return self._emit(
            "refine",
            thought_id=thought_id,
            error_detected=error_detected,
            before_content=before_content,
            after_content=after_content,
            path=path,  # "llm_fixed" | "fallback_fixed" | "no_fix_needed"
            message=f"Refine {thought_id} via {path}: {error_detected}",
            **extra,
        )

    def score_event(
        self,
        thought_id: str,
        score: float,
        inversions: int | None = None,
        error_scope: float | None = None,
        details: dict[str, Any] | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        return self._emit(
            "score",
            thought_id=thought_id,
            score=score,
            inversions=inversions,
            error_scope=error_scope,
            details=details or {},
            message=f"Score {thought_id} = {score} (inversions={inversions})",
            **extra,
        )

    def prune_event(
        self,
        kept_ids: list[str],
        discarded_ids: list[str],
        reason: str,
        nodes_before: int,
        nodes_after_active: int,
        **extra: Any,
    ) -> dict[str, Any]:
        return self._emit(
            "prune",
            kept_ids=kept_ids,
            discarded_ids=discarded_ids,
            reason=reason,
            nodes_before=nodes_before,
            nodes_after_active=nodes_after_active,
            message=(
                f"KeepBest kept {kept_ids}, discarded {discarded_ids} "
                f"(active {nodes_before} → {nodes_after_active})"
            ),
            **extra,
        )

    def llm_call(
        self,
        prompt: str,
        response: str,
        model: str,
        latency_s: float,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        return self._emit(
            "llm_call",
            model=model,
            latency_s=latency_s,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            prompt=_truncate(prompt, 500),
            response=_truncate(response, 500),
            message=f"LLM {model} ({latency_s:.2f}s)",
            **extra,
        )

    def goo_plan(self, steps: list[dict[str, Any]]) -> dict[str, Any]:
        return self._emit(
            "goo_plan",
            steps=steps,
            message=f"GoO plan with {len(steps)} steps",
        )

    def goo_step(self, step_index: int, step: dict[str, Any]) -> dict[str, Any]:
        return self._emit(
            "goo_step",
            step_index=step_index,
            step=step,
            message=f"GoO step {step_index}: {step.get('op')}",
        )

    def run_end(self, result: dict[str, Any]) -> dict[str, Any]:
        return self._emit(
            "run_end",
            result=result,
            message="GoT run finished",
        )

    def info(self, message: str, **extra: Any) -> dict[str, Any]:
        return self._emit("info", message=message, **extra)

    def warning(self, message: str, **extra: Any) -> dict[str, Any]:
        return self._emit("warning", message=message, **extra)

    def error(self, message: str, **extra: Any) -> dict[str, Any]:
        return self._emit("error", message=message, **extra)


def _truncate(text: str, n: int) -> str:
    if len(text) <= n:
        return text
    return text[:n] + f"…[+{len(text) - n} chars]"
