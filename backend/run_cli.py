#!/usr/bin/env python3
"""CLI entry point — run any registered GoT task without the frontend.

Examples:
  python run_cli.py --task sorting --numbers 48 --chunk-size 8
  python run_cli.py --task keyword_counting --chunk-size 2
  python run_cli.py --task set_intersection --chunk-size 8
  python run_cli.py --task document_merging --chunk-size 1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_ROOT))

load_dotenv(BACKEND_ROOT / ".env")

from engine.graph_of_operations import GraphOfOperations  # noqa: E402
from engine.llm_client import LLMClient  # noqa: E402
from engine.logger import GoTLogger  # noqa: E402
from tasks.registry import (  # noqa: E402
    create_task,
    default_chunk_size,
    demo_input_for,
    list_tasks,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run Graph of Thoughts on a registered task")
    p.add_argument(
        "--task",
        type=str,
        default="sorting",
        choices=[t["id"] for t in list_tasks()],
        help="Task plugin id",
    )
    p.add_argument(
        "--numbers",
        type=int,
        default=int(os.getenv("GOT_DEFAULT_NUMBERS", "48")),
        help="Sorting: length of random 0-9 list",
    )
    p.add_argument(
        "--chunk-size",
        type=int,
        default=None,
        help="Chunk size (task-specific default if omitted)",
    )
    p.add_argument(
        "--list",
        type=str,
        default=None,
        help="Sorting: explicit comma-separated list",
    )
    p.add_argument(
        "--input-json",
        type=str,
        default=None,
        help="Path to JSON file with task input (overrides demo input)",
    )
    p.add_argument("--seed", type=int, default=42, help="RNG seed for demo inputs")
    p.add_argument("--generate-k", type=int, default=None)
    p.add_argument("--aggregate-k", type=int, default=None)
    p.add_argument("--log-dir", type=str, default=str(BACKEND_ROOT / "logs"))
    p.add_argument("--run-id", type=str, default=None)
    p.add_argument("--list-tasks", action="store_true", help="Print available tasks and exit")
    return p.parse_args()


def resolve_input(args: argparse.Namespace) -> Any:
    if args.input_json:
        return json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    if args.task == "sorting":
        if args.list:
            return [int(x.strip()) for x in args.list.split(",") if x.strip()]
        return demo_input_for("sorting", n=args.numbers, seed=args.seed)
    return demo_input_for(args.task, seed=args.seed)


def main() -> int:
    args = parse_args()
    if args.list_tasks:
        print(json.dumps(list_tasks(), indent=2))
        return 0

    run_id = args.run_id or f"cli-{uuid.uuid4().hex[:8]}"
    chunk_size = args.chunk_size if args.chunk_size is not None else default_chunk_size(args.task)
    raw_input = resolve_input(args)

    print("=" * 72, file=sys.stderr)
    print(f"Graph of Thoughts — task={args.task}", file=sys.stderr)
    print(f"run_id={run_id}  chunk_size={chunk_size}", file=sys.stderr)
    print("=" * 72, file=sys.stderr)

    logger = GoTLogger(run_id=run_id, log_dir=args.log_dir, also_console=True)
    llm = LLMClient(logger=logger)
    task = create_task(args.task, raw_input)
    goo = GraphOfOperations(
        task=task,
        llm=llm,
        logger=logger,
        generate_k=args.generate_k,
        aggregate_k=args.aggregate_k,
    )
    result = goo.run(raw_input=raw_input, chunk_size=chunk_size)

    snapshot_path = Path(args.log_dir) / f"{run_id}.graph.json"
    snapshot_path.write_text(json.dumps(goo.snapshot(), indent=2, default=str), encoding="utf-8")
    (Path(args.log_dir) / f"{run_id}.result.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )

    merges = [e for e in logger.events if e["event"] == "merge"]
    refines = [
        e
        for e in logger.events
        if e["event"] == "refine" and e.get("path") in {"llm_fixed", "fallback_fixed"}
    ]
    prunes = [
        e
        for e in logger.events
        if e["event"] == "prune" and e.get("nodes_before", 0) > e.get("nodes_after_active", 0)
    ]

    print("\n" + "=" * 72, file=sys.stderr)
    print("RESULT", file=sys.stderr)
    print(f"  task:    {result.get('task')}", file=sys.stderr)
    print(f"  final:   {result.get('final_content')}", file=sys.stderr)
    print(f"  truth:   {result.get('ground_truth')}", file=sys.stderr)
    print(f"  correct: {result.get('correct')}  score={result.get('final_score')}", file=sys.stderr)
    print(f"  log:     {result.get('log_path')}", file=sys.stderr)
    print(f"  graph:   {snapshot_path}", file=sys.stderr)
    print("FIDELITY CHECKS", file=sys.stderr)
    print(f"  multi-parent Aggregate merges: {len(merges)}", file=sys.stderr)
    print(f"  refine corrections:            {len(refines)}", file=sys.stderr)
    print(f"  KeepBest active-count drops:   {len(prunes)}", file=sys.stderr)
    print("=" * 72, file=sys.stderr)

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
