import { Check, ChevronDown, ChevronUp, CircleCheck, CircleX, Copy, ExternalLink, LoaderCircle, Scale } from "lucide-react";
import { useEffect, useState } from "react";
import { domainOf, pct, STOP_REASON_TEXT } from "../lib/format";
import type { Phase } from "../lib/runReducer";
import type { ConsensusEvent, FinalAnswerEvent } from "../lib/types";

interface Props {
  phase: Phase;
  final?: FinalAnswerEvent;
  consensus?: ConsensusEvent;
  roundLabel?: string;
}

export function ConclusionPanel({ phase, final, consensus, roundLabel }: Props) {
  const [expanded, setExpanded] = useState(true);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (final) setExpanded(true);
  }, [final]);

  if (!final) {
    const active = phase === "starting" || phase === "running";
    return (
      <section className={`conclusion conclusion--placeholder ${active ? "is-active" : ""}`} aria-label="Final conclusion">
        {active ? (
          <LoaderCircle size={16} className="spin" aria-hidden="true" />
        ) : phase === "cancelled" || phase === "error" ? (
          <CircleX size={16} aria-hidden="true" />
        ) : (
          <CircleCheck size={16} aria-hidden="true" />
        )}
        <span>
          {active
            ? `The manager will verify and synthesize once the panel settles${roundLabel ? ` · ${roundLabel}` : ""}.`
            : phase === "cancelled"
              ? "Run stopped before a conclusion was reached."
              : phase === "error"
                ? "The run failed before a conclusion was reached."
                : "The manager's verified conclusion will appear here."}
        </span>
        {active && consensus && (
          <span className="tag">
            <Scale size={12} aria-hidden="true" /> Hop {consensus.hop}: {consensus.status}
          </span>
        )}
      </section>
    );
  }

  const r = final.result;
  const panel = r.panel;
  const copy = async () => {
    const text = [r.answer, "", ...r.key_points.map((p) => `• ${p}`)].join("\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <section className={`conclusion conclusion--final ${expanded ? "is-expanded" : ""}`} aria-label="Final conclusion">
      <header className="conclusion__head">
        <CircleCheck size={18} className="c-final" aria-hidden="true" />
        <h2>Final conclusion</h2>
        <span className={`confidence-pill confidence-pill--${r.confidence}`}>{r.confidence} confidence</span>
        <span className="conclusion__meta">
          Panel {panel.status} · {panel.hops} hop{panel.hops === 1 ? "" : "s"} · {panel.rounds} rounds
          {panel.stop_reason && ` · ${STOP_REASON_TEXT[panel.stop_reason] ?? panel.stop_reason}`}
          {panel.interventions.length > 0 && ` · ${panel.interventions.length} intervention${panel.interventions.length > 1 ? "s" : ""}`}
          {panel.confidence != null && ` · panel conf ${pct(panel.confidence)}`}
        </span>
        <span className="conclusion__actions">
          <button className="icon-btn" onClick={copy} aria-label="Copy conclusion" title="Copy">
            {copied ? <Check size={16} /> : <Copy size={16} />}
          </button>
          <button
            className="icon-btn"
            onClick={() => setExpanded((e) => !e)}
            aria-label={expanded ? "Collapse conclusion" : "Expand conclusion"}
            aria-expanded={expanded}
          >
            {expanded ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
          </button>
        </span>
      </header>

      {expanded && (
        <div className="conclusion__body">
          <div className="conclusion__main">
            <p className="conclusion__answer">{r.answer}</p>
            {r.key_points.length > 0 && (
              <ul className="conclusion__points">
                {r.key_points.map((p) => <li key={p}>{p}</li>)}
              </ul>
            )}
          </div>
          <aside className="conclusion__aside">
            {r.sources.length > 0 && (
              <div>
                <h3>Sources</h3>
                <ul className="conclusion__sources">
                  {r.sources.map((s, i) => (
                    <li key={`${s.url}-${i}`}>
                      {s.url ? (
                        <a href={s.url} target="_blank" rel="noopener noreferrer">
                          <ExternalLink size={11} aria-hidden="true" /> {s.title}
                          <span className="citation__domain">{domainOf(s.url)}</span>
                        </a>
                      ) : (
                        s.title
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div>
              <h3>Confidence notes</h3>
              <p>{r.confidence_notes}</p>
            </div>
            {r.open_questions.length > 0 && (
              <div>
                <h3>Open questions</h3>
                <ul>{r.open_questions.map((q) => <li key={q}>{q}</li>)}</ul>
              </div>
            )}
            {r.verification && (
              <div>
                <h3>Manager review</h3>
                <p>{r.verification}</p>
              </div>
            )}
          </aside>
        </div>
      )}
    </section>
  );
}
