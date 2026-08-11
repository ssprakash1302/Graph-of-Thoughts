"""Task plugin registry — engine stays agnostic; CLI/API resolve by name."""

from __future__ import annotations

from typing import Any, Type

from tasks.base_task import BaseTask
from tasks.document_merging_task import DocumentMergingTask
from tasks.keyword_counting_task import KeywordCountingTask
from tasks.set_intersection_task import SetIntersectionTask
from tasks.sorting_task import SortingTask

TASK_REGISTRY: dict[str, Type[BaseTask]] = {
    "sorting": SortingTask,
    "keyword_counting": KeywordCountingTask,
    "set_intersection": SetIntersectionTask,
    "document_merging": DocumentMergingTask,
}


def list_tasks() -> list[dict[str, str]]:
    return [
        {
            "id": "sorting",
            "label": "Sorting",
            "blurb": "Chunk → LLM-sort → pairwise Aggregate (paper §5.1)",
        },
        {
            "id": "keyword_counting",
            "label": "Keyword counting",
            "blurb": "Split text → count countries → Aggregate sums (paper §5.3)",
        },
        {
            "id": "set_intersection",
            "label": "Set intersection",
            "blurb": "Split B → intersect with A → Aggregate union (paper §5.2)",
        },
        {
            "id": "document_merging",
            "label": "Document merging",
            "blurb": "Normalize NDA excerpts → Aggregate without duplication (paper §5.4)",
        },
    ]


def create_task(task_id: str, raw_input: Any | None = None) -> BaseTask:
    if task_id not in TASK_REGISTRY:
        known = ", ".join(TASK_REGISTRY)
        raise ValueError(f"Unknown task '{task_id}'. Known: {known}")
    cls = TASK_REGISTRY[task_id]
    if task_id == "sorting":
        nums = raw_input if isinstance(raw_input, list) else None
        return SortingTask(reference_input=nums)
    if task_id == "keyword_counting":
        if isinstance(raw_input, dict):
            return KeywordCountingTask(
                full_text=str(raw_input.get("text", "")),
                keywords=raw_input.get("keywords"),
            )
        return KeywordCountingTask(full_text=str(raw_input or ""))
    if task_id == "set_intersection":
        if isinstance(raw_input, dict):
            return SetIntersectionTask(
                set_a=raw_input.get("set_a"),
                set_b=raw_input.get("set_b"),
            )
        return SetIntersectionTask()
    if task_id == "document_merging":
        docs = None
        if isinstance(raw_input, dict):
            docs = DocumentMergingTask._normalize_docs(raw_input)
        elif isinstance(raw_input, list):
            docs = DocumentMergingTask._normalize_docs(raw_input)
        return DocumentMergingTask(documents=docs)
    return cls()


def demo_input_for(task_id: str, **kwargs: Any) -> Any:
    cls = TASK_REGISTRY[task_id]
    return cls.make_demo_input(**kwargs)


def default_chunk_size(task_id: str) -> int:
    return {
        "sorting": 8,
        "keyword_counting": 2,  # sentences per passage
        "set_intersection": 8,
        "document_merging": 1,  # one document per seed
    }.get(task_id, 8)
