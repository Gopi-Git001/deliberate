"""Read local or uploaded documents (PDF/text), confined to DOCUMENT_ROOT."""

from __future__ import annotations

from langchain_core.tools import tool

from manager_agent.tools._common import resolve_readable_path


@tool
def document_reader(path: str, max_chars: int = 8000) -> str:
    """Read text from a document under DOCUMENT_ROOT (txt/md/csv/json/pdf).

    Relative paths are resolved against DOCUMENT_ROOT (default ./data).
    """
    try:
        p = resolve_readable_path(path)
    except ValueError as exc:
        return f"document_reader refused: {exc}"
    if not p.exists():
        return f"File not found: {path}"
    suffix = p.suffix.lower()
    try:
        if suffix in {".txt", ".md", ".csv", ".json"}:
            return p.read_text(encoding="utf-8", errors="replace")[:max_chars]
        if suffix == ".pdf":
            from pypdf import PdfReader

            parts: list[str] = []
            for page in PdfReader(str(p)).pages:
                parts.append(page.extract_text() or "")
                if sum(len(x) for x in parts) >= max_chars:
                    break
            return "\n".join(parts)[:max_chars]
        return f"Unsupported file type: {suffix}"
    except Exception as exc:  # noqa: BLE001
        return f"document_reader error: {exc}"
