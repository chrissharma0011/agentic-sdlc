"""
event_log.py  —  the spine of the whole system.

Everything that happens in a run gets recorded here as one immutable Event.
We never edit or delete events; we only ever ADD to the end. That is what
"append-only" means, and it is the same idea a bank ledger uses.

Big idea (event sourcing): we do NOT keep a separate "current state" variable
that nodes overwrite. Instead, the log IS the truth, and the current state is
COMPUTED from the log whenever we need it (see build_state at the bottom).
That is why the audit trail and the metrics come for free later: they are just
different ways of reading this one list.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> str:
    # A timestamp as text, e.g. "2026-08-14T10:31:05.123456+00:00".
    # We use UTC so every event is on the same clock.
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Event:
    """
    One thing that happened. `frozen=True` makes it read-only: once an Event
    is created, none of its fields can be changed. That guarantee is what lets
    us trust the log as an audit record — history can't be quietly rewritten.
    """
    run_id: str          # which run this event belongs to
    stage: str           # which node produced it, e.g. "plan", "verify"
    kind: str            # what happened, e.g. "node_started", "artifact_written", "gate_failed"
    payload: dict        # the actual data: an artifact, a result, a failure reason
    ts: str = field(default_factory=_now)   # when it happened (filled in automatically)


class EventLog:
    """The append-only list, plus a few safe ways to read it."""

    def __init__(self):
        self._events: list[Event] = []      # the underscore means "private, don't touch from outside"

    def append(self, event: Event) -> Event:
        # The ONLY way to add history. No update, no delete — on purpose.
        self._events.append(event)
        return event

    def all(self) -> list[Event]:
        # Return a COPY so outside code can read the history but never mutate ours.
        return list(self._events)

    def for_stage(self, stage: str) -> list[Event]:
        # Every event a given node produced — useful for debugging one stage.
        return [e for e in self._events if e.stage == stage]

    def latest(self, kind: str) -> Event | None:
        # The most recent event of a kind, or None if it never happened.
        matches = [e for e in self._events if e.kind == kind]
        return matches[-1] if matches else None


def build_state(log: EventLog) -> dict:
    """
    Compute the CURRENT state by folding over the whole log, front to back.
    "Fold" just means: start empty, then walk every event and update as we go.

    This is the blackboard READ: any downstream node calls this to see the
    artifacts every upstream node has written so far — reading "downward"
    through the history, exactly like the diagram.
    """
    state = {"artifacts": {}, "history": []}
    for e in log.all():
        # Record a human-readable line for the audit trail.
        state["history"].append(f"{e.ts}  [{e.stage}]  {e.kind}")
        # If this event wrote an artifact, expose it under its stage name.
        if e.kind == "artifact_written":
            state["artifacts"][e.stage] = e.payload
    return state


if __name__ == "__main__":
    log = EventLog()
    run = "run-001"

    log.append(Event(run, "requirement", "node_started", {}))
    log.append(Event(run, "requirement", "artifact_written", {"spec": "shorten URLs, add redirect + click count"}))
    log.append(Event(run, "plan", "node_started", {}))
    log.append(Event(run, "plan", "artifact_written", {"tasks": ["build API", "add redirect", "add analytics"]}))

    print("=== THE LOG (append-only history) ===")
    for e in log.all():
        print(f"  {e.ts}  [{e.stage}]  {e.kind}  ->  {e.payload}")

    print("\n=== STATE DERIVED FROM THE LOG (the blackboard read) ===")
    state = build_state(log)
    print("  artifacts on the blackboard:")
    for stage, art in state["artifacts"].items():
        print(f"    - {stage}: {art}")
