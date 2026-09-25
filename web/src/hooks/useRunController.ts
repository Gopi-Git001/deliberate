import { useCallback, useReducer } from "react";
import { initialRunState, runReducer } from "../lib/runReducer";
import type { UIEvent } from "../lib/types";
import { useEventSource } from "./useEventSource";

async function errorText(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return typeof body.detail === "string" ? body.detail : `Request failed (${res.status})`;
  } catch {
    return `Request failed (${res.status})`;
  }
}

/** Owns the run lifecycle: POST /api/runs, SSE subscription, stop, toasts. */
export function useRunController() {
  const [state, dispatch] = useReducer(runReducer, initialRunState);

  const onEvent = useCallback((event: UIEvent) => dispatch({ type: "event", event }), []);
  const onFatal = useCallback((message: string) => dispatch({ type: "toast", message }), []);
  const connection = useEventSource(state.runId, onEvent, onFatal);

  const start = useCallback(async (topic: string, constraints: string, demo: boolean) => {
    dispatch({ type: "start_request", topic, demo });
    try {
      const res = await fetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, constraints, demo }),
      });
      if (!res.ok) throw new Error(await errorText(res));
      const { run_id } = (await res.json()) as { run_id: string };
      dispatch({ type: "start_ok", runId: run_id });
    } catch (err) {
      dispatch({ type: "start_fail", message: err instanceof Error ? err.message : String(err) });
    }
  }, []);

  const stop = useCallback(async () => {
    if (!state.runId) return;
    dispatch({ type: "stop_request" });
    try {
      const res = await fetch(`/api/runs/${state.runId}/stop`, { method: "POST" });
      if (!res.ok) throw new Error(await errorText(res));
    } catch (err) {
      dispatch({ type: "toast", message: err instanceof Error ? err.message : String(err) });
    }
  }, [state.runId]);

  const dismissToast = useCallback((id: number) => dispatch({ type: "dismiss_toast", id }), []);

  return { state, connection, start, stop, dismissToast };
}
