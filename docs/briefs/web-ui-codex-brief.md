# Web UI — Claude Code / Codex Build Brief (v2 — Polished Design)

**Scope:** Build a **polished, modern web UI** for Gopi’s multi-agent company: submit a topic, watch a **live color-coded debate**, see round summaries and manager interventions, and land on a clear **final conclusion**. Wire to the existing **LangGraph manager + panel** via **FastAPI + SSE**. Do not rebuild agent logic in the frontend.

**Prerequisites:** Manager + panel graphs (or stubs emitting the same event shapes). Extend `manager-agent/`.

**Stack**

| Layer | Choice |
| --- | --- |
| Backend | **FastAPI** + **SSE** (unchanged) |
| Frontend (preferred) | **React (Vite)** + CSS modules or Tailwind |
| Frontend (acceptable MVP) | Plain **HTML/CSS/JS** with a small component library (e.g. Shoelace) — only if React slows delivery |
| Icons | Lucide (or similar) |

**Default to React + Vite** for the polished UI unless blocked; keep the same SSE event contract either way.

---

## Product requirements

1. **Topic input at top** — Prominent submit bar (topic + optional constraints) + Submit / Stop.
2. **Live debate stream (center)** — Smooth auto-scroll chat board with:
   - Panel agent messages (badges labeled `Panel 00`…`Panel 09`)
   - Manager messages (badge `Manager`)
   - Manager **interventions** (amber styling, distinct card)
   - **Round dividers** + **round summary** cards
   - Typing / thinking indicators while an agent is active
3. **Final conclusion panel (bottom)** — Pinned/sticky highlight when `final_answer` arrives (not just another bubble).
4. **Sidebar** — Manager + all 10 panel agents with live status: `idle` | `thinking` | `speaking` | `done` | `error`.
5. **Responsive** — Works on desktop and usable on tablet/narrow widths (sidebar collapses to drawer).
6. **Loading states** — Run-level skeleton/spinner on start; per-agent pulse when thinking.
7. **Server-side secrets only** — No API keys in the browser.

---

## Color palette (dark theme)

Use CSS variables. Exact hex may be tuned ± slightly, but **roles must stay recognizable**.

### Core surfaces

| Token | Hex | Use |
| --- | --- | --- |
| `--bg` | `#0B0F14` | App background |
| `--bg-elevated` | `#121821` | Sidebar, cards, input chrome |
| `--bg-stream` | `#0E141C` | Main stream panel |
| `--border` | `#1E2A38` | Dividers, card outlines |
| `--text` | `#E7EEF7` | Primary text |
| `--text-muted` | `#8B9BB0` | Secondary / timestamps |
| `--accent` | `#3B82F6` | Primary buttons, focus rings |

### Role colors

| Role | Token | Hex | Use |
| --- | --- | --- | --- |
| Manager | `--manager` | `#3B82F6` (blue) | Manager badge, avatar ring, sidebar dot |
| Panel (base) | `--panel` | `#14B8A6` (teal) | Default panel accent |
| Intervention | `--intervene` | `#F59E0B` (amber) | Manager intervention cards |
| Round summary | `--summary` | `#A78BFA` (violet) | Round divider + summary cards |
| Final answer | `--final` | `#22C55E` (green) | Conclusion panel border/glow |
| Error | `--error` | `#EF4444` | Errors / failed status |
| Thinking | `--thinking` | `#64748B` | Idle→thinking pulse |

### Per-agent panel accents (consistent palette)

Assign each clone a stable accent (badge left border / avatar). Keep teal family so the board stays cohesive:

| Agent | Accent |
| --- | --- |
| Panel 00 | `#14B8A6` |
| Panel 01 | `#2DD4BF` |
| Panel 02 | `#06B6D4` |
| Panel 03 | `#22D3EE` |
| Panel 04 | `#38BDF8` |
| Panel 05 | `#60A5FA` |
| Panel 06 | `#818CF8` |
| Panel 07 | `#34D399` |
| Panel 08 | `#4ADE80` |
| Panel 09 | `#2DD4BF` |

Manager always uses `--manager` blue; never reuse panel accents for the manager.

### Bubble / card rules

- Dark elevated card (`--bg-elevated`) with 1px `--border`
- Left accent bar = role/agent color
- Badge pill: agent label on tinted background (`color-mix` or ~15% opacity fill)
- Intervention: amber border + amber badge + icon (e.g. alert-triangle)
- Round summary: violet dashed divider above + summary card
- Final panel: green border, stronger shadow/glow, sticky bottom

