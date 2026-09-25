"""Shared helpers for manager tools."""

from __future__ import annotations

from pathlib import Path

from manager_agent.config import get_settings


def resolve_readable_path(path: str) -> Path:
    """Resolve a model-supplied path, confined to DOCUMENT_ROOT.

    Relative paths are taken relative to DOCUMENT_ROOT. Raises ValueError if the
    result escapes the root or names a dotenv file, so the agent cannot read secrets.
    """
    settings = get_settings()
    root = settings.resolve_path(settings.document_root)
    p = Path(path)
    resolved = (p if p.is_absolute() else root / p).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"Path is outside DOCUMENT_ROOT ({root}): {path}")
    if resolved.name.startswith(".env"):
        raise ValueError("Reading .env files is not allowed.")
    return resolved
