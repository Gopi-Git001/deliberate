"""Manager tool registry — placeholders ready to wire to real backends."""

from manager_agent.tools.academic_search import academic_search
from manager_agent.tools.api_connector import api_connector
from manager_agent.tools.browser import browser_navigate
from manager_agent.tools.code_interpreter import code_interpreter
from manager_agent.tools.data_analysis import data_analysis
from manager_agent.tools.document_reader import document_reader
from manager_agent.tools.fact_checker import fact_checker
from manager_agent.tools.memory import memory_query, memory_store
from manager_agent.tools.planner import planner
from manager_agent.tools.summarizer import summarizer
from manager_agent.tools.web_search import web_search

MANAGER_TOOLS = [
    web_search,
    browser_navigate,
    code_interpreter,
    document_reader,
    memory_store,
    memory_query,
    academic_search,
    data_analysis,
    api_connector,
    summarizer,
    fact_checker,
    planner,
]

__all__ = ["MANAGER_TOOLS"]
