import { TriangleAlert } from "lucide-react";
import { timeOf } from "../lib/format";
import type { ManagerInterventionEvent } from "../lib/types";
import { Avatar } from "./Avatar";

export function InterventionCard({ event }: { event: ManagerInterventionEvent }) {
  return (
    <article className="intervention" role="note" aria-label="Manager intervention">
      <header className="intervention__head">
        <span className="intervention__icon"><TriangleAlert size={16} aria-hidden="true" /></span>
        <Avatar agentId="manager" size="sm" />
        <span className="badge badge--intervene">Manager intervention</span>
        <span className="tag">Hop {event.hop} → {event.hop + 1}</span>
        <time className="bubble__time" dateTime={event.ts}>{timeOf(event.ts)}</time>
      </header>
      {event.reason && <p className="intervention__reason">{event.reason}</p>}
      <blockquote className="intervention__directive">
        <span className="intervention__label">Directive to panel</span>
        {event.content}
      </blockquote>
    </article>
  );
}
