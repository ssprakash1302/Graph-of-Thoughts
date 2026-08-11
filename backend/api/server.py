"""FastAPI server — run GoT and stream engine events via SSE."""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env")

from api.schemas import RunRequest, RunResponse, RunStatus  # noqa: E402
from engine.graph_of_operations import GraphOfOperations  # noqa: E402
from engine.llm_client import LLMClient  # noqa: E402
from engine.logger import GoTLogger  # noqa: E402
from tasks.registry import (  # noqa: E402
    create_task,
    default_chunk_size,
    demo_input_for,
    list_tasks,
)

app = FastAPI(title="Graph of Thoughts API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LOG_DIR = BACKEND_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# In-memory run store (assessment-scale; not multi-tenant durable storage)
_runs: dict[str, dict[str, Any]] = {}
_queues: dict[str, asyncio.Queue] = {}
_loop: asyncio.AbstractEventLoop | None = None


@app.on_event("startup")
async def _startup() -> None:
    global _loop
    _loop = asyncio.get_running_loop()


def _push_event(run_id: str, event: dict[str, Any]) -> None:
    """Thread-safe enqueue of an engine event onto the run's asyncio.Queue."""
    q = _queues.get(run_id)
    loop = _loop
    if q is None or loop is None:
        return
    try:
        loop.call_soon_threadsafe(q.put_nowait, event)
    except RuntimeError:
        pass


def _execute_run(run_id: str, req: RunRequest) -> None:
    store = _runs[run_id]
    store["status"] = "running"
    try:
        task_id = req.task
        if req.payload is not None:
            raw_input: Any = req.payload
        elif task_id == "sorting":
            raw_input = (
                list(req.numbers)
                if req.numbers is not None
                else demo_input_for("sorting", n=req.n, seed=req.seed)
            )
        else:
            raw_input = demo_input_for(task_id, n=req.n, seed=req.seed)

        chunk_size = (
            req.chunk_size
            if req.chunk_size is not None
            else default_chunk_size(task_id)
        )

        def on_event(event: dict[str, Any]) -> None:
            store.setdefault("events", []).append(event)
            if event.get("event") in {
                "node_created",
                "merge",
                "refine",
                "score",
                "prune",
                "goo_step",
                "run_end",
            }:
                snap = store.get("controller")
                if snap is not None:
                    event = {
                        **event,
                        "graph_snapshot": snap.graph.to_dict(),
                    }
            _push_event(run_id, event)

        logger = GoTLogger(
            run_id=run_id,
            log_dir=LOG_DIR,
            event_callback=on_event,
            also_console=True,
        )
        llm = LLMClient(logger=logger)
        task = create_task(task_id, raw_input)
        goo = GraphOfOperations(
            task=task,
            llm=llm,
            logger=logger,
            generate_k=req.generate_k,
            aggregate_k=req.aggregate_k,
        )
        store["controller"] = goo
        result = goo.run(raw_input=raw_input, chunk_size=chunk_size)
        store["result"] = result
        store["snapshot"] = goo.snapshot()
        store["status"] = "completed"

        (LOG_DIR / f"{run_id}.graph.json").write_text(
            json.dumps(store["snapshot"], indent=2, default=str), encoding="utf-8"
        )
        (LOG_DIR / f"{run_id}.result.json").write_text(
            json.dumps(result, indent=2, default=str), encoding="utf-8"
        )
        _push_event(run_id, {"event": "stream_end", "run_id": run_id, "status": "completed"})
    except Exception as exc:  # noqa: BLE001
        store["status"] = "error"
        store["error"] = str(exc)
        _push_event(
            run_id,
            {"event": "error", "run_id": run_id, "message": str(exc), "status": "error"},
        )
        _push_event(run_id, {"event": "stream_end", "run_id": run_id, "status": "error"})


@app.get("/tasks")
async def get_tasks() -> dict[str, Any]:
    return {"tasks": list_tasks()}


@app.post("/run", response_model=RunResponse)
async def start_run(req: RunRequest) -> RunResponse:
    run_id = f"api-{uuid.uuid4().hex[:8]}"
    _runs[run_id] = {
        "status": "queued",
        "result": None,
        "error": None,
        "events": [],
        "snapshot": None,
        "controller": None,
    }
    _queues[run_id] = asyncio.Queue()
    thread = threading.Thread(target=_execute_run, args=(run_id, req), daemon=True)
    thread.start()
    return RunResponse(
        run_id=run_id,
        status="queued",
        message=f"GoT run started ({req.task})",
        task=req.task,
    )

@app.get("/runs/{run_id}", response_model=RunStatus)
async def get_run(run_id: str) -> RunStatus:
    store = _runs.get(run_id)
    if not store:
        raise HTTPException(404, f"Unknown run_id {run_id}")
    return RunStatus(
        run_id=run_id,
        status=store["status"],
        result=store.get("result"),
        error=store.get("error"),
    )


@app.get("/runs/{run_id}/graph")
async def get_graph(run_id: str) -> dict[str, Any]:
    store = _runs.get(run_id)
    if not store:
        # Fall back to disk
        path = LOG_DIR / f"{run_id}.graph.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        raise HTTPException(404, f"Unknown run_id {run_id}")
    if store.get("snapshot"):
        return store["snapshot"]
    ctrl = store.get("controller")
    if ctrl is not None:
        return ctrl.snapshot()
    raise HTTPException(409, "Graph not ready yet")


@app.get("/runs/{run_id}/log")
async def get_log(run_id: str) -> dict[str, Any]:
    path = LOG_DIR / f"{run_id}.jsonl"
    if path.exists():
        events = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return {"run_id": run_id, "events": events}
    store = _runs.get(run_id)
    if store:
        return {"run_id": run_id, "events": store.get("events", [])}
    raise HTTPException(404, f"No log for run_id {run_id}")


@app.get("/stream/{run_id}")
async def stream_run(run_id: str) -> EventSourceResponse:
    if run_id not in _runs:
        raise HTTPException(404, f"Unknown run_id {run_id}")

    async def gen():
        q = _queues[run_id]
        # Replay any events already buffered
        for ev in list(_runs[run_id].get("events", [])):
            yield {"event": ev.get("event", "message"), "data": json.dumps(ev, default=str)}
        while True:
            ev = await q.get()
            yield {"event": ev.get("event", "message"), "data": json.dumps(ev, default=str)}
            if ev.get("event") == "stream_end":
                break

    return EventSourceResponse(gen())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
