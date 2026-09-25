import { useEffect, useMemo, useState } from "react";
import { AgentSidebar } from "./components/AgentSidebar";
import { AppShell } from "./components/AppShell";
import { ConclusionPanel } from "./components/ConclusionPanel";
import { DebateStream } from "./components/DebateStream";
import { ErrorToast } from "./components/ErrorToast";
import { TopicBar } from "./components/TopicBar";
import { useRunController } from "./hooks/useRunController";
import { isActive } from "./lib/runReducer";
import type { Health } from "./lib/types";

export default function App() {
  const { state, connection, start, stop, dismissToast } = useRunController();
  const [topic, setTopic] = useState("");
  const [health, setHealth] = useState<Health | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    fetch("/api/health")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`health ${r.status}`))))
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  const thinking = useMemo(
    () => state.agentOrder.filter((id) => state.agents[id]?.status === "thinking"),
    [state.agentOrder, state.agents],
  );

  return (
    <AppShell
      sidebarOpen={sidebarOpen}
      onCloseSidebar={() => setSidebarOpen(false)}
      top={
        <TopicBar
          topic={topic}
          onTopicChange={setTopic}
          phase={state.phase}
          stopping={state.stopping}
          roundLabel={state.roundLabel}
          startedAt={state.startedAt}
          finishedAt={state.finishedAt}
          reconnecting={connection === "reconnecting"}
          health={health}
          onSubmit={start}
          onStop={stop}
          onMenu={() => setSidebarOpen(true)}
        />
      }
      sidebar={
        <AgentSidebar
          order={state.agentOrder}
          agents={state.agents}
          health={health}
          open={sidebarOpen}
          runActive={isActive(state.phase)}
          onClose={() => setSidebarOpen(false)}
        />
      }
      stream={
        <DebateStream
          items={state.items}
          phase={state.phase}
          runId={state.runId}
          thinking={thinking}
          onExample={setTopic}
        />
      }
      conclusion={
        <ConclusionPanel phase={state.phase} final={state.final} consensus={state.consensus} roundLabel={state.roundLabel} />
      }
      overlay={<ErrorToast toasts={state.toasts} onDismiss={dismissToast} />}
    />
  );
}
