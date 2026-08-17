# Architecture

This document describes how the orchestrator is built, the standard approaches that were considered, the reasoning behind each choice (as decision records), and the system's known limitations.

---

## 1. What this system is, named precisely

The orchestrator is a **blackboard architecture with event sourcing**.

The blackboard pattern is a well-established architecture (originating in 1970s AI research, now widely revived for LLM agent systems) in which specialized agents never communicate directly. Instead, every agent reads from and writes to a single shared knowledge store — the *blackboard* — and a control component decides which agent acts next based on the board's current state.

Using the vocabulary the multi-agent field uses to classify orchestrators, this system is:

- **Orchestration model:** graph-based (a task DAG, generated per requirement)
- **State management:** event-sourced (append-only log; state is a projection of it)
- **Communication pattern:** shared memory / blackboard (agents share the log, they do not pass messages to each other)

### Component mapping

| Blackboard concept | In this system |
|---|---|
| Blackboard (shared knowledge store) | The append-only **event log** (`core/event_log.py`); working state is `build_state()` folded from it |
| Knowledge sources (specialist agents) | The **nodes** in `nodes/agents.py` — Requirement, Plan, Architect, Implement, Test, Verify, Document, Release, plus Context-Retrieval, Clarify, Patch-Implement, and the injected Repair node |
| Control shell (decides who acts next) | The **Controller** (`core/controller.py`) — deterministic code that walks the DAG and applies recovery |

A defining property: nodes do not call each other. The Test node does not receive a message from the Implement node; it reads the shared state. This is what avoids the "phone game" failure mode described in section 3.

---

## 2. Approaches considered

There are three standard ways to build agent orchestration, and this project deliberately chose the middle one.

**(1) Use a framework** — e.g. LangGraph (the 2026 de facto standard for multi-agent systems), CrewAI, the OpenAI Agents SDK. These provide graph state, checkpointing, and human-in-the-loop primitives out of the box.

**(2) Custom orchestration** — hand-roll a state machine over your own data structures. *(This project.)*

**(3) A plain DIY loop** — a single think-act-observe loop with no graph.

**Decision: custom orchestration, no framework.**

The core reason is the nature of the task: the assignment's central requirement is to *demonstrate the orchestration primitives themselves* — dependency graphs, entry/exit gates, retries, rollback, re-planning, human checkpoints, and audit-grade observability. Adopting a framework that supplies those primitives would obscure the very competencies being assessed. Building them directly also forces every design choice to be explicit and defensible rather than inherited.

There are engineering reasons too. Custom orchestration gives **blast-radius control**: because state is materialized to the append-only log between every step, a bad node output cannot corrupt the run — the failed attempt is simply excluded from the next projection. And for a bounded pipeline (~10 nodes, seconds-to-minutes runtime, small fan-out), a framework's abstraction cost does not pay back; frameworks earn their keep at hundreds of parallel branches or multi-day, crash-recoverable runs.

**The trade-off, stated honestly:** we write and own more code, and we do not get durable, months-long execution for free. If this system needed to fan out across hundreds of parallel tasks or survive multi-day runs with crash recovery, the right move would be a framework (LangGraph) or a durable executor (Temporal, AWS Step Functions) rather than extending this controller. That boundary is a deliberate scope line, not an oversight.

---

## 3. Why blackboard, not a linear chain

The most common multi-agent pattern is the **linear chain**: the orchestrator tells Agent A to do its work, A formats its output into a payload and passes it as a message to Agent B, and so on. This has a well-known failure mode — the "phone game": each handoff reformats and loses information, and error routing for a rigid sequence turns into hundreds of lines of brittle retry/branching glue.

The blackboard design avoids this. Every node writes its artifact to the shared log; every downstream node reads exactly what it needs from the current state. There is no message payload to garble, and recovery is uniform because the controller — not a chain of hand-offs — owns retries, rollback, and re-planning. This is also why the execution graph is *not* linear: nodes run when their dependencies are satisfied, some run in parallel (section 7), and the graph can mutate mid-run (section 6).

---

## 4. The governed node lifecycle

Every node runs through the same three-step lifecycle, defined once in `core/node.py` and identical for every agent:

```
1. ENTRY GATE   — are the preconditions on the blackboard met?
2. RUN          — do the work (this is the only place an LLM is called)
3. EXIT GATE    — does the output meet the acceptance criteria?
```

