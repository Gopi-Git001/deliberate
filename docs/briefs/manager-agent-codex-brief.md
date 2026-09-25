# Manager Agent — Claude Code / Codex Build Brief

**Scope:** Build the **manager agent only**. Do not implement panel workers yet. Leave clear hooks for a future 10-agent panel.

**Existing scaffold (optional starting point):** `manager-agent/` — LangGraph package with placeholder tools, `.env.example`, and graph `intake → plan → agent ⇄ tools → synthesize`. Prefer extending this scaffold over rewriting from scratch unless you have a strong reason.

---

## Role

You are building a **manager agent** that:

1. Takes a **user topic** (and optional constraints).
2. **Plans** deep research and a future panel debate (rules only — panel not built yet).
3. Uses tools to **research, summarize, and fact-check**.
4. Will later **supervise** a 10-agent panel debate (hook only: accept `panel_summaries` + `consensus`).
5. **Intervenes only when the panel drifts** (wrong direction, deadlock, broken process) — stays quiet during healthy debate.
6. **Returns one final answer** to the user.

Handoff rule (design now, enforce later): prefer **per-round summaries**, never full panel transcripts.

---

## Brain

| Item | Value |
| --- | --- |
| Model provider | **OpenAI GPT** |
| Config | `OPENAI_API_KEY`, `OPENAI_MODEL` (default e.g. `gpt-4o`) via env |
| Pattern | LangGraph + tool-calling (ReAct-style loop) |

---

## Tools (11) — one-line purpose each

| Tool | Purpose |
| --- | --- |
| `web_search` | Search the live web (Tavily) for current sources. |
| `browser` | Open a URL and extract page content for deeper reading. |
| `code_interpreter` | Run short sandboxed code for checks or transforms. |
| `document_reader` | Read local/uploaded docs (txt, md, pdf, etc.). |
| `memory` (store + query) | Persist and retrieve long-term context via vector DB. |
| `academic_search` | Find papers on Semantic Scholar / arXiv. |
| `data_analysis` | Profile and analyze CSV/JSON datasets. |
| `api_connector` | Call external HTTP APIs using secrets from env vars. |
| `summarizer` | Compress long text into handoff-safe summaries. |
| `fact_checker` | Label claims supported / disputed / unverifiable. |
| `planner` | Produce a structured research + oversight plan before acting. |

Wire real backends behind `@tool` functions. Stubs that return clear `[placeholder]` messages are OK until keys/backends exist.

---

## Secrets / `.env`

- **Never hardcode** API keys in source, prompts, or git.
- Load via `python-dotenv` + `pydantic-settings` (or equivalent).
- Ship `.env.example` only; keep `.env` gitignored.

Minimum `.env.example`:

```bash
OPENAI_API_KEY=
OPENAI_MODEL=gpt-6 
TAVILY_API_KEY=
BROWSER_API_KEY=
E2B_API_KEY=
CHROMA_PERSIST_DIR=./data/chroma
```

Notes:

- Semantic Scholar / arXiv: no key for basic academic search.
- `api_connector` must take an **env var name** for auth tokens, not a raw secret string from the model.

---

## LangGraph state machine

```
START → intake → plan → agent ⇄ tools → synthesize → END
```

| Node | Job |
| --- | --- |
| `intake` | Normalize topic into state; init empty `panel_summaries`, `consensus`, etc. |
| `plan` | Call planner (tool or prompt); store `plan`; set phase to ready-for-tools. |
| `agent` | GPT step with tools bound; may request tool calls. |
| `tools` | Execute tool calls (`ToolNode`); return results to `agent`. |
| `synthesize` | Produce `final_answer` from plan + tool results + optional panel fields. |

**Suggested state fields**

- `messages`, `topic`, `plan`
- `panel_summaries: list[str]` (hook — unused until panel exists)
- `consensus: str` (hook)
- `verification`, `final_answer`
- `phase`, `round_index`, `tool_scratch`

**Guards**

- Cap tool-loop iterations (e.g. `manager_max_tool_steps`).
- Conditional edge: if tool calls remain and under cap → `tools`, else → `synthesize`.

**CLI**

```bash
PYTHONPATH=src python -m manager_agent.main "your topic here"
```

Print `final_answer` clearly.

---

## Step-by-step build order (for Claude Code / Codex)

Execute in order. Do not skip ahead to panel agents.

1. **Confirm scaffold** — Ensure package layout under `src/manager_agent/` with `config`, `state`, `graph`, `nodes`, `tools`, `.env.example`, `.gitignore`, `requirements.txt` / `pyproject.toml`.
2. **Lock config** — Implement settings loader; fail fast with a clear error if `OPENAI_API_KEY` missing when invoking the LLM.
3. **Freeze state schema** — `ManagerState` with panel hooks present but unused.
4. **Implement tools (thin → real)**  
   - First: `planner`, `summarizer`, `fact_checker`, `web_search` (Tavily), `academic_search`, `document_reader`.  
   - Then: `data_analysis`, `api_connector`.  
   - Last: `browser`, `code_interpreter`, `memory` (stubs OK if backends missing).
5. **Wire tool registry** — Single `MANAGER_TOOLS` list imported by the agent node / `ToolNode`.
6. **Build graph** — `intake → plan → agent ⇄ tools → synthesize` with iteration cap.
7. **System prompt** — Manager persona: plan deeply, use tools, prefer summaries, stay quiet unless drift (panel later), deliver one user-facing answer.
8. **CLI + README** — One-command run; document required env vars.
9. **Smoke test** — With keys set, run one topic; confirm plan runs, ≥1 tool path works, `final_answer` non-empty.
10. **Panel seam (no implementation)** — Document in README: next PR adds panel subgraph writing `panel_summaries` / `consensus` before `synthesize`. Do **not** build the 10 clones in this brief.

### Done criteria

- [ ] Keys only from env / `.env`
- [ ] All 11 tools registered (live or honest placeholders)
- [ ] Graph matches intake → plan → tool loop → synthesize
- [ ] CLI returns a final answer for a sample topic
- [ ] No panel worker code; hooks only

### Out of scope (this brief)

- 10 Claude panel clones  
- Debate rounds / consensus voting  
- Perspective shifter / confidence scorer on workers  

---

## Copy-paste system prompt (starter)

```
You are the manager agent. Given a user topic, plan deep research, use tools to gather and verify evidence, and produce one clear final answer.
You will later supervise a 10-agent panel: you will receive round summaries and a consensus, not full transcripts. Intervene only if debate drifts.
Until the panel exists, do the best solo research and synthesis you can. Prefer citations. Do not invent API keys or secrets.
```

---

*Feed this file to Claude Code / Codex as the sole spec for the manager-first milestone.*
