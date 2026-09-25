import type { CSSProperties } from "react";
import { accentVar, agentLabel, MANAGER_ID } from "../lib/colors";
import { pct } from "../lib/format";
import type { AgentInfo } from "../lib/runReducer";
import { Avatar } from "./Avatar";

const STATUS_TEXT = {
  idle: "Idle",
  thinking: "Thinking…",
  speaking: "Speaking",
  done: "Done",
  error: "Error",
} as const;

interface Props {
  agentId: string;
  info: AgentInfo;
  runActive: boolean;
}

export function AgentStatusItem({ agentId, info, runActive }: Props) {
  const isManager = agentId === MANAGER_ID;
  const style = { "--accent-color": accentVar(agentId) } as CSSProperties;
  return (
    <li className={`agent-item is-${info.status}`} style={style}>
      <Avatar agentId={agentId} status={info.status} />
      <div className="agent-item__body">
        <div className="agent-item__row">
          <span className="agent-item__name">{agentLabel(agentId)}</span>
          <span className={`status-pill status-pill--${info.status}`}>
            {info.status === "speaking" && <span className="speaking-bars" aria-hidden="true"><i /><i /><i /></span>}
            {isManager && runActive && info.status === "idle" ? "Supervising" : STATUS_TEXT[info.status]}
          </span>
        </div>
        {isManager ? (
          <p className="agent-item__meta">Plans · supervises · verifies</p>
        ) : info.stance ? (
          <>
            <p className="agent-item__meta" title={info.stance}>
              {info.shifted && <span className="tag tag--shift">DA</span>}
              <span className="agent-item__stance">{info.stance}</span>
            </p>
            <div className="confidence-bar" title={`Confidence ${pct(info.confidence)}`}>
              <span style={{ width: pct(info.confidence ?? 0) }} />
            </div>
          </>
        ) : (
          <p className="agent-item__meta agent-item__meta--empty">Waiting for a position</p>
        )}
      </div>
    </li>
  );
}