If either gate rejects, the node raises a `GateError`, no artifact is written, and the controller decides what happens next. This is the core governance idea: **LLM judgment is fenced inside `run()`, while the control flow around it is deterministic.** A node is never "just do the work" — it is always "check, work, check."

Acceptance criteria are defined by the Planner as data on each task (`acceptance` on the `Task`), so the plan defines the contract and the gate enforces it — spec-as-code.

---

## 5. The event log as the spine

`core/event_log.py` is an append-only list of immutable `Event` records. Working state is not stored anywhere; it is computed on demand by `build_state()`, which folds over the log:

- an `artifact_written` event adds that node's output to the state's artifacts
- a `rollback_occurred` event causes that node's artifact to be excluded from the projection — **without deleting any history**

This single primitive yields several requirements at once, rather than as separate subsystems:

- **Audit trail** — the log *is* the complete, ordered history of everything that happened
- **Rollback** — appending a rollback event, never deleting, keeps the record intact (important for traceability) while removing the bad artifact from the working state
- **Reliability metrics** — `core/metrics.py` folds the same log into `success_rate`, `retries`, `rollbacks`, `escalations`, `node_failures`, `node_passes`, `mttr_seconds`, and `latency_seconds`

Deriving state from an immutable log is the event-sourcing pattern; getting audit, rollback, and metrics from one decision is the payoff.

**Durability / crash recovery.** The log can be given a file path, in which case every event is flushed to `runs/<run_id>/events.jsonl` the moment it is appended, and an existing file is replayed on startup. Because state is a fold over the log, this yields crash recovery directly: if the process dies mid-run, re-invoking with the same run id replays the events, marks already-passed stages done, and resumes exactly where it stopped — no work is repeated. This is the concrete payoff of the event-sourcing decision: durable recovery is a property of the design, not a separate subsystem.

---

## 6. Dynamic task graphs and re-planning

**Per-requirement graphs.** The Planner (`core/planner.py`) classifies each requirement and emits a *different* DAG for each class:

- **Greenfield:** `requirement → plan → architect → (implement ∥ test) → verify → document → release`
- **Brownfield:** `requirement → context_retrieval → clarify → architect → approval → (implement ∥ test) → verify → document → release`
- **Ambiguous:** `requirement → clarify → approval → …` then routed to build-or-patch depending on whether an app already exists

The graphs are genuinely different structures, not the same pipeline with flags — brownfield adds codebase reasoning (`context_retrieval`) and a human approval gate before any change; ambiguous inserts a clarify step that resolves the vague spec before planning.

**Dynamic re-planning (graph mutation at runtime).** When the Verify node fails after its retry budget, the controller does not merely stop. It **mutates the graph**: it injects a new `repair` task, re-routes `verify` to depend on it, resets the affected nodes to pending, and loops back. The repair node regenerates the implementation using the recorded failure reason, and verification runs again. This is the "dynamically re-plan when upstream outputs change" capability — implemented as graph mutation, bounded by a replan budget so it cannot loop forever.

Note on acyclicity: the graph remains a DAG. "Looping back" is expressed as *inserting a new forward task and resetting downstream state*, not as a literal cycle — preserving the DAG invariant while achieving iterative repair.

---

## 7. Concurrency (fork-join)

Nodes that share a `parallel_group` — `implement` and `test`, which both depend only on `architect` — run concurrently on a thread pool and synchronize at their common dependant, `verify`. This is a fork-join pattern.

This is safe specifically *because* of the event-sourced design: the only shared write is an append to the log, and each node's state is materialized independently. There is no shared mutable object for concurrent nodes to corrupt. (Serial execution would also be correct; concurrency is an optimization the architecture permits cleanly.)

---

## 8. The contract chain

A recurring failure in multi-agent code generation is *drift*: the node that writes the code and the node that writes the tests are independent LLM calls, and they invent different interpretations of the same spec (one expects HTTP 307, the other 200; one returns `clicks`, the other `access_count`).

This system prevents drift with a shared contract:

1. The **Architect derives an API contract** (endpoints, methods, status codes, and exact response field names) as JSON from the requirement, validated by a schema gate.
2. **Implement** and **Test** both bind to that *same derived contract*, independently of each other's code.

