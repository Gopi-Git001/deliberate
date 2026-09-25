# Panel Agents (×10) — Claude Code / Codex Build Brief

**Scope:** Build the **10-agent debate panel** and its LangGraph debate cycle. Integrate with the existing **manager** via summary-only handoffs. Do **not** reimplement the manager’s full tool stack; call into manager hooks (`panel_summaries`, `consensus`) or a thin adapter.

**Prerequisite:** Manager scaffold/milestone exists (`manager-agent/` with `ManagerState` fields `panel_summaries`, `consensus`, and synthesize that can consume them).

---

## Role of the panel

Identical **GPT** worker clones that:

1. Receive a **topic** and a **sub-question** from the manager.
2. **Research** with worker tools and form positions.
3. **Debate in rounds**, exchanging arguments **with citations**.
4. After each round, emit a **short summary** for the manager (**never** the full transcript).
5. Stop when they reach **consensus**, or hit **max rounds**, or a **no-new-arguments** ceiling.
6. Return the **surviving conclusion** (+ confidence) to the manager.

The manager may **intervene** if the panel drifts (wrong direction, deadlock, echo chamber). Panel must accept an optional manager intervention message and re-anchor.

---

## Agent design

| Aspect | Spec |
| --- | --- |
| Count | **10** |
| Identity | **Identical clones** — same system prompt template, same tools, same model config |
| Diversity | Comes from **different retrieval results**, **critique**, and the **perspective shifter** — not from 10 different personalities or god-tool sets |
| Brain | **GPT** (OpenAI API; user will buy credits) |
| Memory | **Short-term only** for the current debate thread — **no vector DB**, no cross-session store |
| Naming | e.g. `panel_agent_00` … `panel_agent_09` (or one node invoked with `agent_id`) |

### Clone template (system prompt starter)

```
You are Panel Worker {id}/10 in a multi-agent debate.
Answer the manager’s sub-question on the shared topic.
Use tools to gather evidence. Cite sources. Challenge weak claims.
You share the same role as your siblings; your edge is better evidence and clearer reasoning.
Keep short-term notes only for this debate. Do not invent secrets or API keys.
When asked to shift perspective, argue the opposite side in good faith using evidence.
```

---

## Tools (panel only)

| Tool | Purpose |
| --- | --- |
| `web_search` | Find current web sources for the sub-question. |
| `citation` | Normalize and attach citations (title, url, quote/span) to claims. |
| `document_reader` | Read local/uploaded docs relevant to the debate. |
| `code_runner` | Run short sandboxed snippets for checks or light analysis. |
| `source_ranker` | Rank candidate sources by credibility / relevance. |
| `summarizer` | Compress an agent’s turn or a full round into a manager-safe summary. |
| `confidence_scorer` | Emit a calibrated confidence score (0–1 or low/med/high + rationale). |
| `perspective_shifter` | Force this agent to argue the **opposite** side of the current consensus/majority (anti-echo chamber). |

**Not in scope for panel:** manager vector memory, academic-search monopoly, API connector, planner, fact-checker-as-authority (manager owns final fact-check). Panel may still cite papers via web/docs if needed.

---

## Debate rules

1. **Open-ended** discussion until consensus — but always bounded by stop rules.
2. **Max-round ceiling** — e.g. `PANEL_MAX_ROUNDS=5` (env-configurable; default 3–5).
3. **No-new-arguments stop** — if a round adds no material new claims/citations vs prior round summary (heuristic or LLM judge), stop early.
4. **Consensus** — majority agreement on a single answer string, or unanimous after a settle vote; record dissent briefly in the round summary if any.
5. **Citations required** on substantive claims; uncited claims get challenged.
6. **Perspective shift** — at least once in the first half of the debate (or when echo detected), invoke `perspective_shifter` on 1–2 agents so someone argues the opposite side.
7. **Manager intervention** — if manager injects a drift correction, clear the next round’s agenda from that message; do not ignore it.

### Round protocol

```
For round r in 1..MAX:
  1. Each agent (or a subset per round) produces: claim + citations + confidence
  2. Agents critique peers (optional parallel then merge)
  3. Optional: perspective_shifter on designated agent(s)
  4. Round summarizer → append to panel_summaries (manager-facing)
  5. Check stop: consensus? OR max rounds? OR no-new-arguments?
Emit consensus + overall confidence → manager
```

---

## Mapping to the manager

| Direction | Payload |
| --- | --- |
| Manager → Panel | `topic`, `sub_question` (per agent or shared), optional `constraints`, optional `intervention` |
| Panel → Manager (each round) | **Summary only**: positions, key citations, disagreements, confidence — **not** full message logs |
| Panel → Manager (final) | `consensus` (single answer), `confidence`, optional short dissent note |
| Manager → Panel (optional) | Intervention: reframed question / “you drifted; re-anchor to X” |

**Contract with existing manager state**

- Append strings to `panel_summaries: list[str]`
- Set `consensus: str` when done
- Manager `synthesize` / review nodes already expect these fields

Never stream raw panel `messages` into the manager context.

---

## LangGraph setup (debate cycle)

Suggested package: `src/manager_agent/panel/` (or `src/panel_agent/`) living beside the manager.

### Panel state (`PanelState`)

```text
topic: str
sub_question: str
intervention: str                 # optional manager correction
round_index: int
max_rounds: int
agent_outputs: list[dict]         # per-round structured claims (internal)
round_messages: list              # short-term only; wipe or omit from manager
panel_summaries: list[str]        # manager-facing
prior_summary: str                # for no-new-arguments compare
consensus: str
confidence: str | float
stop_reason: literal["consensus","max_rounds","no_new_arguments","intervention_abort"]
```

### Graph shape

