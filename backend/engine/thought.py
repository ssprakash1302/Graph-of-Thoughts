"""Thought node — one vertex in the graph of thoughts (paper §3.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import uuid


@dataclass
class Thought:
    """A single LLM thought / partial solution.

    In sorting, ``content`` is the current number list and
    ``state_signature`` normalizes the *source* multiset so two
    branches covering the same elements can be recognised as equivalent
    even if they arrived via different paths (paper-style merge detection).
    """

    content: Any
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    state_signature: Any = None
    score: float | None = None
    parents: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    operation_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # GRS flags
    discarded: bool = False
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "state_signature": _sig_to_json(self.state_signature),
            "score": self.score,
            "parents": list(self.parents),
            "children": list(self.children),
            "operation_type": self.operation_type,
            "metadata": self.metadata,
            "discarded": self.discarded,
            "active": self.active,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Thought:
        return cls(
            id=data["id"],
            content=data["content"],
            state_signature=data.get("state_signature"),
            score=data.get("score"),
            parents=list(data.get("parents", [])),
            children=list(data.get("children", [])),
            operation_type=data.get("operation_type"),
            metadata=dict(data.get("metadata", {})),
            discarded=bool(data.get("discarded", False)),
            active=bool(data.get("active", True)),
        )


def _sig_to_json(sig: Any) -> Any:
    if isinstance(sig, tuple):
        return list(sig)
    return sig
