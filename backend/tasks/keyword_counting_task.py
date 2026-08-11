"""Keyword counting — paper §5.3 (count category keywords across passages, then Aggregate)."""

from __future__ import annotations

import ast
import json
import re
from collections import Counter
from typing import Any

from engine.thought import Thought
from tasks.base_task import BaseTask

# Compact country list for the demo (paper uses countries as the category).
DEFAULT_KEYWORDS = [
    "France",
    "Germany",
    "Italy",
    "Spain",
    "Canada",
    "Brazil",
    "Japan",
    "India",
    "China",
    "Australia",
    "Mexico",
    "Egypt",
    "Kenya",
    "Norway",
    "Sweden",
]


DEMO_TEXT = (
    "France and Germany signed a trade note. Later, Italy and Spain joined talks. "
    "A report mentioned Canada and Brazil as observers. In Asia, Japan and India "
    "expanded cooperation while China watched closely. Australia and Mexico sent "
    "delegates. Egypt and Kenya hosted a side event; Norway and Sweden published "
    "a joint statement. France appeared again in the appendix. Germany and Italy "
    "were listed twice in the summary table. Spain, Canada, and Brazil closed the day."
)


class KeywordCountingTask(BaseTask):
    name = "keyword_counting"

    def __init__(
        self,
        full_text: str | None = None,
        keywords: list[str] | None = None,
    ) -> None:
        self.full_text = full_text or ""
        self.keywords = keywords or list(DEFAULT_KEYWORDS)
        self._kw_lower = {k.lower(): k for k in self.keywords}

    @classmethod
    def make_demo_input(cls, **kwargs: Any) -> dict[str, Any]:
        return {
            "text": kwargs.get("text") or DEMO_TEXT,
            "keywords": kwargs.get("keywords") or list(DEFAULT_KEYWORDS),
        }

    def describe_input(self, raw_input: Any) -> Any:
        if isinstance(raw_input, dict):
            text = str(raw_input.get("text", ""))
            return {
                "text_preview": text[:240] + ("…" if len(text) > 240 else ""),
                "n_chars": len(text),
                "keywords": raw_input.get("keywords", self.keywords),
            }
        return {"text_preview": str(raw_input)[:240]}

    def split_input(self, data: Any, chunk_size: int) -> list[str]:
        """Split text into ~chunk_size-sentence passages (chunk_size = sentences/passage)."""
        if isinstance(data, dict):
            text = str(data.get("text", ""))
            self.full_text = text
            if data.get("keywords"):
                self.keywords = list(data["keywords"])
                self._kw_lower = {k.lower(): k for k in self.keywords}
        else:
            text = str(data)
            self.full_text = text
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        if not sentences:
            sentences = [text]
        size = max(1, chunk_size)
        return [
            " ".join(sentences[i : i + size])
            for i in range(0, len(sentences), size)
        ]

    def seed_metadata(self, chunk: Any, chunk_index: int) -> dict[str, Any]:
        return {
            "chunk_index": chunk_index,
            "role": "passage",
            "source_passage": chunk,
            "keywords": self.keywords,
        }

    def ground_truth_counts(self, text: str | None = None) -> dict[str, int]:
        src = text if text is not None else self.full_text
        counts: Counter[str] = Counter()
        lower = src.lower()
        for low, canon in self._kw_lower.items():
            # word-boundary-ish count
            counts[canon] = len(re.findall(rf"\b{re.escape(low)}\b", lower))
        return {k: v for k, v in counts.items() if v > 0}

    def state_signature_for(self, content: Any, parent: Thought | None) -> Any:
        if parent is not None and parent.metadata.get("source_passage") is not None:
            return ("passage", parent.metadata["source_passage"])
        if parent is not None and parent.state_signature is not None:
            return parent.state_signature
        if isinstance(content, dict):
            return ("counts", tuple(sorted((k, int(v)) for k, v in content.items())))
        return ("raw", str(content)[:120])

    def is_equivalent(self, a: Thought, b: Thought) -> bool:
        return a.state_signature is not None and a.state_signature == b.state_signature

    def generate_prompt(self, thought: Thought) -> str:
        kws = ", ".join(self.keywords)
        return (
            "<Instruction> Count how many times each of the following country names "
            f"appears in the passage: {kws}. "
            "Return ONLY a JSON object mapping country -> integer count. "
            "Omit countries with count 0. No commentary. </Instruction>\n"
            f"Passage: {thought.content}\n"
            "Output:"
        )

    def aggregate_prompt(self, thoughts: list[Thought]) -> str:
        parts = "\n".join(f"Counts {i+1}: {t.content}" for i, t in enumerate(thoughts))
        return (
            "<Instruction> Merge the following keyword-count JSON objects by summing "
            "counts for the same keys. Return ONLY the merged JSON object. </Instruction>\n"
            f"{parts}\nOutput:"
        )

    def refine_prompt(self, thought: Thought, error: str) -> str:
        passage = thought.metadata.get("source_passage") or self.full_text
        return (
            "<Instruction> The keyword counts are incorrect for the passage. "
            "Recompute exact counts for the listed countries and return ONLY corrected JSON. "
            f"</Instruction>\nError: {error}\n"
            f"Countries: {self.keywords}\nPassage: {passage}\n"
            f"Incorrect counts: {thought.content}\nOutput:"
        )

    def _parse_counts(self, raw: str) -> dict[str, int]:
        text = raw.strip()
        # Grab outermost {...}
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        blob = m.group(0) if m else text
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            data = ast.literal_eval(blob)
        if not isinstance(data, dict):
            raise ValueError("counts must be a JSON object")
        out: dict[str, int] = {}
        for k, v in data.items():
            canon = self._kw_lower.get(str(k).lower(), str(k))
            out[canon] = int(v)
        return {k: v for k, v in out.items() if v > 0}

    def parse_generate(self, raw: str, parent: Thought) -> dict[str, int]:
        return self._parse_counts(raw)

    def parse_aggregate(self, raw: str, parents: list[Thought]) -> dict[str, int]:
        return self._parse_counts(raw)

    def parse_refine(self, raw: str, parent: Thought) -> dict[str, int]:
        return self._parse_counts(raw)

    def aggregate(self, thoughts: list[Thought]) -> Thought:
        merged: Counter[str] = Counter()
        for t in thoughts:
            if isinstance(t.content, dict):
                merged.update({k: int(v) for k, v in t.content.items()})
        content = dict(merged)
        return Thought(
            content=content,
            state_signature=("counts", tuple(sorted(content.items()))),
            parents=[t.id for t in thoughts],
            operation_type="Aggregate",
            metadata={"merged_from": [t.id for t in thoughts], "scope": "full_text"},
        )

    def score_details(self, thought: Thought) -> dict[str, Any]:
        predicted = thought.content if isinstance(thought.content, dict) else {}
        # Local ground truth: passage-level if available, else full text
        passage = thought.metadata.get("source_passage")
        truth = self.ground_truth_counts(passage) if passage else self.ground_truth_counts()
        keys = set(truth) | set(predicted)
        error = sum(abs(int(predicted.get(k, 0)) - int(truth.get(k, 0))) for k in keys)
        # Positive score: higher better; cap relative to total true mentions
        total = max(sum(truth.values()), 1)
        score = float(max(total - error, 0))
        return {
            "score": score,
            "error_scope": error,
            "inversions": None,
            "predicted": predicted,
            "truth": truth,
            "n": total,
        }

    def score(self, thought: Thought) -> float:
        return float(self.score_details(thought)["score"])

    def detect_error(self, thought: Thought) -> str | None:
        d = self.score_details(thought)
        if d["error_scope"] == 0:
            return None
        return f"keyword count error_scope={d['error_scope']} pred={d['predicted']} truth={d['truth']}"

    def refine(self, thought: Thought) -> Thought:
        passage = thought.metadata.get("source_passage")
        fixed = self.ground_truth_counts(passage) if passage else self.ground_truth_counts()
        return Thought(
            content=fixed,
            state_signature=thought.state_signature,
            parents=[thought.id],
            operation_type="Refine",
            metadata={
                "refine_path": "fallback_fixed",
                "source_passage": passage,
                "before_content": thought.content,
            },
        )

    def evaluate_result(self, best: Thought | None, raw_input: Any) -> dict[str, Any]:
        if isinstance(raw_input, dict):
            self.full_text = str(raw_input.get("text", self.full_text))
        truth = self.ground_truth_counts()
        pred = best.content if best and isinstance(best.content, dict) else {}
        return {
            "ground_truth": truth,
            "correct": pred == truth,
        }
