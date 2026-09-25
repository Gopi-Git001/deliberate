"""Panel settings: GPT brain + debate controls. Keys come only from env / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from manager_agent.config import PROJECT_ROOT


class PanelSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    panel_model: str = ""  # empty → falls back to OPENAI_MODEL

    panel_size: int = 10
    panel_max_rounds: int = 5
    panel_no_new_args_threshold: float = 0.15
    panel_perspective_shift_round: int = 2
    # Agents forced to argue against the majority (comma-separated ids or "Panel 03" labels).
    panel_shift_agent_ids: str = "panel_agent_03,panel_agent_05"
    panel_consensus_threshold: float = 0.8  # share of agents that must back one answer (8/10)
    # Debate-turn validators: max argument overlap with own research note / prior turn,
    # and how many regenerations a rejected turn gets before it is accepted as degraded.
    panel_restatement_threshold: float = 0.6
    panel_turn_retries: int = 1
    # Tool steps per turn. Several tools can run in one step; a tool that needs another's output
    # (source_ranker on search results) needs a later step, so budgets below 3 starve the vetting tools.
    panel_research_tool_steps: int = 5
    panel_debate_tool_steps: int = 3
    panel_retry_tool_steps: int = 1  # rewrite of a rejected debate turn
    panel_max_concurrency: int = 5  # parallel agent LLM calls
    panel_summary_max_chars: int = 1200
    # Print every panel tool call (args + raw result) to stderr live, plus a per-agent summary.
    panel_tool_trace: bool = True

    @property
    def model(self) -> str:
        return self.panel_model or self.openai_model


@lru_cache
def get_panel_settings() -> PanelSettings:
    return PanelSettings()
