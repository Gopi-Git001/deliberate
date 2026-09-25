import { FlaskConical, LoaderCircle, Menu, Send, SlidersHorizontal, Square } from "lucide-react";
import { useEffect, useState, type FormEvent, type KeyboardEvent } from "react";
import { elapsed } from "../lib/format";
import type { Phase } from "../lib/runReducer";
import type { Health } from "../lib/types";

interface Props {
  topic: string;
  onTopicChange: (topic: string) => void;
  phase: Phase;
  stopping: boolean;
  roundLabel?: string;
  startedAt?: number;
  finishedAt?: number;
  reconnecting: boolean;
  health: Health | null;
  onSubmit: (topic: string, constraints: string, demo: boolean) => void;
  onStop: () => void;
  onMenu: () => void;
}

function useNow(active: boolean) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [active]);
  return now;
}

export function TopicBar(p: Props) {
  const [constraints, setConstraints] = useState("");
  const [showConstraints, setShowConstraints] = useState(false);
  const [demoPref, setDemoPref] = useState(false);
  const active = p.phase === "starting" || p.phase === "running";
  const now = useNow(active);
  const keyMissing = p.health != null && !p.health.openai_key_configured;
  const demo = keyMissing || demoPref;
  const canSubmit = p.topic.trim().length >= 3 && !active;

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (canSubmit) p.onSubmit(p.topic.trim(), constraints.trim(), demo);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const time = p.startedAt ? elapsed(p.startedAt, active ? now : (p.finishedAt ?? now)) : "";
  const status: Record<Phase, string> = {
    idle: "Ready",
    starting: "Starting…",
    running: p.stopping ? "Stopping…" : p.reconnecting ? "Reconnecting…" : `Running · ${p.roundLabel ?? "Planning"}`,
    completed: `Completed · ${time}`,
    cancelled: "Stopped",
    error: "Error",
  };

  return (
    <header className="topbar">
      <form className="topbar__form" onSubmit={submit}>
        <button type="button" className="icon-btn topbar__menu" onClick={p.onMenu} aria-label="Show agents">
          <Menu size={20} />
        </button>
        <div className="brand" aria-label="Deliberate">
          <img src="/favicon.svg" alt="" width={26} height={26} />
          <span>Deliberate</span>
        </div>

        <div className="topbar__inputs">
          <div className="topic-field">
            <textarea
              className="topic-input"
              rows={1}
              value={p.topic}
              onChange={(e) => p.onTopicChange(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Ask the panel a question…"
              aria-label="Topic"
              maxLength={2000}
              disabled={active}
            />
            <button
              type="button"
              className={`icon-btn ${showConstraints ? "is-on" : ""}`}
              onClick={() => setShowConstraints((s) => !s)}
              aria-label="Constraints"
              aria-expanded={showConstraints}
              title="Constraints (audience, depth, deadline)"
            >
              <SlidersHorizontal size={17} />
            </button>
          </div>
          {showConstraints && (
            <input
              className="constraints-input"
              value={constraints}
              onChange={(e) => setConstraints(e.target.value)}
              placeholder="Constraints — e.g. audience: executives · depth: brief · focus: EU"
              aria-label="Constraints"
              maxLength={1000}
              disabled={active}
            />
          )}
        </div>

        <label
          className={`demo-toggle ${demo ? "is-on" : ""} ${keyMissing ? "is-locked" : ""}`}
          title={keyMissing ? "No OPENAI_API_KEY on the server: demo mode only" : "Scripted responses through the real graph; no API calls"}
        >
          <input type="checkbox" checked={demo} disabled={keyMissing || active} onChange={(e) => setDemoPref(e.target.checked)} />
          <span className="demo-toggle__track"><span /></span>
          <FlaskConical size={14} aria-hidden="true" /> Demo
        </label>

        {active ? (
          <button type="button" className="btn btn--stop" onClick={p.onStop} disabled={p.stopping || p.phase === "starting"}>
            {p.stopping ? <LoaderCircle size={16} className="spin" /> : <Square size={14} />}
            Stop
          </button>
        ) : (
          <button type="submit" className="btn btn--primary" disabled={!canSubmit}>
            <Send size={15} /> Deliberate
          </button>
        )}

        <span className={`run-chip run-chip--${p.phase}`} role="status">
          <span className="run-chip__dot" />
          {status[p.phase]}
          {active && time && <span className="run-chip__time">{time}</span>}
        </span>
      </form>
    </header>
  );
}