---

## Layout

```
┌────────────────────────────────────────────────────────────┐
│ TOP: Topic input  [____________]  [constraints] [Submit]   │
│      [Stop]   run status chip                              │
├──────────────┬─────────────────────────────────────────────┤
│ SIDEBAR      │  CENTER: Live debate stream                 │
│ Manager ●    │  ── Round 1 ────────────────────────────    │
│ Panel 00 ●   │  [badge] message bubble                     │
│ Panel 01 ●   │  [Round 1 summary card]                     │
│ …            │  [amber] Manager intervention               │
│ Panel 09 ●   │  ── Round 2 ────────────────────────────    │
│              │  …                                          │
│              │  (typing indicator)                         │
├──────────────┴─────────────────────────────────────────────┤
│ BOTTOM: Final conclusion panel (empty until final_answer)  │
└────────────────────────────────────────────────────────────┘
```

**Responsive**

- `≥1024px`: sidebar sticky left (~240px)
- `<1024px`: sidebar becomes overlay drawer; hamburger toggles agents
- Stream always full width of remaining space; conclusion panel full width

**Scroll**

- Smooth auto-scroll to bottom on new events
- If user scrolls up > threshold, pause auto-scroll and show “Jump to latest” chip
- Resume auto-scroll on jump or when user returns to bottom

---

## Component list (React)

| Component | Responsibility |
| --- | --- |
| `AppShell` | Grid: top bar, sidebar, stream, conclusion |
| `TopicBar` | Topic + constraints inputs, Submit, Stop, run status |
| `AgentSidebar` | List of Manager + Panel 00–09 with status dots |
| `AgentStatusItem` | Avatar/initials, label, status (`thinking` pulse, etc.) |
| `DebateStream` | Scroll container; maps events → components |
| `RoundDivider` | “Round N” horizontal rule |
| `MessageBubble` | Card + badge + timestamp + content |
| `InterventionCard` | Amber variant of message (manager drift correction) |
| `RoundSummaryCard` | Violet summary handoff card |
| `TypingIndicator` | Animated dots + “Panel 03 is thinking…” |
| `ConclusionPanel` | Sticky final answer; empty placeholder state |
| `JumpToLatestButton` | Shown when auto-scroll paused |
| `ErrorToast` | `error` events |
| `useEventSource(runId)` | SSE hook → typed events |
| `useRunController` | POST run, stop, connection lifecycle |

Plain HTML/JS equivalent: same component boundaries as ES modules / custom elements.

---

## Event model (backend → frontend)

SSE JSON events (unchanged contract from v1, plus status granularity):

| `type` | Fields |
| --- | --- |
| `run_started` | `run_id`, `topic` |
| `agent_message` | `run_id`, `agent_id`, `agent_label`, `role` (`manager`\|`panel`\|`system`), `content`, `round_index?`, `ts` |
| `manager_intervention` | `run_id`, `content`, `round_index?`, `ts` |
| `round_summary` | `run_id`, `round_index`, `summary`, `ts` |
| `consensus` | `run_id`, `consensus`, `confidence?`, `stop_reason?` |
| `final_answer` | `run_id`, `content`, `ts` |
| `status` | `run_id`, `agent_id?`, `status` (`idle`\|`thinking`\|`speaking`\|`done`\|`error`) |
| `error` | `run_id`, `message` |
| `run_finished` | `run_id` |

**Render map**

| Event | UI |
| --- | --- |
| `agent_message` | `MessageBubble` (blue vs teal accents by role/agent) |
| `manager_intervention` | `InterventionCard` (amber) |
| `round_summary` | `RoundDivider` + `RoundSummaryCard` |
| `status` | Sidebar + optional `TypingIndicator` when `thinking`/`speaking` |
| `final_answer` | `ConclusionPanel` |
| `consensus` | Optional compact chip above conclusion (or merge into conclusion meta) |

**Manager LLM boundary:** UI may show per-agent lines for the live board; manager context still gets **summaries only**.

---

