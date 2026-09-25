export function timeOf(ts: string): string {
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function elapsed(fromMs: number, toMs: number): string {
  const s = Math.max(0, Math.round((toMs - fromMs) / 1000));
  const m = Math.floor(s / 60);
  return m ? `${m}m ${String(s % 60).padStart(2, "0")}s` : `${s}s`;
}

export function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

export function pct(x: number | null | undefined): string {
  return x == null ? "–" : `${Math.round(x * 100)}%`;
}

export const STOP_REASON_TEXT: Record<string, string> = {
  consensus: "Consensus reached",
  max_rounds: "Round limit reached",
  no_new_arguments: "No new arguments",
  intervention_abort: "Aborted by manager",
};
