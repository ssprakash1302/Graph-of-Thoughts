"""Document merging — paper §5.4 (merge overlapping docs; minimize duplication, keep info)."""

from __future__ import annotations

import re
from typing import Any

from engine.thought import Thought
from tasks.base_task import BaseTask

DEMO_DOCS = [
    (
        "NDA-A: The Receiving Party shall keep Confidential Information secret for 3 years. "
        "Governing law is Delaware. Disclosure to employees on a need-to-know basis is allowed."
    ),
    (
        "NDA-B: Confidential Information must not be disclosed for three (3) years. "
        "Return or destroy materials upon request. Governing law: State of Delaware."
    ),
    (
        "NDA-C: Residuals from unaided memory are excluded. "
        "The Receiving Party may share with affiliates under equivalent obligations. "
        "Term of confidentiality: 36 months."
    ),
    (
        "NDA-D: No public announcement without prior written consent. "
        "Injunctive relief is available for breach. Delaware law governs this agreement."
    ),
]


class DocumentMergingTask(BaseTask):
    name = "document_merging"

    def __init__(self, documents: list[str] | None = None) -> None:
        self.documents = list(documents or [])

    @classmethod
    def make_demo_input(cls, **kwargs: Any) -> dict[str, Any]:
        return {"documents": list(kwargs.get("documents") or DEMO_DOCS)}

    @staticmethod
    def _normalize_docs(raw: Any) -> list[str]:
        """Accept plain strings or {name, text} upload objects."""
        if raw is None:
            return []
        items = raw.get("documents", raw) if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            raise ValueError("document_merging input must be a list of texts or {name, text}")
        out: list[str] = []
        for d in items:
            if isinstance(d, dict):
                name = str(d.get("name") or "untitled.txt").strip()
                text = str(d.get("text") or "").strip()
                if not text:
                    continue
                out.append(f"[{name}]\n{text}")
            else:
                text = str(d).strip()
                if text:
                    out.append(text)
        return out

    def describe_input(self, raw_input: Any) -> Any:
        docs = self._normalize_docs(raw_input)
        names: list[str] = []
        if isinstance(raw_input, dict):
            for d in raw_input.get("documents") or []:
                if isinstance(d, dict) and d.get("name"):
                    names.append(str(d["name"]))
        return {
            "n_documents": len(docs),
            "filenames": names,
            "previews": [d[:100] + ("…" if len(d) > 100 else "") for d in docs],
        }

    def split_input(self, data: Any, chunk_size: int) -> list[str]:
        docs = self._normalize_docs(data)
        if not docs:
            raise ValueError("Upload at least two .txt documents to merge")
        self.documents = docs
        # chunk_size groups consecutive docs into a seed bundle (default 1 = one doc/seed)
        size = max(1, chunk_size)
        if size == 1:
            return docs
        return [
            "\n\n".join(docs[i : i + size])
            for i in range(0, len(docs), size)
        ]

    def seed_metadata(self, chunk: Any, chunk_index: int) -> dict[str, Any]:
        return {
            "chunk_index": chunk_index,
            "role": "document_chunk",
            "source_passage": chunk,
            "all_documents": list(self.documents),
        }

    def state_signature_for(self, content: Any, parent: Thought | None) -> Any:
        if parent is not None and parent.metadata.get("source_passage") is not None:
            return ("doc", parent.metadata["source_passage"][:160])
        return ("merged", str(content)[:160])

    def is_equivalent(self, a: Thought, b: Thought) -> bool:
        return a.state_signature is not None and a.state_signature == b.state_signature

    def generate_prompt(self, thought: Thought) -> str:
        return (
            "<Instruction> Rewrite the following NDA excerpt into a concise bullet list "
            "of distinct obligations/clauses. Keep legal meaning. "
            "Output plain text bullets starting with '- '. No preamble. </Instruction>\n"
            f"Document:\n{thought.content}\nOutput:"
        )

    def aggregate_prompt(self, thoughts: list[Thought]) -> str:
        parts = "\n\n".join(f"--- Draft {i+1} ---\n{t.content}" for i, t in enumerate(thoughts))
        return (
            "<Instruction> Merge the following clause drafts into ONE coherent NDA clause list. "
            "Remove duplicated ideas (keep a single clear wording). Preserve unique points. "
            "Output plain text bullets starting with '- '. </Instruction>\n"
            f"{parts}\nOutput:"
        )

    def refine_prompt(self, thought: Thought, error: str) -> str:
        return (
            "<Instruction> The merged clause list has issues (duplication or missing coverage). "
            "Fix it: deduplicate near-identical bullets and keep essential unique obligations. "
            "Output plain text bullets starting with '- '. </Instruction>\n"
            f"Error: {error}\nDraft:\n{thought.content}\nOutput:"
        )

    def _parse_bullets(self, raw: str) -> str:
        lines = []
        for line in raw.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith(("-", "*", "•")):
                s = s.lstrip("-*• ").strip()
            # drop common preambles
            if s.lower().startswith("here") and len(s) < 40:
                continue
            lines.append(f"- {s}")
        if not lines:
            # fallback: whole text as one bullet
            text = raw.strip()
            if not text:
                raise ValueError("empty document merge output")
            lines = [f"- {text}"]
        return "\n".join(lines)

    def parse_generate(self, raw: str, parent: Thought) -> str:
        return self._parse_bullets(raw)

    def parse_aggregate(self, raw: str, parents: list[Thought]) -> str:
        return self._parse_bullets(raw)

    def parse_refine(self, raw: str, parent: Thought) -> str:
        return self._parse_bullets(raw)

    def aggregate(self, thoughts: list[Thought]) -> Thought:
        combined = "\n".join(str(t.content) for t in thoughts)
        # Structural hint: concatenate then dedupe later via LLM/refine
        content = self._deterministic_dedupe(combined)
        return Thought(
            content=content,
            state_signature=("merged", content[:160]),
            parents=[t.id for t in thoughts],
            operation_type="Aggregate",
            metadata={
                "merged_from": [t.id for t in thoughts],
                "all_documents": list(self.documents),
            },
        )

    @staticmethod
    def _normalize_line(line: str) -> str:
        s = line.lower().strip()
        s = re.sub(r"^[-*•]\s*", "", s)
        s = re.sub(r"[^a-z0-9\s]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _deterministic_dedupe(self, text: str) -> str:
        seen: set[str] = set()
        out: list[str] = []
        for line in text.splitlines():
            raw = line.strip()
            if not raw:
                continue
            if not raw.startswith("-"):
                raw = f"- {raw}"
            key = self._normalize_line(raw)
            if key in seen:
                continue
            # near-duplicate: share long token prefix
            if any(key in s or s in key for s in seen if min(len(key), len(s)) > 24):
                continue
            seen.add(key)
            out.append(raw)
        return "\n".join(out)

    def _coverage_keys(self) -> set[str]:
        """Crude bag of content words from all source docs for coverage scoring."""
        bag: set[str] = set()
        for doc in self.documents:
            if isinstance(doc, dict):
                blob = str(doc.get("text") or "")
            else:
                blob = str(doc)
            for w in re.findall(r"[a-zA-Z]{4,}", blob.lower()):
                bag.add(w)
        return bag

    def score_details(self, thought: Thought) -> dict[str, Any]:
        text = str(thought.content or "")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        norms = [self._normalize_line(ln) for ln in lines]
        dupes = len(norms) - len(set(norms))
        # coverage: fraction of source content-words appearing in merge
        src = self._coverage_keys()
        if not src:
            coverage = 1.0
        else:
            present = sum(1 for w in src if w in text.lower())
            coverage = present / len(src)
        # error_scope: duplication penalty + missing coverage
        miss = int(round((1.0 - coverage) * 10))
        error = dupes + miss
        n = max(len(lines), 1)
        score = float(max(n * 2 - error, 0))
        return {
            "score": score,
            "error_scope": error,
            "inversions": dupes,  # secondary: duplicate bullet count
            "duplicates": dupes,
            "coverage": round(coverage, 3),
            "n_bullets": len(lines),
            "n": n,
        }

    def score(self, thought: Thought) -> float:
        return float(self.score_details(thought)["score"])

    def detect_error(self, thought: Thought) -> str | None:
        d = self.score_details(thought)
        # Only flag clear problems so Refine fires when useful
        if d["duplicates"] > 0 or d["coverage"] < 0.55:
            return (
                f"document merge issues: duplicates={d['duplicates']} "
                f"coverage={d['coverage']}"
            )
        return None

    def refine(self, thought: Thought) -> Thought:
        fixed = self._deterministic_dedupe(str(thought.content))
        return Thought(
            content=fixed,
            state_signature=thought.state_signature,
            parents=[thought.id],
            operation_type="Refine",
            metadata={
                "refine_path": "fallback_fixed",
                "before_content": thought.content,
                "all_documents": list(self.documents),
            },
        )

    def evaluate_result(self, best: Thought | None, raw_input: Any) -> dict[str, Any]:
        self.documents = self._normalize_docs(raw_input) or list(self.documents)
        ok = False
        if best is not None:
            d = self.score_details(best)
            ok = d["duplicates"] == 0 and d["coverage"] >= 0.5
        return {
            "ground_truth": {
                "note": "no single gold NDA; success = deduped merge with decent coverage",
                "n_source_docs": len(self.documents),
            },
            "correct": ok,
        }
