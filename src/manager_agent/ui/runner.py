"""Run registry: executes the LangGraph manager (+ panel) in a worker thread per run and
fans its UI events out to SSE subscribers. History is kept so clients can reconnect
(Last-Event-ID) and replay."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from manager_agent.config import get_settings
from manager_agent.llm import MissingAPIKeyError
from manager_agent.main import stream_manager
from manager_agent.runtime import RunCancelled
from manager_agent.ui.events import (
    MANAGER_ID,
    Error,
    RunFinished,
    RunStarted,
    Status,
    Translator,
    now_iso,
    panel_ids,
)

log = logging.getLogger("manager_agent.ui")

# (topic, constraints, configurable) -> iterator of stream_manager-style events
GraphStream = Callable[[str, str, dict[str, Any]], Iterator[dict[str, Any]]]


def default_graph_stream(topic: str, constraints: str, configurable: dict[str, Any]) -> Iterator[dict[str, Any]]:
    return stream_manager(topic, constraints, configurable=configurable)


class TooManyRuns(Exception):
    pass


@dataclass
class Run:
    id: str
    topic: str
    constraints: str
    demo: bool
    loop: asyncio.AbstractEventLoop
    cancel_event: threading.Event = field(default_factory=threading.Event)
    events: list[dict[str, Any]] = field(default_factory=list)
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    finished: bool = False
    reason: str = ""

    # Called on the event-loop thread only.
    def _publish(self, event: dict[str, Any]) -> None:
        event["seq"] = len(self.events) + 1
        self.events.append(event)
        if event["type"] == "run_finished":
            self.finished = True
            self.reason = event["reason"]
        for q in list(self.subscribers):
            q.put_nowait(event)

    # Called from the worker thread.
    def emit(self, model: BaseModel) -> None:
        event = {**model.model_dump(), "run_id": self.id, "ts": now_iso()}
        self.loop.call_soon_threadsafe(self._publish, event)


class RunRegistry:
    def __init__(self, graph_stream: GraphStream = default_graph_stream, keep: int = 20) -> None:
        self.graph_stream = graph_stream
        self.keep = keep
        self.runs: OrderedDict[str, Run] = OrderedDict()

    def active_count(self) -> int:
        return sum(1 for r in self.runs.values() if not r.finished)

    def get(self, run_id: str) -> Run | None:
        return self.runs.get(run_id)

    def start(self, topic: str, constraints: str = "", demo: bool = False) -> Run:
        settings = get_settings()
        if self.active_count() >= settings.ui_max_active_runs:
            raise TooManyRuns(f"At most {settings.ui_max_active_runs} runs at a time.")
        run = Run(
            id=uuid.uuid4().hex[:12], topic=topic, constraints=constraints, demo=demo,
            loop=asyncio.get_running_loop(),
        )
        self.runs[run.id] = run
        while len(self.runs) > self.keep:  # drop the oldest finished runs
            oldest = next((k for k, r in self.runs.items() if r.finished), None)
            if oldest is None:
                break
            del self.runs[oldest]
        threading.Thread(target=self._work, args=(run,), name=f"run-{run.id}", daemon=True).start()
        return run

    def stop(self, run_id: str) -> bool:
        run = self.runs.get(run_id)
        if not run or run.finished:
            return False
        run.cancel_event.set()
        return True

    def _work(self, run: Run) -> None:
        settings = get_settings()
        translator = Translator(settings.panel_size)
        run.emit(RunStarted(topic=run.topic, constraints=run.constraints, demo=run.demo,
                            agents=[MANAGER_ID, *panel_ids(settings.panel_size)]))
        configurable: dict[str, Any] = {"cancel_event": run.cancel_event}
        if run.demo:
            configurable.update(demo=True, demo_delay=settings.ui_demo_delay)
        reason = "completed"
        try:
            for event in self.graph_stream(run.topic, run.constraints, configurable):
                if run.cancel_event.is_set():
                    raise RunCancelled("Run cancelled by user.")
                for ui_event in translator.translate(event):
                    run.emit(ui_event)
        except RunCancelled:
            reason = "cancelled"
        except MissingAPIKeyError as exc:
            reason = "error"
            run.emit(Error(message=str(exc)))
        except Exception as exc:  # noqa: BLE001 — report any graph failure to the browser
            log.exception("run %s failed", run.id)
            reason = "error"
            run.emit(Error(message=f"{type(exc).__name__}: {exc}"))
        if reason != "completed":
            status = "error" if reason == "error" else "idle"
            for agent_id in [MANAGER_ID, *translator.agents]:
                run.emit(Status(agent_id=agent_id, status=status))
        run.emit(RunFinished(reason=reason))

    async def subscribe(self, run: Run, after: int = 0) -> AsyncIterator[dict[str, Any]]:
        """Replay events after `after`, then stream live until run_finished."""
        queue: asyncio.Queue = asyncio.Queue()
        backlog = [e for e in run.events if e["seq"] > after]
        run.subscribers.add(queue)
        try:
            for event in backlog:
                yield event
                if event["type"] == "run_finished":
                    return
            while True:
                event = await queue.get()
                if event["seq"] <= after or (backlog and event["seq"] <= backlog[-1]["seq"]):
                    continue
                yield event
                if event["type"] == "run_finished":
                    return
        finally:
            run.subscribers.discard(queue)
