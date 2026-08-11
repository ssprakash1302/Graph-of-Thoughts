"""Optional Supabase sink — same GoT events as JSONL, posted to got_events.

Enabled only when SUPABASE_URL + key are set. Inserts are queued on a
background thread so they never stall Generate/Aggregate/Refine.
"""

from __future__ import annotations

import os
import queue
import threading
from typing import Any

import httpx

_DROP = {"prompt", "response", "graph_snapshot"}
_MAX_STR = 400
_SENTINEL = object()


def supabase_enabled() -> bool:
    return bool(os.getenv("SUPABASE_URL") and _api_key())


def _api_key() -> str | None:
    return os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")


def _trim(value: Any) -> Any:
    if isinstance(value, str) and len(value) > _MAX_STR:
        return value[:_MAX_STR] + "…"
    if isinstance(value, dict):
        return {k: _trim(v) for k, v in value.items() if k not in _DROP}
    if isinstance(value, list) and len(value) > 40:
        return value[:40] + ["…"]
    return value


def attach_supabase_sink(logger: Any) -> bool:
    """Fan existing logger events out to Supabase. Returns True if hooked."""
    if not supabase_enabled():
        return False

    url = os.getenv("SUPABASE_URL", "").rstrip("/") + "/rest/v1/got_events"
    key = _api_key()
    headers = {
        "apikey": key or "",
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    q: queue.Queue[Any] = queue.Queue()
    warned = {"done": False}

    def worker() -> None:
        with httpx.Client(timeout=8.0) as client:
            while True:
                item = q.get()
                if item is _SENTINEL:
                    q.task_done()
                    break
                try:
                    resp = client.post(url, headers=headers, json=item)
                    if resp.status_code >= 400 and not warned["done"]:
                        warned["done"] = True
                        print(f"[supabase] insert failed ({resp.status_code}): {resp.text[:200]}")
                except Exception as exc:  # noqa: BLE001
                    if not warned["done"]:
                        warned["done"] = True
                        print(f"[supabase] sink offline: {exc}")
                finally:
                    q.task_done()

    threading.Thread(target=worker, name="got-supabase-sink", daemon=True).start()

    def sink(event: dict[str, Any]) -> None:
        row = {
            "run_id": event.get("run_id"),
            "event": event.get("event"),
            "elapsed_s": event.get("elapsed_s"),
            "ts": event.get("ts"),
            "message": event.get("message") or event.get("summary"),
            "payload": _trim(
                {
                    k: v
                    for k, v in event.items()
                    if k
                    not in {"run_id", "event", "elapsed_s", "ts", "message", "summary"}
                }
            ),
        }
        try:
            q.put_nowait(row)
        except Exception:
            pass

    prev = logger.event_callback

    def chained(event: dict[str, Any]) -> None:
        if prev is not None:
            prev(event)
        sink(event)

    logger.event_callback = chained
    if getattr(logger, "info", None):
        logger.info("Supabase event sink attached (async)")
    return True
