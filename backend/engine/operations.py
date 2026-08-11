"""Thought transformations (paper §3.2) + Score / KeepBest / Discard (§3.3).

Each Operation.execute(graph, input_nodes) -> output_nodes mutates the graph
and returns the produced (or retained) thoughts. Aggregate creates genuine
multi-parent graph edges — GoT's differentiator from Tree of Thoughts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from .graph import Graph
from .thought import Thought

if TYPE_CHECKING:
    from tasks.base_task import BaseTask
    from engine.llm_client import LLMClient
    from engine.logger import GoTLogger


class Operation(ABC):
    """Common interface for all Graph-of-Operations steps."""

    name: str = "Operation"

    def __init__(self, logger: GoTLogger | None = None) -> None:
        self.logger = logger

    @abstractmethod
    def execute(self, graph: Graph, input_nodes: list[Thought]) -> list[Thought]:
        raise NotImplementedError


class Generate(Operation):
    """Generate(t, k): one parent → k children via LLM (paper §3.2)."""

    name = "Generate"

    def __init__(
        self,
        task: BaseTask,
        llm: LLMClient,
        k: int = 1,
        logger: GoTLogger | None = None,
        system_prompt: str | None = None,
    ) -> None:
        super().__init__(logger)
        self.task = task
        self.llm = llm
        self.k = k
        self.system_prompt = system_prompt or (
            "You are a careful assistant. Follow the instruction exactly. "
            "Output only the requested data structure, no commentary."
        )

    def execute(self, graph: Graph, input_nodes: list[Thought]) -> list[Thought]:
        if len(input_nodes) != 1:
            raise ValueError("Generate expects exactly one input thought")
        parent = input_nodes[0]
        if self.logger:
            self.logger.operation_start(self.name, [parent.id], k=self.k)

        outputs: list[Thought] = []
        for i in range(self.k):
            prompt = self.task.generate_prompt(parent)
            # Slightly higher temperature so imperfect sorts appear and Refine fires
            raw = self.llm.chat_completion(
                prompt, system=self.system_prompt, temperature=0.7
            )
            content = self.task.parse_generate(raw, parent)
            raw_source = parent.metadata.get("source_chunk", parent.metadata.get("source_multiset"))
            if raw_source is None:
                raw_source = parent.content
            child = Thought(
                content=content,
                state_signature=self.task.state_signature_for(content, parent),
                parents=[parent.id],
                operation_type=self.name,
                metadata={
                    "raw_llm": raw[:300],
                    "generate_index": i,
                    "chunk_index": parent.metadata.get("chunk_index"),
                    # Must be the actual subset/passage, never the integer index —
                    # set intersection scores with set(source_chunk).
                    "source_chunk": raw_source if isinstance(raw_source, list) else parent.metadata.get("source_chunk"),
                    "source_multiset": raw_source if isinstance(raw_source, list) else None,
                    "source_passage": raw_source if isinstance(raw_source, str) else parent.metadata.get("source_passage"),
                    "set_a": parent.metadata.get("set_a"),
                },
            )
            # Equivalence merge: if an active thought already covers the same
            # source multiset *and* identical content, reuse it (node savings).
            existing = graph.find_equivalent(child, self.task.is_equivalent)
            if existing is not None and existing.content == child.content:
                if self.logger:
                    self.logger.info(
                        f"Generate equivalence hit: reusing {existing.id}",
                        new_attempt=child.content,
                    )
                # Do not append the same node twice — KeepBest would then
                # "discard" the duplicate and kill the kept thought.
                if all(o.id != existing.id for o in outputs):
                    outputs.append(existing)
                continue

            graph.add_node(child)
            graph.add_edge(parent.id, child.id)
            if self.logger:
                self.logger.node_created(child.to_dict())
            outputs.append(child)

        if self.logger:
            self.logger.operation_end(
                self.name, [parent.id], [t.id for t in outputs], k=self.k
            )
        return outputs


class Aggregate(Operation):
    """Aggregate(t1..tk): k parents → 1 child with multi-parent edges.

    This is the key GoT differentiator from ToT (paper §3.2 Aggregation).
    """

    name = "Aggregate"

    def __init__(
        self,
        task: BaseTask,
        llm: LLMClient,
        k_attempts: int = 1,
        logger: GoTLogger | None = None,
        system_prompt: str | None = None,
    ) -> None:
        super().__init__(logger)
        self.task = task
        self.llm = llm
        self.k_attempts = k_attempts
        self.system_prompt = system_prompt or (
            "You carefully combine intermediate solutions. "
            "Follow the user instruction exactly and output only the requested structure."
        )

    def execute(self, graph: Graph, input_nodes: list[Thought]) -> list[Thought]:
        # Dedupe by id — a chunk can legally contribute the same thought twice
        # after Generate k>1 equivalence reuse.
        unique: list[Thought] = []
        seen: set[str] = set()
        for t in input_nodes:
            if t.id in seen:
                continue
            seen.add(t.id)
            unique.append(t)
        input_nodes = unique
        if len(input_nodes) < 2:
            if self.logger:
                self.logger.warning(
                    "Aggregate skipped — need ≥2 distinct parents "
                    f"(got {len(input_nodes)}): {[t.id for t in input_nodes]}"
                )
            return input_nodes
        parent_ids = [t.id for t in input_nodes]
        if self.logger:
            self.logger.operation_start(self.name, parent_ids, k_attempts=self.k_attempts)

        before = graph.node_count()
        candidates: list[Thought] = []

        for i in range(self.k_attempts):
            prompt = self.task.aggregate_prompt(input_nodes)
            raw = self.llm.chat_completion(
                prompt, system=self.system_prompt, temperature=0.55
            )
            content = self.task.parse_aggregate(raw, input_nodes)
            # Prefer task.aggregate for a deterministic structural merge of
            # metadata/signature; content comes from the LLM parse above.
            base = self.task.aggregate(input_nodes)
            child = Thought(
                content=content,
                state_signature=base.state_signature,
                parents=parent_ids,
                operation_type=self.name,
                metadata={
                    **base.metadata,
                    "raw_llm": raw[:300],
                    "aggregate_attempt": i,
                    "parent_ids": parent_ids,
                },
            )
            graph.add_node(child)
            for p in parent_ids:
                graph.add_edge(p, child.id)
            if self.logger:
                self.logger.node_created(child.to_dict())
            candidates.append(child)

        after = graph.node_count()
        # Multi-parent merge event — log on the first (primary) candidate;
        # KeepBest later prunes extras. Active-set shrinks at KeepBest time.
        primary = candidates[0]
        graph.record_merge_counts(
            "aggregate_multi_parent",
            before=before,
            after=after,
            parents=parent_ids,
            child=primary.id,
        )
        if self.logger:
            self.logger.merge_event(
                parent_ids=parent_ids,
                child_id=primary.id,
                nodes_before=before,
                nodes_after=after,
                all_candidate_ids=[c.id for c in candidates],
                note=(
                    "Genuine multi-parent graph merge: edges from each parent "
                    "into the aggregated child (ToT cannot express this)."
                ),
            )
            self.logger.operation_end(
                self.name, parent_ids, [c.id for c in candidates]
            )
        return candidates


class Refine(Operation):
    """Refine / ValidateAndImprove: feedback loop on a thought (paper §3.2).

    Path: programmatic error detect → LLM refine → deterministic fallback.
    """

    name = "Refine"

    def __init__(
        self,
        task: BaseTask,
        llm: LLMClient,
        logger: GoTLogger | None = None,
        only_if_imperfect: bool = True,
    ) -> None:
        super().__init__(logger)
        self.task = task
        self.llm = llm
        self.only_if_imperfect = only_if_imperfect

    def execute(self, graph: Graph, input_nodes: list[Thought]) -> list[Thought]:
        if len(input_nodes) != 1:
            raise ValueError("Refine expects exactly one input thought")
        parent = input_nodes[0]
        if self.logger:
            self.logger.operation_start(self.name, [parent.id])

        error = self.task.detect_error(parent)
        if self.only_if_imperfect and error is None:
            if self.logger:
                self.logger.refine_event(
                    thought_id=parent.id,
                    error_detected="none",
                    before_content=parent.content,
                    after_content=parent.content,
                    path="no_fix_needed",
                )
                self.logger.operation_end(self.name, [parent.id], [parent.id])
            return [parent]

        before = parent.content
        path = "llm_fixed"
        refined_content: Any
        raw = ""
        try:
            prompt = self.task.refine_prompt(parent, error or "unknown error")
            raw = self.llm.chat_completion(
                prompt,
                system=(
                    "You fix incorrectly sorted lists. Preserve the exact multiset "
                    "of numbers from the original unsorted input. Output only the "
                    "corrected list."
                ),
            )
            refined_content = self.task.parse_refine(raw, parent)
            # Sanity: must be a list of ints of the right length-ish
            if not isinstance(refined_content, list) or not refined_content:
                raise ValueError("empty/invalid refine parse")
        except Exception as exc:  # noqa: BLE001
            path = "fallback_fixed"
            if self.logger:
                self.logger.warning(
                    f"LLM refine failed ({exc}); using deterministic fallback",
                    thought_id=parent.id,
                )
            fallback = self.task.refine(parent)  # deterministic
            refined_content = fallback.content

        source_multiset = parent.metadata.get("source_multiset")
        if source_multiset is None and parent.state_signature is not None:
            source_multiset = list(parent.state_signature)
        if source_multiset is None:
            source_multiset = list(before) if isinstance(before, list) else []

        child = Thought(
            content=refined_content,
            state_signature=parent.state_signature,
            parents=[parent.id],
            operation_type=self.name,
            metadata={
                "refine_path": path,
                "error_detected": error,
                "raw_llm": (raw[:300] if raw else None),
                "before_content": before,
                "source_multiset": list(source_multiset),
            },
        )
        graph.add_node(child)
        graph.add_edge(parent.id, child.id)  # refine edge; paper notes self-loop form
        # Supersede the imperfect parent in the active set (kept for lineage)
        graph.mark_discarded(parent.id)
        if self.logger:
            self.logger.node_created(child.to_dict())
            self.logger.refine_event(
                thought_id=child.id,
                error_detected=error or "unspecified",
                before_content=before,
                after_content=refined_content,
                path=path,
                parent_id=parent.id,
            )
            self.logger.operation_end(self.name, [parent.id], [child.id], path=path)
        return [child]


class Score(Operation):
    """Score thoughts with the task evaluator E (paper §3.3). Deterministic."""

    name = "Score"

    def __init__(self, task: BaseTask, logger: GoTLogger | None = None) -> None:
        super().__init__(logger)
        self.task = task

    def execute(self, graph: Graph, input_nodes: list[Thought]) -> list[Thought]:
        ids = [t.id for t in input_nodes]
        if self.logger:
            self.logger.operation_start(self.name, ids)

        for thought in input_nodes:
            details = self.task.score_details(thought)
            score = float(details["score"])
            thought.score = score
            thought.metadata["score_details"] = details
            if self.logger:
                self.logger.score_event(
                    thought_id=thought.id,
                    score=score,
                    inversions=details.get("inversions"),
                    error_scope=details.get("error_scope"),
                    details=details,
                )

        if self.logger:
            self.logger.operation_end(self.name, ids, ids)
        return input_nodes


class KeepBest(Operation):
    """Ranking R: keep top-n scored thoughts; discard the rest (paper §3.3)."""

    name = "KeepBest"

    def __init__(self, n: int = 1, logger: GoTLogger | None = None) -> None:
        super().__init__(logger)
        self.n = n

    def execute(self, graph: Graph, input_nodes: list[Thought]) -> list[Thought]:
        ids = [t.id for t in input_nodes]
        if self.logger:
            self.logger.operation_start(self.name, ids, keep_n=self.n)

        before_active = graph.node_count(active_only=True)
        # Unique by id first. Generate(k) can hand the same thought twice
        # (equivalence reuse). Ranking [A, A] with N=1 would put A in both
        # kept and discarded — then mark_discarded(A) empties the chunk and
        # the next Aggregate dies with "expects at least two input thoughts".
        unique: list[Thought] = []
        seen: set[str] = set()
        for t in input_nodes:
            if t.id in seen:
                continue
            seen.add(t.id)
            unique.append(t)
        ranked = sorted(
            unique,
            key=lambda t: (t.score is not None, t.score if t.score is not None else float("-inf")),
            reverse=True,
        )
        kept = ranked[: self.n]
        kept_ids = {t.id for t in kept}
        discarded = [t for t in ranked[self.n :] if t.id not in kept_ids]
        for d in discarded:
            graph.mark_discarded(d.id)
        after_active = graph.node_count(active_only=True)
        graph.record_merge_counts(
            "keepbest_prune",
            before=before_active,
            after=after_active,
            kept=[k.id for k in kept],
            discarded=[d.id for d in discarded],
        )
        if self.logger:
            self.logger.prune_event(
                kept_ids=[k.id for k in kept],
                discarded_ids=[d.id for d in discarded],
                reason=f"KeepBest(N={self.n}) — lower scores pruned",
                nodes_before=before_active,
                nodes_after_active=after_active,
                scores={t.id: t.score for t in input_nodes},
            )
            self.logger.operation_end(
                self.name, ids, [k.id for k in kept], discarded=[d.id for d in discarded]
            )
        return kept


class Discard(Operation):
    """Explicit discard of listed thoughts (paper allows V-/E- removal)."""

    name = "Discard"

    def execute(self, graph: Graph, input_nodes: list[Thought]) -> list[Thought]:
        ids = [t.id for t in input_nodes]
        if self.logger:
            self.logger.operation_start(self.name, ids)
        before = graph.node_count(active_only=True)
        for t in input_nodes:
            graph.mark_discarded(t.id)
        after = graph.node_count(active_only=True)
        if self.logger:
            self.logger.prune_event(
                kept_ids=[],
                discarded_ids=ids,
                reason="Explicit Discard",
                nodes_before=before,
                nodes_after_active=after,
            )
            self.logger.operation_end(self.name, ids, [])
        return []
