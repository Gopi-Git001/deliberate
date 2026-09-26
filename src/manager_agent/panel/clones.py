"""Clone factory: N identical panel agents. Only the id differs."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from manager_agent.panel import llm as panel_llm
from manager_agent.panel.schemas import AgentTurn
from manager_agent.panel.tools import available_panel_tools, local_documents
from manager_agent.panel.trace import current_tracer
from manager_agent.runtime import check_cancelled

TOOL_OUTPUT_MAX_CHARS = 4000

CLONE_PROMPT = """You are Panel Worker {agent_id} ({number}/{size}) in a multi-agent debate.
Answer the manager's sub-question on the shared topic.
Use tools to gather AND vet evidence. Cite sources. Challenge weak claims.
You share the same role as your siblings; your edge is better evidence and clearer reasoning.
Keep short-term notes only for this debate. Do not invent secrets or API keys.
When asked to shift perspective, argue the opposite side in good faith using evidence.

YOUR TOOLS — each has a job; use them, do not just search:
{tool_guide}
You may call several tools in one step, but a tool that needs another tool's output (e.g.
source_ranker on search results) must come in a later step.

Rules:
- Every substantive claim needs a citation (title + url, or a local document). Uncited claims get challenged and scored low-confidence.
- Cite only sources you actually saw in tool results. Never invent URLs.
- If a tool returns [placeholder] or an error, do not retry it.
- Stay on the debate question. A MANAGER INTERVENTION overrides the previous agenda."""

TOOL_GUIDE = {
    "web_search": "find evidence: studies, data, official reports, recent news.",
    "document_reader": "read a local document (path relative to DOCUMENT_ROOT). Available: {documents}.",
    "source_ranker": "rank sources by credibility + relevance. Pass the raw web_search output "
    "(or a JSON list of {{title, url, snippet}}) as `sources`; lean on the top-scored ones.",
    "citation": "normalize each source you will cite (title, url, short quote) into a clean reference.",
    "summarizer": "compress long search results, documents or a peer's argument before you use them.",
    "confidence_scorer": "calibrate your confidence from your self-rating, citation count, average "
    "source_ranker score and share of peers who agree. Use its score as your self_confidence.",
    "perspective_shifter": "steelman the strongest position opposing yours (or a peer's) before you "
    "decide to hold, revise or abandon.",
    "code_runner": "run a short Python snippet to check numbers or do light analysis.",
}

FINAL_STEP_REMINDER = (
    "This is your LAST tool step. You have not yet called: {missing}. Call them now "
    "(in parallel, in this one step) instead of searching more."
)
REQUIRED_REMINDER = "Before you answer, you must still call: {missing}. Call them now; do not answer yet."


def tool_guide(tools: tuple[BaseTool, ...]) -> str:
    docs = ", ".join(local_documents()) or "none"
    return "\n".join(
        f"- {t.name}: " + TOOL_GUIDE.get(t.name, t.description).format(documents=docs) for t in tools
    )


def agent_id_for(index: int) -> str:
    return f"panel_agent_{index:02d}"


@dataclass(frozen=True)
class PanelAgent:
    """One clone. Every clone shares the same prompt template, tools and model."""

    agent_id: str
    number: int
    size: int
    tools: tuple[BaseTool, ...]

    @property
    def system_prompt(self) -> str:
        return CLONE_PROMPT.format(
            agent_id=self.agent_id, number=self.number, size=self.size, tool_guide=tool_guide(self.tools)
        )

    def take_turn(
        self,
        task: str,
        max_tool_steps: int,
        config: RunnableConfig,
        schema: type[BaseModel] = AgentTurn,
        attempt: int = 1,
        required_tools: tuple[str, ...] = (),
        usage: list[dict] | None = None,
    ) -> Any:
        """Short ReAct loop (capped), then a structured turn (AgentTurn or DebateTurn).

        `required_tools` (those this agent actually has) must be called before answering: the agent
        is reminded on its last tool step, or once if it stops early without them.
        Every tool call is traced (args + raw result) before its result reaches the next LLM call,
        and appended to `usage` as {tool, args, result, error} for the caller.
        """
        llm = panel_llm.get_panel_llm()
        tools_by_name = {t.name: t for t in self.tools}
        with_tools = llm.bind_tools(list(self.tools))
        messages: list = [SystemMessage(content=self.system_prompt), HumanMessage(content=task)]
        tracer = current_tracer()
        meta = config.get("metadata") or {}
        where = {
            "agent_id": self.agent_id,
            "role": meta.get("agent.role", "turn"),
            "round_index": meta.get("round.index", 0),
            "attempt": attempt,
        }
        required = [t for t in required_tools if t in tools_by_name]
        used: set[str] = set()
        tool_calls, reminded = 0, False

        def missing() -> list[str]:
            return [t for t in required if t not in used]

        for step in range(max_tool_steps):
            check_cancelled()
            last_step = step == max_tool_steps - 1
            if last_step and missing() and not reminded:
                reminded = True
                messages.append(HumanMessage(content=FINAL_STEP_REMINDER.format(missing=", ".join(missing()))))
                tracer.reminder(**where, missing=missing(), reason="last tool step")
            response = with_tools.invoke(messages, config=config)
            messages.append(response)
            if not response.tool_calls:
                if missing() and not reminded and not last_step:
                    reminded = True
                    messages.append(HumanMessage(content=REQUIRED_REMINDER.format(missing=", ".join(missing()))))
                    tracer.reminder(**where, missing=missing(), reason="stopped before calling them")
                    continue
                break
            for call in response.tool_calls:
                tool = tools_by_name.get(call["name"])
                started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
                t0 = time.perf_counter()
                error = tool is None
                try:
                    out = tool.invoke(call["args"]) if tool else f"Unknown tool {call['name']!r}"
                except Exception as exc:  # noqa: BLE001 — errors go back to the agent
                    out, error = f"{call['name']} error: {exc}", True
                content = str(out)[:TOOL_OUTPUT_MAX_CHARS]
                tool_calls += 1
                used.add(call["name"])
                tracer.tool_call(
                    **where,
                    step=step + 1,
                    tool=call["name"],
                    call_id=call.get("id") or "",
                    args=call["args"],
                    result=out,
                    started_at=started_at,
                    duration_ms=(time.perf_counter() - t0) * 1000,
                    error=error,
                    passed_chars=len(content),
                )
                if usage is not None:
                    usage.append({"tool": call["name"], "args": call["args"], "result": str(out), "error": error})
                messages.append(ToolMessage(content=content, tool_call_id=call["id"], name=call["name"]))

        check_cancelled()
        messages.append(HumanMessage(content="Now state your position for this round."))
        structured = llm.with_structured_output(schema, method="function_calling")
        turn = structured.invoke(messages, config=config)
        tracer.response(**where, tool_calls=tool_calls, max_tool_steps=max_tool_steps, skipped_required=missing())
        return turn


def make_panel(size: int) -> list[PanelAgent]:
    """Build `size` identical clones: panel_agent_00 … panel_agent_{size-1}.

    Tools that cannot work in this environment (no E2B key, no local documents) are left out.
    """
    tools = tuple(available_panel_tools())
    return [
        PanelAgent(agent_id=agent_id_for(i), number=i + 1, size=size, tools=tools)
        for i in range(size)
    ]
