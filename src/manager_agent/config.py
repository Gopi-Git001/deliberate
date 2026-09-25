"""Environment-backed settings. Never hardcode API keys."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# manager-agent/ (the directory holding .env, src/, data/)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Real environment variables always win over .env values.
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    tavily_api_key: str = ""
    semantic_scholar_api_key: str = ""  # optional; raises S2 rate limits

    browser_api_key: str = ""
    e2b_api_key: str = ""

    chroma_persist_dir: str = "./data/chroma"
    openai_embedding_model: str = "text-embedding-3-small"

    # document_reader / data_analysis may only read files under this directory.
    document_root: str = "./data"
    # Comma-separated env var names api_connector may use for auth.
    api_connector_allowed_env_vars: str = ""

    # Guards
    manager_max_tool_steps: int = 8
    max_debate_rounds: int = 3
    max_panel_hops: int = 2
    panel_size: int = 10
    panel_summary_max_chars: int = 1200

    # Web UI
    ui_host: str = "127.0.0.1"
    ui_port: int = 8000
    ui_max_active_runs: int = 2
    ui_demo_delay: float = 1.0  # demo-mode thinking-time multiplier

    def resolve_path(self, value: str) -> Path:
        """Resolve a configured path relative to the project root."""
        p = Path(value)
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()

    def allowed_env_vars(self) -> set[str]:
        return {
            name.strip()
            for name in self.api_connector_allowed_env_vars.split(",")
            if name.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
