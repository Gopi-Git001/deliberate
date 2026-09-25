// SSE event contract — mirrors src/manager_agent/ui/events.py. Keep in sync.

export type AgentStatus = "idle" | "thinking" | "speaking" | "done" | "error";
export type Role = "manager" | "panel" | "system";
export type MessageKind = "plan" | "research" | "handoff" | "review" | "turn" | "shift" | "stop" | "note";

interface Base {
  run_id: string;
  seq: number;
  ts: string;
}

export interface Citation {
  title: string;
  url: string;
}

export interface RunStartedEvent extends Base {
  type: "run_started";
  topic: string;
  constraints: string;
  demo: boolean;
  agents: string[];
}

export interface AgentMessageEvent extends Base {
  type: "agent_message";
  agent_id: string;
  agent_label: string;
  role: Role;
  kind: MessageKind;
  content: string;
  round_index: number | null;
  hop: number | null;
  stance: string | null;
  citations: Citation[];
  confidence: number | null;
  shifted: boolean;
  uncited: boolean;
  addressed_agents: string[];
  position_decision: "" | "hold" | "revise" | "abandon";
  stance_delta: string;
  persuasion_target: string;
  persuasion_appeal: string;
  engagement_failed: boolean;
}

export interface ManagerInterventionEvent extends Base {
  type: "manager_intervention";
  content: string;
  reason: string;
  round_index: number | null;
  hop: number;
}

export interface RoundStartedEvent extends Base {
  type: "round_started";
  round_index: number;
  hop: number;
  label: string;
}

export interface Cluster {
  answer: string;
  agent_ids: string[];
  share: number;
  confidence: number;
}

export interface RoundSummaryEvent extends Base {
  type: "round_summary";
  round_index: number;
  hop: number;
  summary: string;
  clusters: Cluster[];
  novelty: number | null;
}

export interface ConsensusEvent extends Base {
  type: "consensus";
  consensus: string;
  status: string;
  confidence: number | null;
  stop_reason: string | null;
  dissent: string;
  hop: number;
}

export interface FinalResult {
  answer: string;
  key_points: string[];
  sources: { title: string; url: string }[];
  confidence: "low" | "medium" | "high";
  confidence_notes: string;
  open_questions: string[];
  topic: string;
  panel: {
    status: string;
    hops: number;
    rounds: number;
    confidence: number | null;
    stop_reason: string;
    dissent: string;
    interventions: { hop: number; reason: string; directive: string }[];
  };
  verification: string;
  tool_calls: number;
}

export interface FinalAnswerEvent extends Base {
  type: "final_answer";
  content: string;
  result: FinalResult;
}

export interface StatusEvent extends Base {
  type: "status";
  agent_id: string;
  status: AgentStatus;
}

export interface ErrorEvent extends Base {
  type: "error";
  message: string;
}

export interface RunFinishedEvent extends Base {
  type: "run_finished";
  reason: "completed" | "cancelled" | "error";
}

export type UIEvent =
  | RunStartedEvent
  | AgentMessageEvent
  | ManagerInterventionEvent
  | RoundStartedEvent
  | RoundSummaryEvent
  | ConsensusEvent
  | FinalAnswerEvent
  | StatusEvent
  | ErrorEvent
  | RunFinishedEvent;

export interface Health {
  status: string;
  openai_key_configured: boolean;
  tavily_key_configured: boolean;
  manager_model: string;
  panel_model: string;
  panel_size: number;
  active_runs: number;
}
