import { Flag, Info, Shuffle } from "lucide-react";
import type { AgentMessageEvent } from "../lib/types";

export function SystemNote({ event }: { event: AgentMessageEvent }) {
  const Icon = event.kind === "shift" ? Shuffle : event.kind === "stop" ? Flag : Info;
  return (
    <div className={`system-note system-note--${event.kind}`} role="status">
      <Icon size={13} aria-hidden="true" />
      <span>{event.content}</span>
    </div>
  );
}
