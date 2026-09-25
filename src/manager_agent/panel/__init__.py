"""Panel package: the 10-agent debate subgraph and the manager-facing runner contract."""

from collections.abc import Callable

from manager_agent.panel.graph import build_panel_graph, run_panel, stream_panel
from manager_agent.panel.stub import run_panel_stub
from manager_agent.schemas import PanelBrief, PanelResult

PanelRunner = Callable[[PanelBrief], PanelResult]

__all__ = ["PanelRunner", "build_panel_graph", "run_panel", "run_panel_stub", "stream_panel"]
