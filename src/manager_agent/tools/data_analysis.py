"""Lightweight data analysis over CSV/JSON files using pandas."""

from __future__ import annotations

from langchain_core.tools import tool

from manager_agent.tools._common import resolve_readable_path


@tool
def data_analysis(path: str, question: str = "") -> str:
    """Profile a CSV/JSON dataset under DOCUMENT_ROOT: shape, dtypes, stats, sample rows.

    Use the profile to answer `question`; use code_interpreter for custom computation.
    """
    try:
        p = resolve_readable_path(path)
    except ValueError as exc:
        return f"data_analysis refused: {exc}"
    if not p.exists():
        return f"File not found: {path}"
    try:
        import pandas as pd

        suffix = p.suffix.lower()
        if suffix == ".csv":
            df = pd.read_csv(p)
        elif suffix == ".json":
            df = pd.read_json(p)
        else:
            return "Unsupported format; use .csv or .json"
        return (
            f"question={question!r}\n"
            f"shape={df.shape}, columns={list(df.columns)}\n"
            f"dtypes:\n{df.dtypes.to_string()}\n"
            f"missing values:\n{df.isna().sum().to_string()}\n"
            f"describe:\n{df.describe(include='all').to_string()[:3000]}\n"
            f"head:\n{df.head(5).to_string()}"
        )
    except Exception as exc:  # noqa: BLE001
        return f"data_analysis error: {exc}"
