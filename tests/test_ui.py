"""Web UI backend: REST + SSE over the real LangGraph graph (demo brain, no keys, no network)."""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from manager_agent.config import get_settings
from manager_agent.panel.config import get_panel_settings
from manager_agent.ui.app import app, registry
from manager_agent.ui.events import Translator


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("UI_DEMO_DELAY", "0")
    get_settings.cache_clear()
    get_panel_settings.cache_clear()
    with TestClient(app) as c:
        yield c
    for run in list(registry.runs.values()):  # never leak running demo threads
        run.cancel_event.set()


def sse_events(client: TestClient, run_id: str, headers: dict | None = None) -> list[dict]:
    events = []
    with client.stream("GET", f"/api/runs/{run_id}/events", headers=headers or {}) as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        for line in res.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
                if events[-1]["type"] == "run_finished":
                    break
    return events


def start(client: TestClient, topic: str = "Should cities ban cars downtown?", **kw) -> str:
    res = client.post("/api/runs", json={"topic": topic, "demo": True, **kw})
    assert res.status_code == 201, res.text
    return res.json()["run_id"]


def test_health_never_exposes_secrets(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-123")
    get_settings.cache_clear()
    body = client.get("/api/health").json()
    assert body["openai_key_configured"] is True
    assert "sk-test-secret-123" not in json.dumps(body)


def test_real_run_requires_key(client):
    res = client.post("/api/runs", json={"topic": "Some topic"})
    assert res.status_code == 400 and "OPENAI_API_KEY" in res.json()["detail"]


def test_topic_validation(client):
    assert client.post("/api/runs", json={"topic": "", "demo": True}).status_code == 422


def test_demo_run_streams_full_contract(client):
    events = sse_events(client, start(client))
    types = [e["type"] for e in events]

    assert types[0] == "run_started" and types[-1] == "run_finished"
    assert events[-1]["reason"] == "completed"
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert all(e["run_id"] == events[0]["run_id"] and e["ts"] for e in events)
    for t in ("agent_message", "status", "round_started", "round_summary",
              "manager_intervention", "consensus", "final_answer"):
        assert t in types, t
    assert types.index("manager_intervention") < types.index("final_answer")

    msgs = [e for e in events if e["type"] == "agent_message"]
    panel_labels = {e["agent_label"] for e in msgs if e["role"] == "panel"}
    assert panel_labels == {f"Panel {i:02d}" for i in range(10)}
    assert any(e["role"] == "manager" and e["agent_label"] == "Manager" for e in msgs)
    turn = next(e for e in msgs if e["role"] == "panel")
    assert turn["stance"] and turn["confidence"] is not None and "citations" in turn

    statuses = {e["status"] for e in events if e["type"] == "status"}
    assert {"thinking", "speaking", "done"} <= statuses
    final = next(e for e in events if e["type"] == "final_answer")
    assert final["content"] and final["result"]["panel"]["hops"] == 2


def test_reconnect_replays_only_missed_events(client):
    run_id = start(client)
    full = sse_events(client, run_id)
    tail = sse_events(client, run_id, headers={"Last-Event-ID": str(len(full) - 5)})
    assert [e["seq"] for e in tail] == [e["seq"] for e in full[-5:]]


def test_stop_cancels_run(client, monkeypatch):
    monkeypatch.setenv("UI_DEMO_DELAY", "0.3")
    get_settings.cache_clear()
    run_id = start(client)
    time.sleep(1.0)
    assert client.post(f"/api/runs/{run_id}/stop").json() == {"stopping": True}
    events = sse_events(client, run_id)
    assert events[-1] == {**events[-1], "type": "run_finished", "reason": "cancelled"}
    assert "final_answer" not in [e["type"] for e in events]


def test_active_run_limit(client, monkeypatch):
    monkeypatch.setenv("UI_DEMO_DELAY", "0.3")
    monkeypatch.setenv("UI_MAX_ACTIVE_RUNS", "1")
    get_settings.cache_clear()
    first = start(client)
    assert client.post("/api/runs", json={"topic": "Another topic", "demo": True}).status_code == 429
    client.post(f"/api/runs/{first}/stop")
    sse_events(client, first)


def test_unknown_run_404(client):
    assert client.get("/api/runs/nope/events").status_code == 404
    assert client.post("/api/runs/nope/stop").status_code == 404


def test_translator_maps_intervention_and_turns():
    t = Translator()
    t.translate({"type": "panel_start", "hop": 1, "question": "Q", "agents": [f"panel_agent_{i:02d}" for i in range(10)]})
    out = t.translate({"type": "manager_step", "node": "review", "decision": "intervene",
                       "verification": "Panel deadlocked", "directive": "Refocus"})
    assert out[0].type == "manager_intervention" and out[0].content == "Refocus" and out[0].hop == 1
    out = t.translate({"type": "agent_turn", "agent_id": "panel_agent_03", "round": 1, "stance": "S",
                       "argument": "A", "citations": [{"title": "T", "url": "https://x.org"}],
                       "confidence": 0.7, "shifted": True, "uncited": False})
    assert [e.type for e in out] == ["status", "agent_message", "status"]
    assert out[1].agent_label == "Panel 03" and out[1].shifted and out[0].status == "speaking" and out[2].status == "done"
