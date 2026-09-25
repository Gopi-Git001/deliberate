"""End-to-end tool-call trace for panel agents.

Every tool call a panel agent makes is printed to stderr the moment its result comes back —
before that result is handed to the agent's next LLM call. Each structured turn (research or
debate response) is recorded too, so the end-of-run summary can show, per agent, how many tool
calls were made and how many responses were generated without one. Stderr keeps the trace out
of `--json` stdout.

One tracer per panel run (ContextVar; LangGraph copies context into its worker threads), so
concurrent UI runs do not mix their traces.
"""

from __future__ import annotations

import json
import sys
import threading
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TextIO

RULE = "─" * 88


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        return repr(value)


def _indent(text: str, prefix: str = "    │ ") -> str:
    return "\n".join(prefix + line for line in (text or "(empty)").splitlines() or [""])


def is_tool_error(tool: str, result: str) -> bool:
    """Failures that tools return as text: '<tool> error: ...', '<tool> refused: ...', placeholders."""
    head = result.lstrip()[:200]
    return head.startswith((f"{tool} error", f"{tool} refused", "[placeholder]", "Unknown tool", "File not found"))


@dataclass
class AgentStats:
    tool_calls: int = 0
    tool_errors: int = 0
    responses: int = 0
    responses_with_tools: int = 0
    reminders: int = 0
    by_tool: Counter = field(default_factory=Counter)
    # (role, round, attempt, [tools]) for every response that skipped a required tool.
    skipped_required: list[tuple[str, int, int, list[str]]] = field(default_factory=list)
    # (role, round, attempt, reason) for every response generated with zero tool calls.
    no_tool_responses: list[tuple[str, int, int, str]] = field(default_factory=list)


