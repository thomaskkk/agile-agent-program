"""CLI entrypoint: uv run python -m program_layer.main --sdd path/to/sdd.md"""
from __future__ import annotations

import argparse
import sys
import uuid

from langchain_core.runnables.config import RunnableConfig
from program_layer.graph import build_graph


def cli() -> None:
    parser = argparse.ArgumentParser(description="Run a Program Layer delivery cycle.")
    parser.add_argument("--sdd", required=True, help="Path to the Solution Design Document (.md)")
    args = parser.parse_args()

    try:
        sdd_text = open(args.sdd).read()
    except FileNotFoundError:
        print(f"Error: SDD file not found: {args.sdd}", file=sys.stderr)
        sys.exit(1)

    graph = build_graph()
    thread_id = str(uuid.uuid4())
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

    print(f"Starting delivery run (thread_id={thread_id})...")
    final_state = None
    for event in graph.stream({"sdd_raw": sdd_text}, config=config, stream_mode="values"):
        final_state = event
        node_status = event.get("status", "")
        if node_status:
            print(f"  status -> {node_status}")

    if final_state:
        print(f"\nDelivery run complete. Final status: {final_state.get('status', 'unknown')}")
    else:
        print("\nDelivery run produced no state.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    cli()
