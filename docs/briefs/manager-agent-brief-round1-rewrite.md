# Manager + Panel — Round-1 Debate Rewrite (Claude Code Prompt)

**Scope:** Update the existing `manager-agent` project so Round 1+ is a real cross-agent debate, not parallel restatements of research. Keep the manager brain, intake, planning, tools, and delegation intact. Change only the post-research debate protocol (and the panel prompts / validators that enforce it).

**Do not** rebuild the manager from scratch. **Do not** remove research, perspective shift, consensus rules, or early stop.

---

## Keep (do not break)

### Manager
- **Brain:** OpenAI GPT via `OPENAI_API_KEY` / `OPENAI_MODEL` (env only; never hardcode secrets).
- **Flow:** topic intake → sub-question planning → manager research/tools → panel brief → delegate to 10-agent panel → receive **per-round summaries only** (never full transcripts) → intervene only on drift/deadlock → synthesize one final answer.
- **LangGraph wiring:** existing manager graph + panel subgraph hooks (`panel_summaries`, `consensus`, intervention path).

### Panel (unchanged pieces)
1. **Research phase (before any debate round):** each of the 10 agents researches **independently** with its own tools. Agents must **not** see each other’s research notes during this phase.
2. **Perspective shift:** after Round 1 (or when echo is detected), force **Panel 03 and Panel 05** (or the configured pair) to argue **against** the majority position in good faith.
3. **Consensus rules:**
   - Need **≥ 8 of 10** agreement on the scoped answer (or an explicitly conditional treatment of unresolved ambiguities).
   - Every load-bearing claim needs a **traceable source**.
   - Minority / dissent must be **documented**, not overwritten by a vote.
4. **Early stop:** stop before max rounds when consensus criteria are met, sub-questions are answered or explicitly gapped, and no unresolved objection would materially change the conclusion. If ambiguity blocks a useful synthesis, stop and request user clarification.

---

## Change: Round 1+ must be a live debate

### Failure mode you are fixing
Today, Round 1 turns often restated each agent’s own research note with little engagement. **That is a failure.** Round 1+ must show agents reacting to each other.

### Required protocol after research completes

```
1. RESEARCH (keep as-is)
   - Fan out 10 independent research turns.
   - Collect structured research notes: claim, sources, confidence, agent_id.
   - Agents cannot see peers during research.

2. BROADCAST DIGEST (new — required before Round 1)
   - Manager (or panel orchestrator acting for the manager) builds a **research digest** that includes EVERY agent’s research note (or a faithful short form of each: agent_id, core claim, 1–3 key citations, confidence).
   - Broadcast that digest to **all 10 agents** as shared context for Round 1.
   - Digest is for the panel only; the manager still receives **summaries**, not full transcripts, after each debate round.

3. ROUND 1 (replace current prompt logic)
   Each agent’s Round 1 output MUST:
   (a) React to **at least two other agents’** specific claims and/or sources by name/id
       (quote or paraphrase the claim; cite which agent and which source you are answering).
   (b) Defend OR revise its own position with evidence (say explicitly: held / revised / abandoned).
   (c) Try to convince **at least one** named other agent (address them; say what they should accept and why).
   Hard forbid: restating the agent’s research note verbatim or near-verbatim.
   Hard fail: if Round 1 text is substantially the same as that agent’s research note → reject and regenerate.

4. ROUNDS 2–3 (same engagement rule)
   - Respond to **prior-round arguments**, not the original question alone.
   - Same (a)(b)(c) requirements, referencing Round r−1 turns (and the digest only as background).
   - Perspective-shifted agents (03/05) must still satisfy (a)(b)(c) while arguing the opposite side.

5. ENGAGEMENT TRACKING (per agent, per round) — store in panel state
   For each agent turn record:
   - `addressed_agents: list[str]`     # who they replied to
   - `agreements: list[str]`           # short notes of what they accepted
   - `disagreements: list[str]`        # short notes of what they contested
   - `evidence_cited: list[str]`       # urls/titles used this turn
   - `position_changed: bool`         # vs their previous stance / research note
   - `stance_delta: str`              # one-line: held | revised | abandoned + why

6. CONSENSUS GATE (stricter)
   Consensus may be declared only if:
   - ≥ 8/10 agree on the answer string (or conditional framing), AND
   - Final positions show **real engagement** (not parallel restatements):
     * Every surviving agent has, in at least one debate round, addressed ≥2 peers, AND
     * Round-1 similarity check against research notes failed for fewer than 2 agents after retries, AND
     * Minority views are documented in the round summary / consensus payload.
   If agents “agree” but never engaged, treat as **echo / invalid consensus** → run another round or force perspective shift, do not stop as success.
```

