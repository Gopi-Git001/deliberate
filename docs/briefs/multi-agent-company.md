# Multi-Agent Company System

## 1. Idea

A multi-agent “company” that turns an open-ended topic into one vetted answer.

The user sends a topic to a **manager agent**. The manager plans the work and delegates it to a **panel of worker agents**. The panel debates the topic openly — bringing different sources and perspectives, challenging each other — until they reach consensus. They return one final answer to the manager.

The manager analyzes that answer, verifies it against the brief, and can intervene if the debate drifts off-course. Once satisfied, the manager delivers the result to the user.

The manager stays mostly quiet during healthy debate. Intervention is reserved for wrong direction, broken process, or failed consensus.

## 2. Workflow

1. **User → Manager** — User provides a topic (and optional constraints: depth, audience, deadline).
2. **Manager plans** — Manager clarifies the goal, breaks it into research angles, sets debate rules (max rounds, consensus criteria, early-stop conditions), and assigns the panel.
3. **Panel researches** — Each worker gathers sources and forms an initial position.
4. **Open debate rounds** — Workers argue, cite, and rebut in capped rounds. After each round, a short summary is produced (not a full transcript dump).
5. **Consensus** — When positions converge, or early-stop fires (agreement clear / max rounds hit), the panel emits one joint answer.
6. **Manager review** — Manager analyzes and fact-checks the answer. If the direction is wrong, the manager jumps in (reframe, reassign, or force another bounded round).
7. **Delivery** — Manager returns the final answer to the user, with optional confidence notes and key sources.

Hard stops: max debate rounds, token/cost budget, and hop limits on manager ↔ panel handoffs so loops cannot run forever.

## 3. Agentic Architecture

### (a) Manager agent

| Aspect | Choice |
| --- | --- |
| Role | Planner, delegator, verifier, user-facing synthesizer |
| Brain | GPT-6 Asra |
| Memory | Long-term memory + vector DB (cross-session context) |

**Tools**

- Web search
- Browser
- Code interpreter
- Document reader
- Memory + vector DB
- Academic search (Semantic Scholar / arXiv)
- Data analysis
- API connector
- Summarizer
- Fact-checker
- Planner

**Design notes**

- Pass **per-round summaries** to the manager, not full panel transcripts.
- Cap debate rounds and enable **early stop** when consensus is clear.
- Stay quiet unless the panel drifts, deadlocks, or violates the brief.
- Synthesize one user-facing answer; never forward raw multi-agent chatter.

### (b) Panel agents

| Aspect | Choice |
| --- | --- |
| Composition | Ten identical clones (same role template, divergent sources/perspectives in practice) |
| Brain | Claude models |
| Memory | Short-term only for the current debate — no full vector DB |

**Tools**

- Web search
- Citation tool
- Document reader
- Code runner
- Source-ranker
- Summarizer

**How the panel works**

Each agent brings different sources and angles. They challenge claims, rank evidence, and revise positions across capped rounds until **one** answer emerges. Diversity comes from retrieval and critique, not from inventing ten different “personalities” with overlapping god-tools.

---

## Pitfalls to avoid

- **God agents** — Do not give one agent every tool; tool-choice quality collapses past ~15 tools. Keep the manager broad and workers narrow.
- **Infinite handoff loops** — Cap manager ↔ panel hops; escalate or stop when the same handoff repeats.
- **Uncapped debate cost** — Tokens scale with agents × rounds × growing context. Always set max rounds, budgets, and early stop.
- **Dumping full worker transcripts** — Flooding the manager with raw chat burns tokens and confuses synthesis. Summarize each round.
- **Skipping observability** — Tag every span with `agent.name`, `agent.role`, and `round.index` so you can debug cost, loops, and drift.

---

## Free / low-cost API options

| Need | Option |
| --- | --- |
| Academic search | Semantic Scholar and arXiv — no API key required for basic use |
| Web search | Tavily (~1000 free searches/month); SerpAPI (~100 free) |
| Data analysis | Local Python, or E2B free tier for sandboxed code |

---

## Framework notes

| Framework | Best fit |
| --- | --- |
| **LangGraph** | Complex routing, durable state, checkpoints — preferred for this manager + capped debate loop |
| **CrewAI** | Fast role-based crews (`Process.hierarchical` + `manager_agent`) |
| **AutoGen SelectorGroupChat** | Conversational panels with explicit speaker control / debate rounds |
| **OpenAI Agents SDK** | Simple handoffs when you need a light orchestrator-worker path |

**Recommended shape for this design:** LangGraph (or equivalent StateGraph) for the outer manager loop and round caps; AutoGen-style group chat or an explicit debate subgraph for the panel; summaries-only handoffs back to the manager after each round.
