"""Clone factory: N identical panel agents. Only the id differs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from manager_agent.panel import llm as panel_llm
from manager_agent.panel.schemas import AgentTurn
from manager_agent.panel.tools import PANEL_TOOLS
from manager_agent.runtime import check_cancelled

TOOL_OUTPUT_MAX_CHARS = 4000

CLONE_PROMPT = """You are Panel Worker {agent_id} ({number}/{size}) in a multi-agent debate.
Answer the manager's sub-question on the shared topic.
Use tools to gather evidence. Cite sources. Challenge weak claims.
You share the same role as your siblings; your edge is better evidence and clearer reasoning.
Keep short-term notes only for this debate. Do not invent secrets or API keys.
When asked to shift perspective, argue the opposite side in good faith using evidence.

Rules:
- Every substantive claim needs a citation (title + url, or a local document). Uncited claims get challenged and scored low-confidence.
- Cite only sources you actually saw in tool results. Never invent URLs.
- If a tool returns [placeholder] or an error, do not retry it.
- Stay on the debate question. A MANAGER INTERVENTION overrides the previous agenda."""


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
        return CLONE_PROMPT.format(agent_id=self.agent_id, number=self.number, size=self.size)

    def take_turn(
        self,
        task: str,
        max_tool_steps: int,
        config: RunnableConfig,
        schema: type[BaseModel] = AgentTurn,
    ) -> Any:
        """Short ReAct loop (capped), then a structured turn (AgentTurn or DebateTurn)."""
        llm = panel_llm.get_panel_llm()
        tools_by_name = {t.name: t for t in self.tools}
        with_tools = llm.bind_tools(list(self.tools))
        messages: list = [SystemMessage(content=self.system_prompt), HumanMessage(content=task)]

        for _ in range(max_tool_steps):
            check_cancelled()
            response = with_tools.invoke(messages, config=config)
            messages.append(response)
            if not response.tool_calls:
                break
            for call in response.tool_calls:
                tool = tools_by_name.get(call["name"])
                try:
                    out = tool.invoke(call["args"]) if tool else f"Unknown tool {call['name']!r}"
                except Exception as exc:  # noqa: BLE001 — errors go back to the agent
                    out = f"{call['name']} error: {exc}"
                messages.append(
                    ToolMessage(
                        content=str(out)[:TOOL_OUTPUT_MAX_CHARS],
                        tool_call_id=call["id"],
                        name=call["name"],
                    )
                )

        check_cancelled()
        messages.append(HumanMessage(content="Now state your position for this round."))
        structured = llm.with_structured_output(schema, method="function_calling")
        return structured.invoke(messages, config=config)


def make_panel(size: int) -> list[PanelAgent]:
    """Build `size` identical clones: panel_agent_00 … panel_agent_{size-1}."""
    tools = tuple(PANEL_TOOLS)
    return [
        PanelAgent(agent_id=agent_id_for(i), number=i + 1, size=size, tools=tools)
        for i in range(size)
    ]
