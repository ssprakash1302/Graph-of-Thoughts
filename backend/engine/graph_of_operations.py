"""Graph of Operations (GoO) — static execution plan + controller (paper §4.5).

The GoO is built once before execution as an explicit, inspectable sequence of
operation steps with dependencies. The controller walks the plan, wires each
step's outputs into successor inputs, and maintains the GRS (graph + scores).
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from .graph import Graph
from .llm_client import LLMClient
from .logger import GoTLogger
from .operations import Aggregate, Generate, KeepBest, Refine, Score
from .thought import Thought

from tasks.base_task import BaseTask


@dataclass
class GoOStep:
    """One node in the Graph of Operations plan."""

    id: str
    op: str  # Generate | Aggregate | Refine | Score | KeepBest
    params: dict[str, Any] = field(default_factory=dict)
    # Logical input keys resolved at runtime from the GRS registry
    input_keys: list[str] = field(default_factory=list)
    output_key: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "op": self.op,
            "params": self.params,
            "input_keys": self.input_keys,
            "output_key": self.output_key,
            "description": self.description,
        }


class GraphOfOperations:
    """Controller: builds a GoO for a task and executes it over a Graph (GRS)."""

    def __init__(
        self,
        task: BaseTask,
        llm: LLMClient | None = None,
        logger: GoTLogger | None = None,
        generate_k: int | None = None,
        aggregate_k: int | None = None,
        keep_best_n: int = 1,
        refine_when_imperfect: bool = True,
    ) -> None:
        self.task = task
        self.logger = logger
        self.llm = llm
        self.generate_k = generate_k or int(os.getenv("GOT_GENERATE_K", "2"))
        self.aggregate_k = aggregate_k or int(os.getenv("GOT_AGGREGATE_K", "2"))
        self.keep_best_n = keep_best_n
        self.refine_when_imperfect = refine_when_imperfect

        self.graph = Graph()
        self.steps: list[GoOStep] = []
        # GRS registry: named buckets of thought IDs produced by steps
        self.registry: dict[str, list[str]] = {}
        self.execution_trace: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ plan

    def build_decompose_merge_plan(self, raw_input: Any, chunk_size: int) -> list[GoOStep]:
        """Shared GoO used by sorting / keyword / set / document tasks (paper §5).

        Pattern: Seed chunks → Generate(k) → Score → Refine → Score → KeepBest
        → pairwise Aggregate ladder until one thought remains.

        Demo defaults Generate k=2 / Aggregate k=2 (paper often uses 3 / 10).
        """
        chunks = self.task.split_input(raw_input, chunk_size)
        if not chunks:
            raise ValueError("Task split_input produced zero chunks")
        steps: list[GoOStep] = []
        task_name = getattr(self.task, "name", "task")

        chunk_keys: list[str] = []
        for i, chunk in enumerate(chunks):
            key = f"chunk_{i}"
            chunk_keys.append(key)
            steps.append(
                GoOStep(
                    id=f"seed_{i}",
                    op="Seed",
                    params={"chunk_index": i, "chunk": chunk},
                    input_keys=[],
                    output_key=key,
                    description=f"Seed chunk {i} for {task_name}",
                )
            )

        leaf_keys: list[str] = []
        for i, key in enumerate(chunk_keys):
            gen_out = f"gen_{i}"
            steps.append(
                GoOStep(
                    id=f"generate_{i}",
                    op="Generate",
                    params={"k": self.generate_k},
                    input_keys=[key],
                    output_key=gen_out,
                    description=f"Generate k={self.generate_k} for chunk {i}",
                )
            )
            scored = f"scored_gen_{i}"
            steps.append(
                GoOStep(
                    id=f"score_gen_{i}",
                    op="Score",
                    params={},
                    input_keys=[gen_out],
                    output_key=scored,
                    description=f"Score generate candidates for chunk {i}",
                )
            )
            refined = f"refined_{i}"
            steps.append(
                GoOStep(
                    id=f"refine_{i}",
                    op="Refine",
                    params={"per_candidate": True},
                    input_keys=[scored],
                    output_key=refined,
                    description=f"Refine imperfect candidates for chunk {i}",
                )
            )
            scored2 = f"scored_ref_{i}"
            steps.append(
                GoOStep(
                    id=f"score_ref_{i}",
                    op="Score",
                    params={},
                    input_keys=[refined],
                    output_key=scored2,
                    description=f"Re-score after refine for chunk {i}",
                )
            )
            best = f"best_chunk_{i}"
            steps.append(
                GoOStep(
                    id=f"keepbest_{i}",
                    op="KeepBest",
                    params={"n": self.keep_best_n},
                    input_keys=[scored2],
                    output_key=best,
                    description=f"KeepBest(N={self.keep_best_n}) for chunk {i}",
                )
            )
            leaf_keys.append(best)

        level = 0
        current = leaf_keys
        while len(current) > 1:
            next_level: list[str] = []
            i = 0
            pair_idx = 0
            while i < len(current):
                if i + 1 < len(current):
                    left, right = current[i], current[i + 1]
                    agg_out = f"agg_L{level}_{pair_idx}"
                    steps.append(
                        GoOStep(
                            id=f"aggregate_L{level}_{pair_idx}",
                            op="Aggregate",
                            params={"k_attempts": self.aggregate_k},
                            input_keys=[left, right],
                            output_key=agg_out,
                            description=(
                                f"Aggregate level {level} pair {pair_idx} "
                                f"(k_attempts={self.aggregate_k})"
                            ),
                        )
                    )
                    scored = f"scored_{agg_out}"
                    steps.append(
                        GoOStep(
                            id=f"score_{agg_out}",
                            op="Score",
                            params={},
                            input_keys=[agg_out],
                            output_key=scored,
                            description=f"Score aggregate candidates {agg_out}",
                        )
                    )
                    refined = f"refined_{agg_out}"
                    steps.append(
                        GoOStep(
                            id=f"refine_{agg_out}",
                            op="Refine",
                            params={"per_candidate": True},
                            input_keys=[scored],
                            output_key=refined,
                            description=f"Refine aggregate candidates {agg_out}",
                        )
                    )
                    scored2 = f"scored2_{agg_out}"
                    steps.append(
                        GoOStep(
                            id=f"score2_{agg_out}",
                            op="Score",
                            params={},
                            input_keys=[refined],
                            output_key=scored2,
                            description=f"Re-score refined aggregate {agg_out}",
                        )
                    )
                    best = f"best_{agg_out}"
                    steps.append(
                        GoOStep(
                            id=f"keepbest_{agg_out}",
                            op="KeepBest",
                            params={"n": self.keep_best_n},
                            input_keys=[scored2],
                            output_key=best,
                            description=f"KeepBest after aggregate {agg_out}",
                        )
                    )
                    next_level.append(best)
                    i += 2
                    pair_idx += 1
                else:
                    next_level.append(current[i])
                    i += 1
            current = next_level
            level += 1

        self.steps = steps
        if self.logger:
            self.logger.goo_plan([s.to_dict() for s in steps])
            self.logger.info(
                f"GoO built for {task_name}",
                task=task_name,
                chunk_size=chunk_size,
                n_chunks=len(chunks),
                generate_k=self.generate_k,
                aggregate_k=self.aggregate_k,
                n_steps=len(steps),
            )
        return steps

    # Back-compat alias used by early sorting demos
    def build_sorting_plan(self, numbers: list[int], chunk_size: int) -> list[GoOStep]:
        return self.build_decompose_merge_plan(numbers, chunk_size)

    # --------------------------------------------------------------- execute

    def run(
        self,
        raw_input: Any = None,
        chunk_size: int = 8,
        *,
        numbers: list[int] | None = None,
    ) -> dict[str, Any]:
        """Execute the GoO. ``numbers`` retained for sorting CLI back-compat."""
        if raw_input is None:
            if numbers is None:
                raise ValueError("run() requires raw_input (or numbers= for sorting)")
            raw_input = numbers

        if self.llm is None:
            raise RuntimeError("LLMClient required to execute GoO")
        if self.logger is None:
            self.logger = GoTLogger(run_id=str(uuid.uuid4())[:8])

        t0 = time.time()
        self.build_decompose_merge_plan(raw_input, chunk_size)

        for idx, step in enumerate(self.steps):
            self.logger.goo_step(idx, step.to_dict())
            outputs = self._execute_step(step)
            self.registry[step.output_key] = [t.id for t in outputs]
            self.execution_trace.append(
                {
                    "step_index": idx,
                    "step_id": step.id,
                    "op": step.op,
                    "output_key": step.output_key,
                    "output_ids": [t.id for t in outputs],
                }
            )

        final_key = self.steps[-1].output_key
        final_ids = self.registry.get(final_key, [])
        final_thoughts = [self.graph.get_node(i) for i in final_ids if i in self.graph.nodes]
        final_thoughts = [t for t in final_thoughts if t.active]
        if not final_thoughts:
            active = self.graph.active_nodes()
            final_thoughts = sorted(
                active,
                key=lambda t: t.score if t.score is not None else float("-inf"),
                reverse=True,
            )[:1]

        best = final_thoughts[0] if final_thoughts else None
        eval_fields = self.task.evaluate_result(best, raw_input)
        result = {
            "run_id": self.logger.run_id,
            "task": getattr(self.task, "name", "unknown"),
            "elapsed_s": round(time.time() - t0, 3),
            "input": self.task.describe_input(raw_input),
            "chunk_size": chunk_size,
            "generate_k": self.generate_k,
            "aggregate_k": self.aggregate_k,
            "final_content": best.content if best else None,
            "final_score": best.score if best else None,
            "final_thought_id": best.id if best else None,
            "graph_stats": self.graph.to_dict()["stats"],
            "llm_usage": self.llm.usage_summary(),
            "goo_steps": len(self.steps),
            "log_path": str(self.logger.log_path),
            **eval_fields,
        }
        self.logger.run_end(result)
        return result

    def _resolve_inputs(self, step: GoOStep) -> list[Thought]:
        nodes: list[Thought] = []
        seen: set[str] = set()
        for key in step.input_keys:
            ids = self.registry.get(key, [])
            for tid in ids:
                if tid in seen or tid not in self.graph.nodes:
                    continue
                node = self.graph.get_node(tid)
                if node.active:
                    nodes.append(node)
                    seen.add(tid)
        return nodes

    def _execute_step(self, step: GoOStep) -> list[Thought]:
        op = step.op
        if op == "Seed":
            chunk = step.params["chunk"]
            meta = self.task.seed_metadata(chunk, int(step.params["chunk_index"]))
            thought = Thought(
                content=chunk,
                state_signature=self.task.state_signature_for(chunk, None),
                operation_type="Seed",
                metadata=meta,
            )
            self.graph.add_node(thought)
            if self.logger:
                self.logger.node_created(thought.to_dict())
            return [thought]

        inputs = self._resolve_inputs(step)

        if op == "Generate":
            assert len(inputs) == 1
            gen = Generate(
                task=self.task,
                llm=self.llm,  # type: ignore[arg-type]
                k=int(step.params.get("k", self.generate_k)),
                logger=self.logger,
            )
            return gen.execute(self.graph, inputs)

        if op == "Aggregate":
            agg = Aggregate(
                task=self.task,
                llm=self.llm,  # type: ignore[arg-type]
                k_attempts=int(step.params.get("k_attempts", self.aggregate_k)),
                logger=self.logger,
            )
            return agg.execute(self.graph, inputs)

        if op == "Score":
            return Score(task=self.task, logger=self.logger).execute(self.graph, inputs)

        if op == "Refine":
            # Refine each candidate independently (feedback loop per thought)
            out: list[Thought] = []
            refine_op = Refine(
                task=self.task,
                llm=self.llm,  # type: ignore[arg-type]
                logger=self.logger,
                only_if_imperfect=self.refine_when_imperfect,
            )
            for node in inputs:
                # Always attempt refine path; Refine itself no-ops if perfect
                # but we force refine when score details show error_scope > 0
                needs = True
                details = node.metadata.get("score_details") or {}
                err_scope = details.get("error_scope")
                if err_scope is None:
                    # Non-sorting tasks may only expose score; treat max-ish as perfect via detect_error
                    err_scope = 0 if self.task.detect_error(node) is None else 1
                if self.refine_when_imperfect and err_scope == 0:
                    needs = False
                if not needs and self.task.detect_error(node) is None:
                    out.append(node)
                    continue
                if err_scope > 0 or self.task.detect_error(node):
                    out.extend(refine_op.execute(self.graph, [node]))
                else:
                    out.append(node)
            return out

        if op == "KeepBest":
            return KeepBest(
                n=int(step.params.get("n", self.keep_best_n)),
                logger=self.logger,
            ).execute(self.graph, inputs)

        raise ValueError(f"Unknown GoO operation: {op}")

    def snapshot(self) -> dict[str, Any]:
        return {
            "graph": self.graph.to_dict(),
            "registry": self.registry,
            "execution_trace": self.execution_trace,
            "steps": [s.to_dict() for s in self.steps],
        }
