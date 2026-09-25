"""Run the panel solo: python -m manager_agent.panel "topic" --question "..." [--sub ...]."""

from __future__ import annotations

import argparse
import json
import sys

from dotenv import load_dotenv

from manager_agent.config import PROJECT_ROOT
from manager_agent.llm import MissingAPIKeyError
from manager_agent.main import _print_event
from manager_agent.panel.config import get_panel_settings
from manager_agent.panel.graph import stream_panel
from manager_agent.schemas import DebateRules, PanelBrief


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(prog="manager_agent.panel")
    parser.add_argument("topic")
    parser.add_argument("--question", help="Debate question (defaults to the topic)")
    parser.add_argument("--sub", action="append", default=[], help="Sub-question (repeatable)")
    parser.add_argument("--rounds", type=int, default=0, help="Max rounds (default PANEL_MAX_ROUNDS)")
    parser.add_argument("--json", action="store_true", help="Print raw events as JSON lines")
    args = parser.parse_args(argv)

    settings = get_panel_settings()
    brief = PanelBrief(
        topic=args.topic,
        goal=args.question or args.topic,
        sub_questions=args.sub or [args.question or args.topic],
        research_angles=[],
        debate_rules=DebateRules(
            max_rounds=args.rounds or settings.panel_max_rounds,
            consensus_criteria=f">= {settings.panel_consensus_threshold:.0%} of agents back one answer",
            early_stop="no new arguments",
        ),
        panel_size=settings.panel_size,
        hop=1,
    )
    try:
        for event in stream_panel(brief):
            if args.json:
                print(json.dumps(event, ensure_ascii=False))
            elif event["type"] == "panel_result":
                r = event["result"]
                print(f"\n=== PANEL RESULT ({r['status']}, stop: {r['stop_reason']}, "
                      f"rounds: {r['rounds_run']}, confidence: {r['confidence']}) ===\n{r['consensus']}")
                if r["dissent"]:
                    print(f"Dissent: {r['dissent']}")
            else:
                _print_event(event)
    except MissingAPIKeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
