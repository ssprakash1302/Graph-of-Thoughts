"""Sorting task — paper §5.1 (numbers 0–9 with duplicates, merge-based GoT).

Primary score: paper error-scope X+Y converted to positive score
  max(n - error_scope, 0)  (higher is better for KeepBest).
Secondary metric: adjacent inversion count (logged alongside).
"""

from __future__ import annotations

import ast
import json
import random
import re
from collections import Counter
from typing import Any

from engine.thought import Thought
from tasks.base_task import BaseTask


class SortingTask(BaseTask):
    name = "sorting"

    def __init__(self, reference_input: list[int] | None = None) -> None:
        # Full original input — needed for frequency term Y in error-scope
        # when scoring partial chunks we use the chunk's own multiset.
        self.reference_input = reference_input

    # ---- helpers ----------------------------------------------------------

    @staticmethod
    def make_random_list(n: int = 48, low: int = 0, high: int = 9, seed: int | None = None) -> list[int]:
        rng = random.Random(seed)
        return [rng.randint(low, high) for _ in range(n)]

    @staticmethod
    def parse_number_list(raw: str) -> list[int]:
        """Extract a Python list of ints from messy LLM output."""
        text = raw.strip()
        # Prefer fenced / JSON-looking spans
        candidates: list[str] = []
        for match in re.finditer(r"\[[^\[\]]*\]", text, flags=re.DOTALL):
            candidates.append(match.group(0))
        if not candidates:
            candidates = [text]
        last_err: Exception | None = None
        for cand in reversed(candidates):  # prefer the last list in the reply
            try:
                val = json.loads(cand)
            except json.JSONDecodeError:
                try:
                    val = ast.literal_eval(cand)
                except (SyntaxError, ValueError) as e:
                    last_err = e
                    continue
            if isinstance(val, list) and all(isinstance(x, (int, float)) for x in val):
                return [int(x) for x in val]
        raise ValueError(f"Could not parse number list from LLM output: {raw[:200]} ({last_err})")

    @staticmethod
    def adjacent_inversions(seq: list[int]) -> int:
        """X in the paper: count of adjacent pairs out of order."""
        return sum(1 for i in range(len(seq) - 1) if seq[i] > seq[i + 1])

    @staticmethod
    def frequency_mismatch(output: list[int], reference: list[int], value_range=range(10)) -> int:
        """Y in the paper: Σ |count_out(i) - count_ref(i)| over i in 0..9."""
        c_out = Counter(output)
        c_ref = Counter(reference)
        return sum(abs(c_out[i] - c_ref[i]) for i in value_range)

    def error_scope(self, output: list[int], reference: list[int]) -> dict[str, Any]:
        x = self.adjacent_inversions(output)
        y = self.frequency_mismatch(output, reference)
        scope = x + y
        n = len(reference)
        positive = max(n - scope, 0)
        return {
            "X_adjacent_inversions": x,
            "Y_frequency_mismatch": y,
            "error_scope": scope,
            "inversions": x,  # secondary metric alias
            "score": float(positive),
            "n": n,
        }

    def _reference_for(self, thought: Thought) -> list[int]:
        """Multiset the thought should preserve (chunk or full input)."""
        if "source_multiset" in thought.metadata:
            return list(thought.metadata["source_multiset"])
        if thought.state_signature is not None:
            # state_signature is the sorted tuple of the source multiset
            return list(thought.state_signature)
        if isinstance(thought.content, list):
            return list(thought.content)
        return list(self.reference_input or [])

    # ---- BaseTask API -----------------------------------------------------

    def split_input(self, data: list[int], chunk_size: int) -> list[list[int]]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        return [list(data[i : i + chunk_size]) for i in range(0, len(data), chunk_size)]

    def seed_metadata(self, chunk: Any, chunk_index: int) -> dict[str, Any]:
        return {
            "chunk_index": chunk_index,
            "role": "unsorted_chunk",
            "source_multiset": list(chunk),
            "source_chunk": list(chunk),
        }

    def evaluate_result(self, best: Thought | None, raw_input: Any) -> dict[str, Any]:
        truth = sorted(list(raw_input))
        return {
            "ground_truth": truth,
            "correct": bool(best and best.content == truth),
        }

    @classmethod
    def make_demo_input(cls, **kwargs: Any) -> list[int]:
        return cls.make_random_list(
            n=int(kwargs.get("n", 48)),
            seed=kwargs.get("seed", 42),
        )

    def state_signature_for(self, content: Any, parent: Thought | None) -> Any:
        # Equivalence = same source multiset (sorted tuple), not the current order.
        if parent is not None and parent.state_signature is not None:
            return parent.state_signature
        if parent is not None and "source_multiset" in parent.metadata:
            return tuple(sorted(parent.metadata["source_multiset"]))
        if isinstance(content, list):
            return tuple(sorted(content))
        return None

    def is_equivalent(self, a: Thought, b: Thought) -> bool:
        return a.state_signature is not None and a.state_signature == b.state_signature

    def generate_prompt(self, thought: Thought) -> str:
        nums = thought.content
        return (
            "<Instruction> Sort the following list of numbers in ascending order. "
            "Output only the sorted list of numbers, no additional text. "
            "The output MUST contain exactly the same numbers with the same "
            "frequencies as the input (duplicates matter). </Instruction>\n"
            "<Example>\n"
            "Input: [3, 7, 0, 2, 8, 1, 2, 2]\n"
            "Output: [0, 1, 2, 2, 2, 3, 7, 8]\n"
            "</Example>\n"
            f"Input: {nums}\n"
            "Output:"
        )

    def aggregate_prompt(self, thoughts: list[Thought]) -> str:
        lists = [t.content for t in thoughts]
        lengths = [len(x) for x in lists]
        body = "\n".join(f"List {i + 1} (len={lengths[i]}): {lst}" for i, lst in enumerate(lists))
        return (
            "<Instruction> Merge the following sorted lists into one sorted list "
            "using a merge-sort style approach. Only output the final merged list "
            "without any additional text. Preserve all elements (duplicates matter). "
            "</Instruction>\n"
            "<Approach>\n"
            "1. Initialize an empty merged list and pointers for each input list.\n"
            "2. Repeatedly append the smallest head element among remaining lists.\n"
            "3. Append any leftovers.\n"
            "</Approach>\n"
            f"{body}\n"
            "Output:"
        )

    def refine_prompt(self, thought: Thought, error: str) -> str:
        reference = self._reference_for(thought)
        return (
            "<Instruction> The following two lists represent an unsorted list of "
            "numbers and a sorted variant of that list. The sorted variant is not "
            "correct. Fix the sorted variant so that it is correct. Make sure that "
            f"the output list is sorted ascending, has length {len(reference)}, and "
            "contains the same elements (same frequencies) as the input list. "
            "Output only the corrected list. </Instruction>\n"
            f"Error detected: {error}\n"
            f"Input: {reference}\n"
            f"Incorrectly Sorted: {thought.content}\n"
            "Output:"
        )

    def parse_generate(self, raw: str, parent: Thought) -> list[int]:
        return self.parse_number_list(raw)

    def parse_aggregate(self, raw: str, parents: list[Thought]) -> list[int]:
        return self.parse_number_list(raw)

    def parse_refine(self, raw: str, parent: Thought) -> list[int]:
        return self.parse_number_list(raw)

    def aggregate(self, thoughts: list[Thought]) -> Thought:
        """Structural merge: combined source multiset + multi-parent metadata."""
        combined_source: list[int] = []
        for t in thoughts:
            combined_source.extend(self._reference_for(t))
        # Deterministic merge of *contents* as a structural hint (LLM may replace)
        merged_content = sorted(sum((list(t.content) for t in thoughts), []))
        return Thought(
            content=merged_content,
            state_signature=tuple(sorted(combined_source)),
            parents=[t.id for t in thoughts],
            operation_type="Aggregate",
            metadata={
                "source_multiset": combined_source,
                "merged_from": [t.id for t in thoughts],
            },
        )

    def score(self, thought: Thought) -> float:
        return float(self.score_details(thought)["score"])

    def score_details(self, thought: Thought) -> dict[str, Any]:
        output = list(thought.content)
        reference = self._reference_for(thought)
        details = self.error_scope(output, reference)
        details["thought_id"] = thought.id
        return details

    def detect_error(self, thought: Thought) -> str | None:
        details = self.score_details(thought)
        if details["error_scope"] == 0:
            return None
        parts = []
        if details["X_adjacent_inversions"] > 0:
            # name first out-of-order adjacent pair
            seq = list(thought.content)
            for i in range(len(seq) - 1):
                if seq[i] > seq[i + 1]:
                    parts.append(
                        f"adjacent inversion at index {i}: {seq[i]} > {seq[i + 1]}"
                    )
                    break
        if details["Y_frequency_mismatch"] > 0:
            parts.append(
                f"frequency mismatch Y={details['Y_frequency_mismatch']} "
                f"vs source multiset {self._reference_for(thought)}"
            )
        return "; ".join(parts) if parts else f"error_scope={details['error_scope']}"

    def refine(self, thought: Thought) -> Thought:
        """Deterministic fallback: restore exact source multiset, sorted."""
        reference = self._reference_for(thought)
        fixed = sorted(reference)
        return Thought(
            content=fixed,
            state_signature=thought.state_signature or tuple(sorted(reference)),
            parents=[thought.id],
            operation_type="Refine",
            metadata={
                "refine_path": "fallback_fixed",
                "source_multiset": reference,
                "before_content": thought.content,
            },
        )
