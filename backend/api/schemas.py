"""Pydantic request/response models for the GoT API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

TaskId = Literal[
    "sorting",
    "keyword_counting",
    "set_intersection",
    "document_merging",
]


class RunRequest(BaseModel):
    task: TaskId = "sorting"
    # Sorting
    numbers: list[int] | None = Field(
        default=None,
        description="Sorting: explicit list. If omitted with task=sorting, random 0-9 list.",
    )
    n: int = Field(default=48, ge=4, le=128, description="Sorting random length / set size hint")
    # Generic payload for non-sorting tasks (or override)
    payload: dict[str, Any] | None = Field(
        default=None,
        description="Task input object, e.g. {text,keywords} / {set_a,set_b} / {documents}",
    )
    chunk_size: int | None = Field(default=None, ge=1, le=64)
    seed: int | None = 42
    generate_k: int | None = Field(default=None, ge=1, le=10)
    aggregate_k: int | None = Field(default=None, ge=1, le=20)


class RunResponse(BaseModel):
    run_id: str
    status: str
    message: str
    task: str


class RunStatus(BaseModel):
    run_id: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