They stay independent (real black-box testing) while agreeing on the spec (no drift). When they still occasionally diverge, the Verify node's real test execution catches it and the repair loop (section 6) converges the code toward the frozen tests. The contract makes success likely; verification makes failure safe.

---

## 9. Controlled autonomy (human-in-the-loop)

Humans own the high-impact decisions:

- **Clarify gate** — for brownfield/ambiguous, the system asks the human scenario-specific questions before proceeding.
- **Approval gate** — before modifying existing code (or committing to a resolved spec), the human sees the impact analysis and chooses `yes` / `no` / `revise`. On `revise`, the human's written feedback is honored in the resulting patch.
- **Escalation** — when automated retries *and* re-planning are exhausted, the controller assembles a decision package (LLM-generated diagnosis + full event lineage) and hands control to the human, who can approve a resume or halt. Approval **resumes** the run; it is not merely a stop button.

---

## 10. Guardrails

Policies in `core/policy.py` are enforced at gates as cross-cutting checks, not as steps a node could skip:

- `no_secrets_in_code` — rejects output containing apparent secrets
- `tests_must_pass_before_release` — the Release gate verifies, from the blackboard, that verification actually passed

Enforcing these at the gate level (rather than inside a node) is deliberate: a node can be routed around by a re-plan, but a gate check cannot.

---

## 11. Architecture decision records

Key decisions in Y-statement form (*in the context of… facing… we decided… to achieve… accepting…*).

**ADR-1 — Hand-rolled orchestration, no framework.**
In the context of a graded assignment whose core requirement is demonstrating orchestration primitives, facing the option of using LangGraph or a similar framework, we decided to build a custom state machine, to achieve full ownership and defensibility of every primitive (gates, retries, re-planning, audit), accepting that we write more code and forgo framework-provided durable execution.

**ADR-2 — Blackboard over linear chain.**
In the context of coordinating multiple LLM agents across an SDLC, facing the common linear-chain/message-passing pattern, we decided to use a blackboard (shared event log), to achieve uniform recovery and no information loss between steps, accepting that a shared store requires disciplined state derivation.

**ADR-3 — Event sourcing as the state model.**
In the context of needing audit trails, rollback, and metrics, facing the option of mutable state plus a separate logger, we decided to make state a projection of an append-only event log, to achieve all three from one primitive with full traceability (and, by persisting the log, crash recovery), accepting that current state must be recomputed by folding the log.

**ADR-4 — Deterministic control shell, LLM fenced in nodes.**
In the context of wanting reproducible, governable control flow, facing the option of an LLM-driven controller, we decided to keep the controller deterministic and confine LLM calls to node bodies, to achieve predictable orchestration and testable recovery logic, accepting that routing cannot itself be "reasoned about" by a model at runtime.

**ADR-5 — Agent-derived, schema-gated contract.**
In the context of preventing code/test drift, facing a choice between a hardcoded contract and free-form generation, we decided to have the Architect derive the contract from the spec behind a schema gate (with a validated reference fallback), to achieve a genuinely agent-derived source of truth without sacrificing reliability, accepting a small risk that a derived contract falls back to the reference when malformed.

---

## 12. Limitations & trade-offs

Deliberate scope lines for a prototype, each with an extension path:

- **Event log durability (implemented).** Events are flushed to `runs/<run_id>/events.jsonl` as they occur, and a crashed run resumes by replaying the log (skipping completed stages). Remaining edge: a crash *inside* a node — after its LLM call but before the event is written — causes that single node to re-run on resume (an idempotent retry, not data loss). Full exactly-once execution would need intra-node checkpointing, which is out of scope.
- **Keyword intent classifier.** Requirements are classified by keyword matching, which is brittle at the edges (e.g. "display…" reads as a build, not a change, unless phrased with a change verb). Extension: an LLM classifier; the keyword version is transparent and deterministic for the demo.
- **Naive secret scan.** The no-secrets guardrail is a substring check, not static analysis.
- **Single-project scope.** Changes target the current code on disk (like a git working tree), not a project selected by id. Extension: project-scoped storage keyed above the run id.
- **LLM non-determinism.** Generated code varies between runs. This is managed — not eliminated — by real test verification, bounded retries, dynamic re-planning, and human escalation. A run that fails and recovers (or escalates honestly) is the system working as designed, not a defect.
