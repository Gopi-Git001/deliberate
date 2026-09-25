import { X } from "lucide-react";
import { MANAGER_ID } from "../lib/colors";
import type { AgentInfo } from "../lib/runReducer";
import type { Health } from "../lib/types";
import { AgentStatusItem } from "./AgentStatusItem";

interface Props {
  order: string[];
  agents: Record<string, AgentInfo>;
  health: Health | null;
  open: boolean;
  runActive: boolean;
  onClose: () => void;
}

const LEGEND = [
  ["var(--manager)", "Manager"],
  ["var(--panel)", "Panel agents"],
  ["var(--intervene)", "Intervention"],
  ["var(--summary)", "Round summary"],
  ["var(--final)", "Final answer"],
] as const;

export function AgentSidebar({ order, agents, health, open, runActive, onClose }: Props) {
  const panel = order.filter((id) => id !== MANAGER_ID);
  const active = panel.filter((id) => ["thinking", "speaking"].includes(agents[id]?.status)).length;
  return (
    <aside className={`sidebar ${open ? "is-open" : ""}`} aria-label="Agents">
      <div className="sidebar__head">
        <h2 className="sidebar__title">Agents</h2>
        <button className="icon-btn sidebar__close" onClick={onClose} aria-label="Close agent list">
          <X size={18} />
        </button>
      </div>
      <div className="sidebar__scroll">
        <p className="sidebar__section">Manager</p>
        <ul className="agent-list">
          <AgentStatusItem agentId={MANAGER_ID} info={agents[MANAGER_ID] ?? { status: "idle" }} runActive={runActive} />
        </ul>
        <p className="sidebar__section">
          Panel <span className="sidebar__count">{active ? `${active} active` : `${panel.length} agents`}</span>
        </p>
        <ul className="agent-list">
          {panel.map((id) => (
            <AgentStatusItem key={id} agentId={id} info={agents[id] ?? { status: "idle" }} runActive={runActive} />
          ))}
        </ul>
      </div>
      <div className="sidebar__foot">
        <ul className="legend">
          {LEGEND.map(([color, label]) => (
            <li key={label}>
              <span className="legend__swatch" style={{ background: color }} />
              {label}
            </li>
          ))}
        </ul>
        {health && (
          <p className="sidebar__models">
            Manager <code>{health.manager_model}</code> · Panel <code>{health.panel_model}</code>
          </p>
        )}
      </div>
    </aside>
  );
}
