import { useEffect, useRef, useState } from "react";
import type { UIEvent } from "../lib/types";

export type ConnectionState = "idle" | "connecting" | "open" | "reconnecting" | "closed";

/** Subscribe to a run's SSE stream. The browser reconnects with Last-Event-ID automatically;
 *  the server replays anything missed and the reducer drops duplicates by `seq`. */
export function useEventSource(
  runId: string | undefined,
  onEvent: (event: UIEvent) => void,
  onFatal: (message: string) => void,
): ConnectionState {
  const [state, setState] = useState<ConnectionState>("idle");
  const handlers = useRef({ onEvent, onFatal });
  handlers.current = { onEvent, onFatal };

  useEffect(() => {
    if (!runId) {
      setState("idle");
      return;
    }
    setState("connecting");
    const es = new EventSource(`/api/runs/${runId}/events`);
    let finished = false;

    es.onopen = () => setState("open");
    es.onmessage = (msg) => {
      let event: UIEvent;
      try {
        event = JSON.parse(msg.data) as UIEvent;
      } catch {
        return;
      }
      handlers.current.onEvent(event);
      if (event.type === "run_finished") {
        finished = true;
        es.close();
        setState("closed");
      }
    };
    es.onerror = () => {
      if (finished) return;
      if (es.readyState === EventSource.CLOSED) {
        setState("closed");
        handlers.current.onFatal("Lost connection to the server.");
      } else {
        setState("reconnecting");
      }
    };
    return () => {
      finished = true;
      es.close();
    };
  }, [runId]);

  return state;
}
