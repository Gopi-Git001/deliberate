"""Per-run options carried in the LangGraph config (`configurable`).

Values propagate into every node, the panel subgraph and its parallel Send workers,
so a run can be cancelled or put in demo mode without global state.

    configurable = {"cancel_event": threading.Event(), "demo": True, "demo_delay": 1.0}
"""

from __future__ import annotations

from typing import Any

from langgraph.config import get_config


class RunCancelled(Exception):
    """Raised inside the graph when the run's cancel_event is set."""


def run_option(key: str, default: Any = None) -> Any:
    try:
        return (get_config().get("configurable") or {}).get(key, default)
    except RuntimeError:  # called outside a graph run
        return default


def check_cancelled() -> None:
    event = run_option("cancel_event")
    if event is not None and event.is_set():
        raise RunCancelled("Run cancelled by user.")


def demo_enabled() -> bool:
    return bool(run_option("demo", False))
