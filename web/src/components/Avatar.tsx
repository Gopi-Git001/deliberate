import type { CSSProperties } from "react";
import { accentVar, agentInitials } from "../lib/colors";
import type { AgentStatus } from "../lib/types";

interface Props {
  agentId: string;
  status?: AgentStatus;
  size?: "sm" | "md";
}

export function Avatar({ agentId, status, size = "md" }: Props) {
  const style = { "--accent-color": accentVar(agentId) } as CSSProperties;
  return (
    <span className={`avatar avatar--${size} ${status ? `is-${status}` : ""}`} style={style} aria-hidden="true">
      {agentInitials(agentId)}
      {status && <span className="avatar__dot" />}
    </span>
  );
}
