import type { RoundStartedEvent } from "../lib/types";

export function RoundDivider({ event }: { event: RoundStartedEvent }) {
  return (
    <div className="round-divider" role="separator" aria-label={event.label}>
      <span>{event.label}</span>
    </div>
  );
}