```
START
  → panel_intake          # load topic/sub_question/intervention; reset short-term memory
  → research_fanout       # 10 clones gather sources (parallel if possible)
  → debate_round          # argue / cite / critique / optional perspective_shifter
  → summarize_round       # manager-safe summary → panel_summaries
  → check_stop            # consensus | max_rounds | no_new_arguments
       ├─ (continue) → debate_round
       └─ (stop) → settle_consensus → END
```

Wire into manager as a **subgraph node** `run_panel` between manager `plan`/`delegating` and `reviewing`/`synthesize`:

```
manager: … → delegate_to_panel → run_panel → manager_review → synthesize
```

### Parallelism

- Prefer fan-out for research turns (asyncio / LangGraph Send API).
- Debate round may be sequential critique or parallel draft-then-merge; document the choice in README.

---

## Env handling (Claude keys)

```bash
# Panel / Anthropic
OPENAI_API_KEY=
OPENAI_MODEL=GPT-6-Luna          # or user-chosen Claude model

# Debate controls
PANEL_MAX_ROUNDS=5
PANEL_NO_NEW_ARGS_THRESHOLD=0.15          # optional similarity threshold
PANEL_PERSPECTIVE_SHIFT_ROUND=2           # force opposite-side round

# Shared search (if panel web_search uses Tavily)
TAVILY_API_KEY=

# Optional sandbox for code_runner
E2B_API_KEY=
```

Rules:

- Load via `.env` + settings object; **never hardcode** keys.
- Extend `.env.example`; keep `.env` gitignored.
- Fail fast with a clear error if `ANTHROPIC_API_KEY` missing when the panel runs.
- Manager keeps using `OPENAI_API_KEY`; panel uses `ANTHROPIC_API_KEY` — both may coexist.

---

## Step-by-step build order

1. **Package + settings** — `panel/` module; Anthropic + debate env settings; `.env.example` updated.
2. **PanelState + clone factory** — one factory builds agent `0..9` with identical tools/prompt; only `id` differs.
3. **Implement panel tools** — `web_search`, `citation`, `document_reader`, `code_runner`, `source_ranker`, `summarizer`, `confidence_scorer`, `perspective_shifter` (shifter = prompt+tool that rewrites the agent’s stance to the opposite side with evidence).
4. **Short-term memory** — in-graph state / message list only; explicitly **no** Chroma/vector store on panel.
5. **research_fanout node** — each clone produces initial brief + citations.
6. **debate_round node** — exchange arguments; enforce citation habit; call perspective shifter on schedule/echo.
7. **summarize_round node** — write manager-facing summary; store `prior_summary`.
8. **check_stop** — consensus detector + max rounds + no-new-arguments comparator.
9. **settle_consensus** — single `consensus` string + confidence.
10. **Manager integration** — `delegate_to_panel` passes `topic`/`sub_question`; map outputs into `panel_summaries` + `consensus`; ensure manager synthesize uses them.
11. **Intervention path** — accept manager `intervention` string; next round re-anchors.
12. **Smoke test** — one topic, ≥2 rounds, summaries shorter than raw logs, stop rule fires, consensus returned.
13. **README** — how to run panel solo + via manager; env vars; stop rules.

### Done criteria — panel package

- [ ] Exactly **10 identical clones** (same tools/prompt template; distinct ids only)
- [ ] Brain = **GPT** via `OPENAI_API_KEY` / `OPENAI_MODEL`
- [ ] All listed panel tools registered, including **perspective_shifter**
- [ ] **Short-term memory only** — no panel vector DB
- [ ] Debate stops on **consensus** OR **max rounds** OR **no-new-arguments**
- [ ] Each round produces a **summary**; manager never receives full transcripts by default
- [ ] Final **consensus** (+ confidence) written for the manager
- [ ] Manager **intervention** can re-anchor a subsequent round
- [ ] Keys only from env; smoke test documented and passing with keys set

### Done criteria — whole panel system (manager + panel)

- [ ] User topic → manager plan → panel debate → round summaries → consensus → manager review → user final answer
- [ ] Summary-only handoff enforced at the boundary
- [ ] Drift intervention path works end-to-end
- [ ] Cost/loop guards: `PANEL_MAX_ROUNDS`, tool/loop caps, no infinite handoff
- [ ] Observability: log/tag `agent.id`, `round_index`, `stop_reason`

### Out of scope

- Replacing the manager brain or manager tools  
- Long-term panel memory / shared vector DB  
- More than 10 workers or unique per-agent personas  
- Shipping without stop rules  

---

## Suggested file layout

```
src/manager_agent/
  panel/
    __init__.py
    config.py              # Anthropic + debate settings
    state.py               # PanelState
    clones.py              # factory for 10 identical agents
    tools/
      web_search.py
      citation.py
      document_reader.py
      code_runner.py
      source_ranker.py
      summarizer.py
      confidence_scorer.py
      perspective_shifter.py
    nodes.py               # intake, research, debate, summarize, stop, settle
    graph.py               # compile panel subgraph
  graph.py                 # manager graph calls panel subgraph
```

---

## Copy-paste integration checklist for Codex

```
[ ] Read manager state.py — confirm panel_summaries + consensus fields
[ ] Add panel settings (ANTHROPIC_*, PANEL_*)
[ ] Implement identical clone factory ×10
[ ] Implement 8 panel tools (incl. perspective_shifter)
[ ] Build debate graph with max-round + no-new-arguments stops
[ ] Summaries → panel_summaries each round; never dump transcripts to manager
[ ] settle → consensus; wire manager_review / synthesize
[ ] Smoke test + README
```

---

*Feed this file to Claude Code / Codex as the sole spec for the panel milestone. Build manager first if not done; then this brief.*
