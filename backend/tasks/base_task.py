"""Abstract task plugin interface.

A second task (document merging, keyword aggregation, …) can drop into
tasks/ and plug into the same engine without touching engine/ code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from engine.thought import Thought


class BaseTask(ABC):
    """Contract every GoT task plugin must implement."""

    name: str = "base"

    # ---- prompts / parsing (LLM side) ------------------------------------

    @abstractmethod
    def generate_prompt(self, thought: Thought) -> str:
        """Prompt used by Generate to produce a new thought from ``thought``."""

    @abstractmethod
    def aggregate_prompt(self, thoughts: list[Thought]) -> str:
        """Prompt used by Aggregate to merge multiple thoughts."""

    @abstractmethod
    def refine_prompt(self, thought: Thought, error: str) -> str:
        """Prompt used by Refine when an error was detected."""

    @abstractmethod
    def parse_generate(self, raw: str, parent: Thought) -> Any:
        """Parse LLM Generate response into thought content."""

    @abstractmethod
    def parse_aggregate(self, raw: str, parents: list[Thought]) -> Any:
        """Parse LLM Aggregate response into thought content."""

    @abstractmethod
    def parse_refine(self, raw: str, parent: Thought) -> Any:
        """Parse LLM Refine response into thought content."""

    # ---- graph / evaluation ----------------------------------------------

    @abstractmethod
    def aggregate(self, thoughts: list[Thought]) -> Thought:
        """Structural merge (signature/metadata); content may be overwritten by LLM parse."""

    @abstractmethod
    def score(self, thought: Thought) -> float:
        """Primary score (higher is better)."""

    @abstractmethod
    def score_details(self, thought: Thought) -> dict[str, Any]:
        """Rich score breakdown for logging (must include 'score')."""

    @abstractmethod
    def is_equivalent(self, a: Thought, b: Thought) -> bool:
        """Merge-detection: True if two thoughts cover the same logical state."""

    @abstractmethod
    def refine(self, thought: Thought) -> Thought:
        """Deterministic refine fallback (no LLM)."""

    @abstractmethod
    def detect_error(self, thought: Thought) -> str | None:
        """Return a human-readable error description, or None if OK."""

    @abstractmethod
    def state_signature_for(self, content: Any, parent: Thought | None) -> Any:
        """Build the normalized equivalence signature for content."""

    @abstractmethod
    def split_input(self, data: Any, chunk_size: int) -> list[Any]:
        """Decompose the raw task input into chunks for the GoO seed step."""

    def seed_metadata(self, chunk: Any, chunk_index: int) -> dict[str, Any]:
        """Extra metadata attached to each Seed thought (override per task)."""
        return {
            "chunk_index": chunk_index,
            "role": "seed_chunk",
            "source_chunk": chunk,
        }

    def evaluate_result(self, best: Thought | None, raw_input: Any) -> dict[str, Any]:
        """Task-specific final correctness fields for the run result dict."""
        return {
            "ground_truth": None,
            "correct": None,
        }

    def describe_input(self, raw_input: Any) -> Any:
        """JSON-serializable summary of the raw input for logs/API."""
        return raw_input

    @classmethod
    def make_demo_input(cls, **kwargs: Any) -> Any:
        """Build a default demo payload for CLI/UI."""
        raise NotImplementedError(f"{cls.__name__}.make_demo_input not implemented")
