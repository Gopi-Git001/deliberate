"""Panel tool registry — identical for every clone. No memory / vector-DB tools by design."""

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

__all__ = ["PANEL_TOOLS"]