## Wiring into LangGraph (FastAPI + SSE)

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/runs` | `{ topic, constraints? }` → `{ run_id }` |
| `GET` | `/api/runs/{run_id}/events` | SSE typed events |
| `POST` | `/api/runs/{run_id}/stop` | Cooperative cancel |
| `GET` | `/api/health` | Liveness |
| `GET` | `/` | Serve React build or `index.html` |

Runner wraps `build_manager_graph()` / panel subgraph; nodes `emit()` into an async queue. CORS only as needed for Vite dev (`localhost:5173` → API).

---

## Project structure

```
manager-agent/
  src/manager_agent/
    ui/
      app.py                 # FastAPI: API + static/SPA mount
      runner.py
      events.py
      static/                # if plain HTML MVP
        index.html
        styles.css           # CSS variables = palette
        app.js
  web/                       # if React (preferred)
    package.json
    vite.config.ts
    index.html
    src/
      main.tsx
      styles.css             # palette tokens
      App.tsx
      components/            # list above
      hooks/useEventSource.ts
      hooks/useRunController.ts
      lib/colors.ts          # agent_id → accent
      lib/types.ts           # event types
  requirements.txt           # fastapi, uvicorn[standard]
  README.md
```

Production: build Vite → `web/dist`, mount from FastAPI. Dev: Vite proxy `/api` to uvicorn.

---

## Env

```bash
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
TAVILY_API_KEY=
UI_HOST=127.0.0.1
UI_PORT=8000
```

Browser never receives these keys.

---

## Step-by-step build order

1. **Palette + tokens** — CSS variables file; document role/agent colors.
2. **Event schema** — pydantic/`types.ts` aligned.
3. **Runner + FastAPI SSE** — `POST /runs`, `GET .../events`, stop, health (stub emitters OK first).
4. **AppShell layout** — top topic bar, sidebar, stream, conclusion placeholder (no data).
5. **Presentational components** — `MessageBubble`, `InterventionCard`, `RoundSummaryCard`, `RoundDivider`, `TypingIndicator`, `AgentStatusItem` with correct colors.
6. **TopicBar + useRunController** — start/stop run.
7. **useEventSource + DebateStream** — render live events; smooth scroll + jump-to-latest.
8. **Sidebar status wiring** — `thinking` / `speaking` / `done` + typing indicator.
9. **ConclusionPanel** — sticky final answer on `final_answer`.
10. **Instrument graph emits** — manager/panel/summary/intervention/status.
11. **Responsive pass** — drawer sidebar, touch-friendly controls.
12. **Loading / empty / error states** — skeletons, empty stream copy, toasts.
13. **README** — palette note, run instructions (API + web), screenshot optional.
14. **Smoke test** — one topic shows labeled colored bubbles, round divider/summary, intervention style (if emitted), final green conclusion panel.

### Done criteria — design / frontend

- [ ] Dark theme with documented CSS variables
- [ ] Manager = blue; interventions = amber; summaries = violet; final = green; panels = teal palette
- [ ] Message **cards/bubbles** with **name badges**
- [ ] Topic input **at top**; stream **center**; conclusion **at bottom**; agent sidebar with statuses
- [ ] Round **dividers** + distinct summary cards
- [ ] Typing/thinking indicators + run loading state
- [ ] Smooth scrolling with jump-to-latest when paused
- [ ] Responsive (sidebar collapses on narrow screens)
- [ ] React+Vite **or** justified plain HTML/JS MVP using the same components/palette

### Done criteria — integration

- [ ] FastAPI + SSE backend intact
- [ ] Submit runs existing LangGraph path (no fake second orchestrator)
- [ ] Labeled Panel 00–09 + Manager in stream and sidebar
- [ ] Secrets server-side only
- [ ] Smoke test + README

### Out of scope

- Auth / multi-user  
- Mobile native apps  
- Prompt editing UI  
- Replacing LangGraph with client-side agents  

---

## Run commands (target)

```bash
# API
cd manager-agent
source .venv/bin/activate
pip install fastapi 'uvicorn[standard]'
export PYTHONPATH=src
uvicorn manager_agent.ui.app:app --host 127.0.0.1 --port 8000 --reload

# Web (React)
cd web
npm install
npm run dev
# open Vite URL; proxy /api → :8000
```

---

## Copy-paste checklist for Codex

```
[ ] Apply dark palette CSS variables (manager blue, panel teals, amber intervention, violet summary, green final)
[ ] Build AppShell: TopicBar | AgentSidebar | DebateStream | ConclusionPanel
[ ] Components: bubbles, badges, round divider, summary card, intervention card, typing indicator
[ ] FastAPI + SSE runner wired to LangGraph
[ ] Status continuum: idle → thinking → speaking → done
[ ] Responsive sidebar drawer
[ ] Smoke test live topic end-to-end
[ ] README with palette + run steps
```

---

*v2 brief — feed this file to Claude Code / Codex as the sole spec for the polished web UI milestone. Replaces the flatter v1 UI guidance; event/API contract stays compatible.*