### Prompt contract (inject into each debate-round system/user message)

```
You are Panel {id}/10 in Round {r}.

You already wrote a private research note. Do NOT paste or lightly paraphrase that note.

You are given:
- RESEARCH_DIGEST: every agent’s research claim + key sources
- PRIOR_ROUND_ARGUMENTS: (empty in Round 1; full peer turns in Round 2+)

Your reply MUST:
1. Name at least two other agents and engage a specific claim or source from each.
2. State whether you HOLD, REVISE, or ABANDON your prior position, with evidence.
3. Explicitly try to persuade at least one named agent.
4. Keep citations on load-bearing claims.

Output JSON matching the debate turn schema (claim, addressed_agents, agreements,
disagreements, evidence_cited, position_changed, stance_delta, confidence, citations).
```

### Validator (implement and enforce)

Before accepting a debate turn:
1. **Similarity check** vs that agent’s research note (and vs its prior debate turn): if too similar (e.g. high token overlap / embedding similarity above threshold), reject with reason `restated_research` and regenerate once.
2. **Engagement check:** `len(addressed_agents) >= 2`, and those ids exist and are not self.
3. **Persuasion check:** at least one `addressed_agents` entry is framed as a convince attempt (prompt + optional light LLM judge).
4. On second failure, accept a degraded turn but flag `engagement_failed=true` so consensus gate can block early stop.

### Round summary → manager (still summaries only)

Each round summary handed to the manager must include:
- Clustered positions with vote counts / confidence
- Who moved (position_changed agents)
- Notable agreements/disagreements between named agents
- Key citations
- Whether engagement gate passed
- Dissent note

Never dump full transcripts into the manager context.

### Perspective shift (keep, but compatible with new rules)

After Round 1 summary:
- If majority forms, run perspective shift on Panel 03 and Panel 05 against that majority.
- Their Round 2 turns must still meet engagement rules while arguing the opposite side.

### Early stop / consensus (keep thresholds, add engagement)

- Max rounds unchanged (env-configurable).
- No-new-arguments stop still allowed, but only if engagement gates passed in the latest round.
- 8/10 consensus + documented minority + traceable sources + **engagement gate**.

---

## Implementation order for Claude Code

1. Locate panel debate prompts and round loop (`panel/` graph: research → debate_round → summarize → check_stop).
2. Add `build_research_digest()` and broadcast it into Round 1 agent context.
3. Replace Round 1+ agent prompts with the engagement contract above.
4. Add per-turn schema fields + validators (similarity, addressed_agents, position_changed).
5. Tighten consensus / early-stop to require the engagement gate.
6. Keep manager intake/plan/tools/delegation/summaries-only handoff unchanged.
7. Smoke test in demo or live:
   - Research notes differ per agent and are independent.
   - Digest lists all 10.
   - Round 1 turns name ≥2 peers and are not near-copies of research.
   - Round 2 responds to Round 1 arguments.
   - Perspective shift still fires on 03/05.
   - Consensus at 8/10 only when engagement gate passes.

### Done criteria

- [ ] Research phase still independent (no peer visibility)
- [ ] Research digest broadcast before Round 1
- [ ] Round 1+ forbids verbatim / near-verbatim research restatement
- [ ] Each debate turn addresses ≥2 other agents, defends/revises, tries to persuade ≥1
- [ ] Engagement tracking stored per agent per round
- [ ] Perspective shift 03/05 retained
- [ ] Consensus ≥8/10 + sources + documented dissent + engagement gate
- [ ] Manager still sees summaries only; GPT manager path unchanged
- [ ] Secrets still env-only

### Out of scope

- Redesigning the web UI chrome (unless a tiny status field for “engagement failed” is trivial)
- Replacing the manager tool set
- Changing panel size away from 10

---

*Paste this entire file to Claude Code as the Round-1 debate rewrite spec. Build exactly this change set; nothing more.*
