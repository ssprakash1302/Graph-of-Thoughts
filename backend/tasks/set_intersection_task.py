"""Set intersection — paper §5.2 (split B, intersect each subset with A, Aggregate unions)."""

from __future__ import annotations

import ast
import json
import random
import re
from typing import Any

from engine.thought import Thought
from tasks.base_task import BaseTask


class SetIntersectionTask(BaseTask):
    name = "set_intersection"

    def __init__(
        self,
        set_a: list[Any] | None = None,
        set_b: list[Any] | None = None,
    ) -> None:
        self.set_a = list(set_a or [])
        self.set_b = list(set_b or [])

    @classmethod
    def make_demo_input(cls, **kwargs: Any) -> dict[str, Any]:
        n = int(kwargs.get("n", 32))
        seed = kwargs.get("seed", 42)
        rng = random.Random(seed)
        universe = list(range(80))
        set_a = sorted(rng.sample(universe, n))
        overlap = set_a[: n // 2]
        rest = [x for x in universe if x not in set_a]
        set_b = sorted(overlap + rng.sample(rest, n - len(overlap)))
        rng.shuffle(set_b)
        return {"set_a": set_a, "set_b": set_b}

    def describe_input(self, raw_input: Any) -> Any:
        if isinstance(raw_input, dict):
            return {
                "set_a": raw_input.get("set_a"),
                "set_b": raw_input.get("set_b"),
                "n_a": len(raw_input.get("set_a") or []),
                "n_b": len(raw_input.get("set_b") or []),
            }
        return raw_input

    def split_input(self, data: Any, chunk_size: int) -> list[list[Any]]:
        if not isinstance(data, dict):
            raise ValueError("set_intersection input must be {set_a, set_b}")
        self.set_a = list(data["set_a"])
        self.set_b = list(data["set_b"])
        size = max(1, chunk_size)
        return [list(self.set_b[i : i + size]) for i in range(0, len(self.set_b), size)]

    def seed_metadata(self, chunk: Any, chunk_index: int) -> dict[str, Any]:
        return {
            "chunk_index": chunk_index,
            "role": "subset_b",
            "set_a": list(self.set_a),
            "source_chunk": list(chunk),
        }

    def true_intersection(self) -> list[Any]:
        return sorted(set(self.set_a) & set(self.set_b))

    def state_signature_for(self, content: Any, parent: Thought | None) -> Any:
        if parent is not None and parent.metadata.get("source_chunk") is not None:
            a = tuple(sorted(parent.metadata.get("set_a") or self.set_a))
            b = tuple(sorted(parent.metadata["source_chunk"]))
            return ("intersect_scope", a, b)
        if isinstance(content, list):
            return ("set", tuple(sorted(content)))
        return ("raw", str(content))

    def is_equivalent(self, a: Thought, b: Thought) -> bool:
        return a.state_signature is not None and a.state_signature == b.state_signature

    def generate_prompt(self, thought: Thought) -> str:
        set_a = thought.metadata.get("set_a") or self.set_a
        return (
            "<Instruction> Compute the set intersection of Set A and Subset B. "
            "Return ONLY a JSON array of the common elements, sorted ascending. "
            "No duplicates. </Instruction>\n"
            f"Set A: {set_a}\n"
            f"Subset B: {thought.content}\n"
            "Output:"
        )

    def aggregate_prompt(self, thoughts: list[Thought]) -> str:
        parts = "\n".join(
            f"Partial intersection {i+1}: {t.content}" for i, t in enumerate(thoughts)
        )
        return (
            "<Instruction> Merge the following partial intersection lists into one set "
            "(union of elements). Return ONLY a sorted JSON array with unique elements. "
            "</Instruction>\n"
            f"{parts}\nOutput:"
        )

    def refine_prompt(self, thought: Thought, error: str) -> str:
        set_a = thought.metadata.get("set_a") or self.set_a
        scope = thought.metadata.get("source_chunk")
        return (
            "<Instruction> The intersection result is wrong. Fix it. "
            "If a source subset is provided, intersect Set A with that subset only; "
            "otherwise return the full A∩B. Output ONLY a sorted JSON array. </Instruction>\n"
            f"Error: {error}\nSet A: {set_a}\n"
            f"Subset B (optional): {scope}\n"
            f"Incorrect: {thought.content}\nOutput:"
        )

    def _parse_list(self, raw: str) -> list[Any]:
        text = raw.strip()
        m = re.search(r"\[[^\[\]]*\]", text, flags=re.DOTALL)
        blob = m.group(0) if m else text
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            data = ast.literal_eval(blob)
        if not isinstance(data, list):
            raise ValueError("expected a JSON array")
        return sorted(set(data), key=lambda x: (str(type(x)), x))

    def parse_generate(self, raw: str, parent: Thought) -> list[Any]:
        return self._parse_list(raw)

    def parse_aggregate(self, raw: str, parents: list[Thought]) -> list[Any]:
        return self._parse_list(raw)

    def parse_refine(self, raw: str, parent: Thought) -> list[Any]:
        return self._parse_list(raw)

    def aggregate(self, thoughts: list[Thought]) -> Thought:
        merged: set[Any] = set()
        for t in thoughts:
            if isinstance(t.content, list):
                merged.update(t.content)
        content = sorted(merged, key=lambda x: (str(type(x)), x))
        return Thought(
            content=content,
            state_signature=("set", tuple(content)),
            parents=[t.id for t in thoughts],
            operation_type="Aggregate",
            metadata={
                "merged_from": [t.id for t in thoughts],
                "set_a": list(self.set_a),
                "scope": "union_of_partial_intersections",
            },
        )

    def _expected_for(self, thought: Thought) -> list[Any]:
        set_a = set(thought.metadata.get("set_a") or self.set_a)
        scope = thought.metadata.get("source_chunk")
        if isinstance(scope, (list, tuple, set)):
            return sorted(set_a & set(scope))
        return self.true_intersection()

    def score_details(self, thought: Thought) -> dict[str, Any]:
        pred = set(thought.content) if isinstance(thought.content, list) else set()
        truth = set(self._expected_for(thought))
        extra = len(pred - truth)
        missing = len(truth - pred)
        error = extra + missing
        n = max(len(truth), 1)
        return {
            "score": float(max(n - error, 0)),
            "error_scope": error,
            "inversions": None,
            "extra": extra,
            "missing": missing,
            "predicted": sorted(pred, key=lambda x: (str(type(x)), x)),
            "truth": sorted(truth, key=lambda x: (str(type(x)), x)),
            "n": n,
        }

    def score(self, thought: Thought) -> float:
        return float(self.score_details(thought)["score"])

    def detect_error(self, thought: Thought) -> str | None:
        d = self.score_details(thought)
        if d["error_scope"] == 0:
            return None
        return (
            f"set intersection error_scope={d['error_scope']} "
            f"extra={d['extra']} missing={d['missing']}"
        )

    def refine(self, thought: Thought) -> Thought:
        fixed = self._expected_for(thought)
        return Thought(
            content=fixed,
            state_signature=thought.state_signature,
            parents=[thought.id],
            operation_type="Refine",
            metadata={
                "refine_path": "fallback_fixed",
                "set_a": thought.metadata.get("set_a") or self.set_a,
                "source_chunk": thought.metadata.get("source_chunk"),
                "before_content": thought.content,
            },
        )

    def evaluate_result(self, best: Thought | None, raw_input: Any) -> dict[str, Any]:
        if isinstance(raw_input, dict):
            self.set_a = list(raw_input.get("set_a") or self.set_a)
            self.set_b = list(raw_input.get("set_b") or self.set_b)
        truth = self.true_intersection()
        pred = (
            sorted(set(best.content), key=lambda x: (str(type(x)), x))
            if best and isinstance(best.content, list)
            else []
        )
        return {"ground_truth": truth, "correct": pred == truth}
