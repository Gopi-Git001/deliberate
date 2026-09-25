"""CLI entrypoint and programmatic API for the manager agent."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from typing import Any

from dotenv import load_dotenv

from manager_agent.config import PROJECT_ROOT, get_settings
from manager_agent.graph import build_manager_graph
from manager_agent.llm import MissingAPIKeyError
from manager_agent.panel import PanelRunner, run_panel, run_panel_stub
from manager_agent.schemas import FinalAnswer


def _prepare(
    topic: str,
    constraints: str,
    panel_runner: PanelRunner | None,
    configurable: dict[str, Any] | None = None,
):
    settings = get_settings()
    app = build_manager_graph(panel_runner or run_panel)
    # Each tool step is agent + tools (2 supersteps); leave headroom for panel hops.
    limit = 2 * settings.manager_max_tool_steps + 4 * settings.max_panel_hops + 20
    config: dict[str, Any] = {"recursion_limit": limit}
    if configurable:
        config["configurable"] = configurable  # per-run options: cancel_event, demo
    return app, {"topic": topic, "constraints": constraints}, config


def run_manager(
    topic: str, constraints: str = "", panel_runner: PanelRunner | None = None
) -> FinalAnswer:
    """Run the manager on a topic and return the structured final answer."""
    app, inputs, config = _prepare(topic, constraints, panel_runner)
    state = app.invoke(inputs, config=config)
    return FinalAnswer.model_validate(state["result"])


def stream_manager(
    topic: str,
    constraints: str = "",
    panel_runner: PanelRunner | None = None,
    configurable: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    """Run the manager, yielding events: manager steps, panel debate events, final answer.

    Panel state updates are dropped — only the panel's own debate events surface.
    """
    app, inputs, config = _prepare(topic, constraints, panel_runner, configurable)
    for namespace, mode, chunk in app.stream(
        inputs, config=config, stream_mode=["updates", "custom"], subgraphs=True
    ):
        if mode == "custom":
            yield {"source": "panel" if namespace else "manager", **chunk}
            continue
        if namespace:  # raw panel node updates never leave the panel
            continue
        for node, update in chunk.items():
            update = update or {}
            event: dict[str, Any] = {"source": "manager", "type": "manager_step", "node": node}
            if "phase" in update:
                event["phase"] = update["phase"]
            if node == "plan" and update.get("plan"):
                event["plan"] = update["plan"]
            if node == "agent":
                calls = getattr(update["messages"][-1], "tool_calls", None) or []
                event["tool_calls"] = [c["name"] for c in calls]
            if node == "review":
                event["decision"] = update.get("review_decision")
                event["verification"] = update.get("verification")
                event["directive"] = update.get("directive", "")
            yield event
            if node == "synthesize":
                yield {"source": "manager", "type": "final_answer", "result": update["result"]}


def _print_human(result: FinalAnswer) -> None:
    print("\n=== FINAL ANSWER ===\n")
    print(result.answer)
    print("\nKey points:")
    for p in result.key_points:
        print(f"  - {p}")
    if result.sources:
        print("\nSources:")
        for s in result.sources:
            print(f"  - {s.title}" + (f" — {s.url}" if s.url else ""))
    print(f"\nConfidence: {result.confidence} — {result.confidence_notes}")
    if result.open_questions:
        print("\nOpen questions:")
        for q in result.open_questions:
            print(f"  - {q}")
    p = result.panel
    print(
        f"\nPanel: {p.status}, hops={p.hops}, rounds={p.rounds}, stop={p.stop_reason or '-'}, "
        f"confidence={p.confidence if p.confidence is not None else '-'}, "
        f"interventions={len(p.interventions)}"
    )
    print(f"Review: {result.verification}")
    print(f"Tool calls: {result.tool_calls}")


def _print_event(event: dict[str, Any]) -> None:
    kind = event.get("type")
    if kind == "manager_step":
        extra = ""
        if event.get("tool_calls"):
            extra = f" → tools: {', '.join(event['tool_calls'])}"
        if event.get("decision"):
            extra = f" → {event['decision']}: {event.get('verification', '')}"
        print(f"[manager] {event['node']}{extra}")
    elif kind == "panel_start":
        print(f"[panel] hop {event['hop']} start — {len(event['agents'])} agents, max {event['max_rounds']} rounds")
    elif kind == "agent_turn":
        flag = " (devil's advocate)" if event["shifted"] else ""
        print(f"  [{event['agent_id']} r{event['round']}{flag}] {event['stance']} (conf {event['confidence']})")
    elif kind == "perspective_shift":
        print(f"[panel] round {event['round']} perspective shift → {', '.join(event['agents'])}")
    elif kind == "round_summary":
        print(f"[panel] {event['summary']}")
    elif kind == "stop":
        print(f"[panel] stop: {event['stop_reason']} after round {event['round']}")
    elif kind == "consensus":
        print(f"[panel] {event['status']} (conf {event['confidence']}): {event['consensus']}")


def main(argv: list[str] | None = None) -> int:
    # Loads .env into os.environ too, so api_connector can read allowlisted vars.
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(prog="manager-agent")
    parser.add_argument("topic", nargs="+", help="Topic for the manager to research")
    parser.add_argument("--constraints", default="", help="Depth, audience, deadline...")
    parser.add_argument("--json", action="store_true", help="Print the full structured result")
    parser.add_argument("--stream", action="store_true", help="Print manager + debate events live")
    parser.add_argument("--stub-panel", action="store_true", help="Use the no-LLM panel stub")
    args = parser.parse_args(argv)
    topic = " ".join(args.topic).strip()
    runner = run_panel_stub if args.stub_panel else run_panel

    try:
        if args.stream:
            result = None
            for event in stream_manager(topic, args.constraints, runner):
                if event["type"] == "final_answer":
                    result = FinalAnswer.model_validate(event["result"])
                else:
                    _print_event(event)
        else:
            result = run_manager(topic, args.constraints, runner)
    except MissingAPIKeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    else:
        _print_human(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
