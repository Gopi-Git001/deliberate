"""Panel tool registry — identical for every clone. No memory / vector-DB tools by design."""

from langchain_core.tools import BaseTool

from manager_agent.config import get_settings
from manager_agent.panel.tools.citation import citation
from manager_agent.panel.tools.code_runner import code_runner
from manager_agent.panel.tools.confidence_scorer import confidence_scorer
from manager_agent.panel.tools.perspective_shifter import perspective_shifter
from manager_agent.panel.tools.source_ranker import source_ranker
from manager_agent.panel.tools.summarizer import summarizer

# Shared with the manager (same implementation, same DOCUMENT_ROOT sandbox).
from manager_agent.tools.document_reader import document_reader
from manager_agent.tools.web_search import web_search

PANEL_TOOLS = [
    web_search,
    citation,
    document_reader,
    code_runner,
    source_ranker,
    summarizer,
    confidence_scorer,
    perspective_shifter,
]

DOCUMENT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".pdf"}


def local_documents(limit: int = 50) -> list[str]:
    """Readable files under DOCUMENT_ROOT, relative paths (what document_reader accepts)."""
    settings = get_settings()
    root = settings.resolve_path(settings.document_root)
    if not root.is_dir():
        return []
    files = sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in DOCUMENT_SUFFIXES and not p.name.startswith(".")
    )
    return files[:limit]


def available_panel_tools() -> list[BaseTool]:
    """PANEL_TOOLS minus tools that can only return placeholders here, so agents are never
    offered a tool that cannot work: code_runner needs E2B_API_KEY, document_reader needs files."""
    skip = set()
    if not get_settings().e2b_api_key:
        skip.add("code_runner")
    if not local_documents():
        skip.add("document_reader")
    return [t for t in PANEL_TOOLS if t.name not in skip]


__all__ = ["PANEL_TOOLS", "available_panel_tools", "local_documents"]
