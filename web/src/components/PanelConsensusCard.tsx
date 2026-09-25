import { Scale } from "lucide-react";
import { pct, STOP_REASON_TEXT } from "../lib/format";
import type { ConsensusEvent } from "../lib/types";

/** The panel's conclusion for one hop, as returned to the manager. */
export function PanelConsensusCard({ event }: { event: ConsensusEvent }) {
  const reached = event.status === "consensus";
  return (
    <article className={`panel-consensus ${reached ? "" : "is-deadlock"}`}>
      <header className="summary__head">
        <Scale size={15} aria-hidden="true" />
        <span className="badge badge--panel">{reached ? "Panel consensus" : "No majority"}</span>
        <span className="tag">Hop {event.hop}</span>
        {event.stop_reason && <span className="tag">{STOP_REASON_TEXT[event.stop_reason] ?? event.stop_reason}</span>}
        <span className="tag">Confidence {pct(event.confidence)}</span>
      </header>
      <p className="panel-consensus__text">{event.consensus}</p>
      {event.dissent && <p className="panel-consensus__dissent">Dissent: {event.dissent}</p>}
    </article>
  );
}