class ToolTracer:
    def __init__(self, label: str = "panel", enabled: bool = True, stream: TextIO | None = None) -> None:
        self.label = label
        self.enabled = enabled
        self.stream = stream
        self.stats: dict[str, AgentStats] = {}
        self.error_messages: Counter = Counter()  # (tool, first line of the error) -> count
        self._lock = threading.Lock()
        self._seq = 0

    def _print(self, text: str) -> None:
        if self.enabled:
            print(text, file=self.stream or sys.stderr, flush=True)

    def _agent(self, agent_id: str) -> AgentStats:
        return self.stats.setdefault(agent_id, AgentStats())

    def tool_call(
        self,
        *,
        agent_id: str,
        role: str,
        round_index: int,
        attempt: int,
        step: int,
        tool: str,
        call_id: str,
        args: Any,
        result: Any,
        started_at: str,
        duration_ms: float,
        error: bool,
        passed_chars: int,
    ) -> None:
        """Record one tool call. Call this before the result reaches the agent's next LLM call.

        Tools report most failures (quota, bad input, missing key) as returned text, not
        exceptions, so those count as errors too.
        """
        raw = str(result)
        error = error or is_tool_error(tool, raw)
        with self._lock:
            self._seq += 1
            seq = self._seq
            stats = self._agent(agent_id)
            stats.tool_calls += 1
            stats.by_tool[tool] += 1
            stats.tool_errors += int(error)
            if error:
                self.error_messages[(tool, (raw.splitlines() or [""])[0][:160])] += 1
            truncated = f" (agent receives first {passed_chars} of {len(raw)} chars)" if passed_chars < len(raw) else ""
            self._print(
                f"[trace #{seq}] {started_at}  {agent_id}  {role} r{round_index} attempt {attempt} step {step}\n"
                f"    tool:     {tool}  (call_id={call_id}){'  ERROR' if error else ''}\n"
                f"    args:\n{_indent(_json(args))}\n"
                f"    result ({len(raw)} chars, {duration_ms:.0f} ms){truncated}:\n{_indent(raw)}\n"
                f"    → returned at {_now()}; handing result to {agent_id} before it forms its response"
            )

    def reminder(
        self, *, agent_id: str, role: str, round_index: int, attempt: int, missing: list[str], reason: str
    ) -> None:
        """The agent was told to call required tools it had not used yet."""
        with self._lock:
            self._agent(agent_id).reminders += 1
            self._print(
                f"[trace] {_now()}  {agent_id}  {role} r{round_index} attempt {attempt}: "
                f"reminded to call {', '.join(missing)} ({reason})"
            )

    def response(
        self,
        *,
        agent_id: str,
        role: str,
        round_index: int,
        attempt: int,
        tool_calls: int,
        max_tool_steps: int,
        skipped_required: list[str] | None = None,
    ) -> None:
        """Record one structured agent response and how many tool calls preceded it."""
        with self._lock:
            stats = self._agent(agent_id)
            stats.responses += 1
            where = f"{agent_id}  {role} r{round_index} attempt {attempt}"
            if skipped_required:
                stats.skipped_required.append((role, round_index, attempt, list(skipped_required)))
                self._print(
                    f"[trace] {_now()}  ⚠ SKIPPED REQUIRED TOOLS  {where}: never called "
                    f"{', '.join(skipped_required)}"
                )
            if tool_calls:
                stats.responses_with_tools += 1
                self._print(f"[trace] {_now()}  {where}: response formed after {tool_calls} tool call(s)")
                return
            reason = (
                "tool steps disabled for this call (max_tool_steps=0)"
                if max_tool_steps <= 0
                else "model chose not to call any tool"
            )
            stats.no_tool_responses.append((role, round_index, attempt, reason))
            self._print(f"[trace] {_now()}  ⚠ NO TOOL CALL  {where}: response generated without a tool call — {reason}")

    def summary(self) -> str:
        with self._lock:
            rows = sorted(self.stats.items())
        lines = [RULE, f"TOOL-CALL TRACE SUMMARY — {self.label}", RULE]
        header = (
            f"{'agent':<16}{'tool calls':>11}{'errors':>8}{'responses':>11}{'w/ tools':>10}{'NO tool':>9}"
            f"{'skipped req':>13}{'reminders':>11}"
        )
        lines.append(header)
        total = AgentStats()
        for agent_id, s in rows:
            no_tool = len(s.no_tool_responses)
            flag = "  ⚠ FLAGGED" if no_tool or s.skipped_required else ""
            lines.append(
                f"{agent_id:<16}{s.tool_calls:>11}{s.tool_errors:>8}{s.responses:>11}"
                f"{s.responses_with_tools:>10}{no_tool:>9}{len(s.skipped_required):>13}{s.reminders:>11}{flag}"
            )
            total.tool_calls += s.tool_calls
            total.tool_errors += s.tool_errors
            total.responses += s.responses
            total.responses_with_tools += s.responses_with_tools
            total.no_tool_responses += s.no_tool_responses
            total.skipped_required += s.skipped_required
            total.reminders += s.reminders
            total.by_tool.update(s.by_tool)
        lines.append(
            f"{'TOTAL':<16}{total.tool_calls:>11}{total.tool_errors:>8}{total.responses:>11}"
            f"{total.responses_with_tools:>10}{len(total.no_tool_responses):>9}"
            f"{len(total.skipped_required):>13}{total.reminders:>11}"
        )
        if total.by_tool:
            lines += ["", "Calls per tool: " + ", ".join(f"{t} {n}" for t, n in total.by_tool.most_common())]
            for agent_id, s in rows:
                lines.append(f"  {agent_id}: " + ", ".join(f"{t} {n}" for t, n in s.by_tool.most_common()))
        flagged = [(a, s) for a, s in rows if s.no_tool_responses]
        if flagged:
            lines += ["", f"⚠ {len(flagged)} agent(s) responded WITHOUT a tool call:"]
            for agent_id, s in flagged:
                for role, rnd, attempt, reason in s.no_tool_responses:
                    lines.append(f"  - {agent_id}: {role} r{rnd} attempt {attempt} — {reason}")
        elif rows:
            lines += ["", "Every agent response was preceded by at least one tool call."]
        else:
            lines += ["", "No panel agent responses were recorded."]
        skipped = [(a, s) for a, s in rows if s.skipped_required]
        if skipped:
            lines += ["", f"⚠ {len(skipped)} agent(s) answered without calling every REQUIRED tool:"]
            for agent_id, s in skipped:
                for role, rnd, attempt, tools in s.skipped_required:
                    lines.append(f"  - {agent_id}: {role} r{rnd} attempt {attempt} — skipped {', '.join(tools)}")
        with self._lock:
            errors = self.error_messages.most_common()
        if errors:
            lines += ["", f"⚠ {total.tool_errors} tool call(s) FAILED — agents got no usable result from them:"]
            lines += [f"  - {n} × {tool}: {message}" for (tool, message), n in errors]
        lines.append(RULE)
        return "\n".join(lines)

    def print_summary(self) -> None:
        self._print(self.summary())


_current: ContextVar[ToolTracer | None] = ContextVar("panel_tool_tracer", default=None)
_fallback = ToolTracer(label="panel (untracked run)")


def current_tracer() -> ToolTracer:
    """The tracer for the active panel run (a process-wide fallback outside one)."""
    return _current.get() or _fallback


@contextmanager
def tracing(label: str, enabled: bool = True) -> Iterator[ToolTracer]:
    """Scope a tracer to one panel run; prints the summary when the run ends (or fails)."""
    tracer = ToolTracer(label=label, enabled=enabled)
    token = _current.set(tracer)
    tracer._print(f"{RULE}\nTOOL-CALL TRACE — {label} — started {_now()}\n{RULE}")
    try:
        yield tracer
    finally:
        _current.reset(token)
        tracer.print_summary()
