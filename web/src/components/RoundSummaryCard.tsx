import { ArrowUpRight } from "lucide-react";
import { agentLabel, CLUSTER_COLORS } from "../lib/colors";
import { pct } from "../lib/format";
import type { RoundSummaryEvent } from "../lib/types";

export function RoundSummaryCard({ event }: { event: RoundSummaryEvent }) {
  const total = event.clusters.reduce((n, c) => n + c.agent_ids.length, 0) || 1;
  return (
    <article className="summary" aria-label={`Round ${event.round_index} summary`}>
      <header className="summary__head">
        <span className="badge badge--summary">Round {event.round_index} summary</span>
        <span className="summary__handoff">
          <ArrowUpRight size={13} aria-hidden="true" /> handed to Manager
        </span>
        {event.novelty != null && (
          <span className="tag" title="Share of new arguments/sources vs the previous round">
            Novelty {pct(event.novelty)}
          </span>
        )}
      </header>

      {event.clusters.length > 0 && (
        <div className="votes">
          <div className="votes__bar" role="img" aria-label="Position split">
            {event.clusters.map((c, i) => (
              <span
                key={c.answer}
                style={{ flexGrow: c.agent_ids.length, background: CLUSTER_COLORS[Math.min(i, CLUSTER_COLORS.length - 1)] }}
                title={`${c.agent_ids.length}/${total}: ${c.answer}`}
              />
            ))}
          </div>
          <ul className="votes__legend">
            {event.clusters.slice(0, 4).map((c, i) => (
              <li key={c.answer} title={c.agent_ids.map(agentLabel).join(", ")}>
                <span className="legend__swatch" style={{ background: CLUSTER_COLORS[Math.min(i, CLUSTER_COLORS.length - 1)] }} />
                <strong>{c.agent_ids.length}/{total}</strong>
                <span className="votes__answer">{c.answer}</span>
                <span className="votes__conf">conf {pct(c.confidence)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="summary__text">{event.summary}</p>
    </article>
  );
}
