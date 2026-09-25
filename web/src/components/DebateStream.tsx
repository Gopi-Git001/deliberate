import { MessagesSquare } from "lucide-react";
import { useAutoScroll } from "../hooks/useAutoScroll";
import type { Phase, StreamItem } from "../lib/runReducer";
import { InterventionCard } from "./InterventionCard";
import { JumpToLatestButton } from "./JumpToLatestButton";
import { MessageBubble } from "./MessageBubble";
import { PanelConsensusCard } from "./PanelConsensusCard";
import { RoundDivider } from "./RoundDivider";
import { RoundSummaryCard } from "./RoundSummaryCard";
import { SystemNote } from "./SystemNote";
import { TypingIndicator } from "./TypingIndicator";

const EXAMPLES = [
  "Should cities ban private cars from downtown cores?",
  "Is a four-day work week good for knowledge-worker productivity?",
  "Should small teams adopt microservices from day one?",
];

interface Props {
  items: StreamItem[];
  phase: Phase;
  runId?: string;
  thinking: string[];
  onExample: (topic: string) => void;
}

function renderItem(item: StreamItem) {
  switch (item.kind) {
    case "message":
      return <MessageBubble event={item.event} />;
    case "system":
      return <SystemNote event={item.event} />;
    case "intervention":
      return <InterventionCard event={item.event} />;
    case "divider":
      return <RoundDivider event={item.event} />;
    case "summary":
      return <RoundSummaryCard event={item.event} />;
    case "consensus":
      return <PanelConsensusCard event={item.event} />;
  }
}

export function DebateStream({ items, phase, runId, thinking, onExample }: Props) {
  const { ref, pinned, unseen, onScroll, jumpToLatest } = useAutoScroll(items.length, runId);
  const active = phase === "starting" || phase === "running";

  return (
    <section className="stream" aria-label="Live debate">
      <div className="stream__scroll" ref={ref} onScroll={onScroll} aria-live="polite" aria-busy={active}>
        <div className="stream__inner">
          {phase === "idle" && items.length === 0 && (
            <div className="empty">
              <span className="empty__icon"><MessagesSquare size={28} aria-hidden="true" /></span>
              <h2>Put a question to the panel</h2>
              <p>
                The <span className="c-manager">manager</span> plans the research and briefs ten{" "}
                <span className="c-panel">panel agents</span>. They debate in rounds with citations, and a devil's
                advocate tests the majority. Every round is summarized for the manager, which{" "}
                <span className="c-intervene">intervenes</span> only if the debate drifts, then delivers one{" "}
                <span className="c-final">verified conclusion</span>.
              </p>
              <div className="empty__examples">
                {EXAMPLES.map((t) => (
                  <button key={t} className="chip" onClick={() => onExample(t)}>{t}</button>
                ))}
              </div>
            </div>
          )}

          {items.map((item) => (
            <div key={item.id} className="stream__item">{renderItem(item)}</div>
          ))}

          {active && items.length < 2 && (
            <div className="skeletons" aria-hidden="true">
              {[0, 1, 2].map((i) => (
                <div key={i} className="skeleton"><span /><span /><span /></div>
              ))}
            </div>
          )}

          {active && <TypingIndicator agentIds={thinking} />}
        </div>
      </div>
      {!pinned && items.length > 0 && <JumpToLatestButton unseen={unseen} onClick={jumpToLatest} />}
    </section>
  );
}
