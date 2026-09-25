import { ExternalLink, ListChecks, Search, Send, ShieldCheck, type LucideIcon } from "lucide-react";
import type { CSSProperties } from "react";
import { accentVar, agentLabel } from "../lib/colors";
import { domainOf, pct, timeOf } from "../lib/format";
import type { AgentMessageEvent, MessageKind } from "../lib/types";
import { Avatar } from "./Avatar";

const MANAGER_KIND: Partial<Record<MessageKind, [LucideIcon, string]>> = {
  plan: [ListChecks, "Research plan"],
  research: [Search, "Research"],
  handoff: [Send, "Delegation"],
  review: [ShieldCheck, "Review"],
};

export function MessageBubble({ event }: { event: AgentMessageEvent }) {
  const isManager = event.role === "manager";
  const style = { "--accent-color": accentVar(event.agent_id) } as CSSProperties;
  const kind = isManager ? MANAGER_KIND[event.kind] : undefined;
  const KindIcon = kind?.[0];

  return (
    <article className={`bubble ${isManager ? "bubble--manager" : "bubble--panel"}`} style={style}>
      <header className="bubble__head">
        <Avatar agentId={event.agent_id} size="sm" />
        <span className="badge">{event.agent_label}</span>
        {kind && KindIcon && (
          <span className="bubble__kind">
            <KindIcon size={13} aria-hidden="true" /> {kind[1]}
          </span>
        )}
        {!isManager && event.round_index != null && (
          <span className="tag">{event.round_index === 0 ? "Research" : `R${event.round_index}`}</span>
        )}
        {event.shifted && <span className="tag tag--shift" title="Forced to argue the opposite side">Devil's advocate</span>}
        {event.position_decision && (
          <span className={`tag tag--decision tag--${event.position_decision}`} title={event.stance_delta}>
            {event.position_decision}
          </span>
        )}
        {event.uncited && <span className="tag tag--warn" title="No citations — peers will challenge this">Uncited</span>}
        {event.engagement_failed && (
          <span className="tag tag--warn" title="Failed the engagement check after a retry">Engagement failed</span>
        )}
        <time className="bubble__time" dateTime={event.ts}>{timeOf(event.ts)}</time>
      </header>

      {event.addressed_agents?.length > 0 && (
        <p className="bubble__replying">
          Replying to {event.addressed_agents.map(agentLabel).join(", ")}
          {event.persuasion_target && <> · convincing <strong>{agentLabel(event.persuasion_target)}</strong></>}
        </p>
      )}
      {event.stance && <p className="bubble__stance">{event.stance}</p>}
      {event.content && <p className="bubble__text">{event.content}</p>}
      {event.persuasion_appeal && <p className="bubble__appeal">“{event.persuasion_appeal}”</p>}

      {(event.citations.length > 0 || event.confidence != null) && (
        <footer className="bubble__foot">
          {event.citations.length > 0 && (
            <ul className="citations" aria-label="Citations">
              {event.citations.map((c, i) => (
                <li key={`${c.url}-${i}`}>
                  {c.url ? (
                    <a className="citation" href={c.url} target="_blank" rel="noopener noreferrer" title={c.title}>
                      <ExternalLink size={11} aria-hidden="true" />
                      <span className="citation__title">{c.title}</span>
                      <span className="citation__domain">{domainOf(c.url)}</span>
                    </a>
                  ) : (
                    <span className="citation">{c.title}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
          {event.confidence != null && (
            <div className="confidence" title="Calibrated confidence (self-rating × evidence × source quality)">
              <span className="confidence__label">Confidence</span>
              <span className="confidence-bar confidence-bar--wide">
                <span style={{ width: pct(event.confidence) }} />
              </span>
              <span className="confidence__value">{pct(event.confidence)}</span>
            </div>
          )}
        </footer>
      )}
    </article>
  );
}
