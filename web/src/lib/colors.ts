// agent_id → accent color. Values come from CSS tokens in styles/tokens.css.

export const MANAGER_ID = "manager";

export function accentVar(agentId: string): string {
  if (agentId === MANAGER_ID) return "var(--manager)";
  const m = /^panel_agent_(\d\d)$/.exec(agentId);
  return m ? `var(--agent-${m[1]})` : "var(--thinking)";
}

export function agentLabel(agentId: string): string {
  if (agentId === MANAGER_ID) return "Manager";
  const m = /^panel_agent_(\d\d)$/.exec(agentId);
  return m ? `Panel ${m[1]}` : agentId;
}

export function agentInitials(agentId: string): string {
  if (agentId === MANAGER_ID) return "M";
  const m = /^panel_agent_(\d\d)$/.exec(agentId);
  return m ? m[1] : "?";
}

// Cluster colors for round vote bars: leader in panel teal, then distinct supporting hues.
export const CLUSTER_COLORS = ["var(--panel)", "var(--agent-05)", "var(--agent-06)", "var(--thinking)"];
