import { MANAGER_ID } from "./colors";
import type {
  AgentMessageEvent,
  AgentStatus,
  ConsensusEvent,
  FinalAnswerEvent,
  ManagerInterventionEvent,
  RoundStartedEvent,
  RoundSummaryEvent,
  UIEvent,
} from "./types";

export type Phase = "idle" | "starting" | "running" | "completed" | "cancelled" | "error";

export type StreamItem =
  | { kind: "message"; id: number; event: AgentMessageEvent }
  | { kind: "system"; id: number; event: AgentMessageEvent }
  | { kind: "intervention"; id: number; event: ManagerInterventionEvent }
  | { kind: "divider"; id: number; event: RoundStartedEvent }
  | { kind: "summary"; id: number; event: RoundSummaryEvent }
  | { kind: "consensus"; id: number; event: ConsensusEvent };

export interface AgentInfo {
  status: AgentStatus;
  stance?: string;
  confidence?: number | null;
  round?: number | null;
  shifted?: boolean;
}

export interface Toast {
  id: number;
  message: string;
}

export interface RunState {
  phase: Phase;
  runId?: string;
  topic: string;
  demo: boolean;
  startedAt?: number;
  finishedAt?: number;
  stopping: boolean;
  items: StreamItem[];
  agents: Record<string, AgentInfo>;
  agentOrder: string[];
  roundLabel?: string;
  consensus?: ConsensusEvent;
  final?: FinalAnswerEvent;
  toasts: Toast[];
  lastSeq: number;
}

export type Action =
  | { type: "start_request"; topic: string; demo: boolean }
  | { type: "start_ok"; runId: string }
  | { type: "start_fail"; message: string }
  | { type: "stop_request" }
  | { type: "toast"; message: string }
  | { type: "dismiss_toast"; id: number }
  | { type: "event"; event: UIEvent };

const DEFAULT_AGENTS = [MANAGER_ID, ...Array.from({ length: 10 }, (_, i) => `panel_agent_${String(i).padStart(2, "0")}`)];

function idleAgents(order: string[]): Record<string, AgentInfo> {
  return Object.fromEntries(order.map((id) => [id, { status: "idle" as AgentStatus }]));
}

export const initialRunState: RunState = {
  phase: "idle",
  topic: "",
  demo: false,
  stopping: false,
  items: [],
  agents: idleAgents(DEFAULT_AGENTS),
  agentOrder: DEFAULT_AGENTS,
  toasts: [],
  lastSeq: 0,
};

let toastSeq = 0;
const toast = (message: string): Toast => ({ id: ++toastSeq, message });

export function runReducer(state: RunState, action: Action): RunState {
  switch (action.type) {
    case "start_request":
      return {
        ...initialRunState,
        agentOrder: state.agentOrder,
        agents: idleAgents(state.agentOrder),
        phase: "starting",
        topic: action.topic,
        demo: action.demo,
        startedAt: Date.now(),
        toasts: state.toasts,
      };
    case "start_ok":
      return { ...state, phase: "running", runId: action.runId };
    case "start_fail":
      return { ...state, phase: "error", finishedAt: Date.now(), toasts: [...state.toasts, toast(action.message)] };
    case "stop_request":
      return { ...state, stopping: true };
    case "toast":
      return { ...state, toasts: [...state.toasts, toast(action.message)] };
    case "dismiss_toast":
      return { ...state, toasts: state.toasts.filter((t) => t.id !== action.id) };
    case "event":
      return applyEvent(state, action.event);
  }
}

function applyEvent(state: RunState, ev: UIEvent): RunState {
  if (ev.seq <= state.lastSeq) return state; // replayed after reconnect
  const s: RunState = { ...state, lastSeq: ev.seq };
  const push = (item: StreamItem) => (s.items = [...state.items, item]);

  switch (ev.type) {
    case "run_started":
      s.agentOrder = ev.agents;
      s.agents = idleAgents(ev.agents);
      s.demo = ev.demo;
      break;
    case "agent_message":
      if (ev.role === "system") {
        push({ kind: "system", id: ev.seq, event: ev });
      } else {
        push({ kind: "message", id: ev.seq, event: ev });
        if (ev.role === "panel") {
          s.agents = {
            ...state.agents,
            [ev.agent_id]: {
              ...state.agents[ev.agent_id],
              stance: ev.stance ?? undefined,
              confidence: ev.confidence,
              round: ev.round_index,
              shifted: ev.shifted,
            },
          };
        }
      }
      break;
    case "manager_intervention":
      push({ kind: "intervention", id: ev.seq, event: ev });
      break;
    case "round_started":
      push({ kind: "divider", id: ev.seq, event: ev });
      s.roundLabel = ev.label;
      break;
    case "round_summary":
      push({ kind: "summary", id: ev.seq, event: ev });
      break;
    case "consensus":
      push({ kind: "consensus", id: ev.seq, event: ev });
      s.consensus = ev;
      break;
    case "final_answer":
      s.final = ev;
      break;
    case "status":
      s.agents = { ...state.agents, [ev.agent_id]: { ...state.agents[ev.agent_id], status: ev.status } };
      break;
    case "error":
      s.toasts = [...state.toasts, toast(ev.message)];
      break;
    case "run_finished":
      s.phase = ev.reason === "completed" ? "completed" : ev.reason === "cancelled" ? "cancelled" : "error";
      s.finishedAt = Date.now();
      s.stopping = false;
      break;
  }
  return s;
}

export function isActive(phase: Phase): boolean {
  return phase === "starting" || phase === "running";
}
