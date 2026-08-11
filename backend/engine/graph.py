"""Graph of Thoughts + Graph Reasoning State (paper §3.1, §4.5).

G stores vertices (Thought) and directed edges (parent → child).
Node-count history supports the paper's efficiency claim: aggregation
and KeepBest reduce redundant work (N before → M after).
"""

from __future__ import annotations

from typing import Any, Callable

from .thought import Thought


class Graph:
    """Directed graph of thoughts (the GRS-backed reasoning graph)."""

    def __init__(self) -> None:
        self.nodes: dict[str, Thought] = {}
        # adjacency: parent_id -> [child_id, ...]
        self.edges: list[tuple[str, str]] = []
        self.node_count_history: list[dict[str, Any]] = []
        self._record_count("init")

    # ---- mutations --------------------------------------------------------

    def add_node(self, thought: Thought) -> Thought:
        if thought.id in self.nodes:
            raise ValueError(f"Node {thought.id} already exists")
        self.nodes[thought.id] = thought
        self._record_count("add_node", thought_id=thought.id, op=thought.operation_type)
        return thought

    def add_edge(self, parent_id: str, child_id: str) -> None:
        if parent_id not in self.nodes or child_id not in self.nodes:
            raise KeyError(f"Cannot add edge {parent_id}→{child_id}: missing node")
        edge = (parent_id, child_id)
        if edge not in self.edges:
            self.edges.append(edge)
        parent = self.nodes[parent_id]
        child = self.nodes[child_id]
        if child_id not in parent.children:
            parent.children.append(child_id)
        if parent_id not in child.parents:
            child.parents.append(parent_id)

    def get_node(self, node_id: str) -> Thought:
        return self.nodes[node_id]

    def remove_node(self, node_id: str) -> None:
        """Hard-remove a node (rare). Prefer mark_discarded for KeepBest."""
        if node_id not in self.nodes:
            return
        node = self.nodes[node_id]
        for p in list(node.parents):
            parent = self.nodes.get(p)
            if parent and node_id in parent.children:
                parent.children.remove(node_id)
        for c in list(node.children):
            child = self.nodes.get(c)
            if child and node_id in child.parents:
                child.parents.remove(node_id)
        self.edges = [(a, b) for a, b in self.edges if a != node_id and b != node_id]
        del self.nodes[node_id]
        self._record_count("remove_node", thought_id=node_id)

    def mark_discarded(self, node_id: str) -> None:
        node = self.nodes[node_id]
        node.discarded = True
        node.active = False

    # ---- queries ----------------------------------------------------------

    def active_nodes(self) -> list[Thought]:
        return [n for n in self.nodes.values() if n.active and not n.discarded]

    def node_count(self, active_only: bool = False) -> int:
        if active_only:
            return len(self.active_nodes())
        return len(self.nodes)

    def record_merge_counts(
        self,
        label: str,
        before: int,
        after: int,
        **extra: Any,
    ) -> dict[str, Any]:
        """Explicit before/after snapshot for Aggregate / KeepBest demos."""
        entry = {
            "event": "merge_count",
            "label": label,
            "before": before,
            "after": after,
            "delta": before - after,
            **extra,
        }
        self.node_count_history.append(entry)
        return entry

    def _record_count(self, reason: str, **extra: Any) -> None:
        self.node_count_history.append(
            {
                "event": "node_count",
                "reason": reason,
                "total": len(self.nodes),
                "active": self.node_count(active_only=True),
                **extra,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [{"source": a, "target": b} for a, b in self.edges],
            "node_count_history": list(self.node_count_history),
            "stats": {
                "total_nodes": len(self.nodes),
                "active_nodes": self.node_count(active_only=True),
                "edge_count": len(self.edges),
            },
        }

    def find_equivalent(
        self,
        thought: Thought,
        is_equivalent: Callable[[Thought, Thought], bool],
        candidates: list[Thought] | None = None,
    ) -> Thought | None:
        """Return an existing active thought equivalent to ``thought``, if any."""
        pool = candidates if candidates is not None else self.active_nodes()
        for other in pool:
            if other.id == thought.id:
                continue
            if is_equivalent(thought, other):
                return other
        return None
