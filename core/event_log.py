"""
event_log.py  —  the spine of the whole system.

Everything that happens in a run gets recorded here as one immutable Event.
We never edit or delete events; we only ever ADD to the end. That is what
"append-only" means, and it is the same idea a bank ledger uses.

Event sourcing: we do NOT keep a separate "current state" variable that nodes
overwrite. The log IS the truth; current state is COMPUTED from the log
(build_state). Because we never delete, a rolled-back attempt stays in history
for audit — build_state simply ignores the artifact it produced.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Event:
    """One immutable thing that happened. frozen=True = cannot be edited."""
    run_id: str
    stage: str
    kind: str
    payload: dict
    ts: str = field(default_factory=_now)


class EventLog:
    """Append-only list, plus safe read helpers. No update, no delete."""

    def __init__(self):
        self._events: list[Event] = []

    def append(self, event: Event) -> Event:
        self._events.append(event)
        return event

    def all(self) -> list[Event]:
        return list(self._events)

    def for_stage(self, stage: str) -> list[Event]:
        return [e for e in self._events if e.stage == stage]

    def latest(self, kind: str) -> Event | None:
        matches = [e for e in self._events if e.kind == kind]
        return matches[-1] if matches else None


def build_state(log: EventLog) -> dict:
    """
    Compute current state by folding over the whole log, front to back.

    Key event-sourcing move: we NEVER delete history. When a node's attempt is
    rolled back, the controller appends a 'rollback_occurred' event naming that
    stage. Here, that tells us to DROP the artifact from that stage's failed
    attempt — the history remains, but the derived state ignores the bad work.
    """
    state = {"artifacts": {}, "history": []}
    for e in log.all():
        state["history"].append(f"{e.ts}  [{e.stage}]  {e.kind}")

        if e.kind == "artifact_written":
            state["artifacts"][e.stage] = e.payload

        elif e.kind == "rollback_occurred":
            # Forget the rolled-back stage's artifact (if any). History stays.
            bad_stage = e.payload.get("rolled_back_node")
            state["artifacts"].pop(bad_stage, None)

    return state


if __name__ == "__main__":
    log = EventLog()
    run = "run-001"
    log.append(Event(run, "requirement", "artifact_written", {"spec": "shorten URLs"}))
    log.append(Event(run, "plan", "artifact_written", {"tasks": ["api", "redirect"]}))
    # Simulate a rolled-back plan attempt: history keeps it, state drops it.
    log.append(Event(run, "plan", "rollback_occurred", {"rolled_back_node": "plan"}))

    print("=== FULL HISTORY (nothing deleted) ===")
    for e in log.all():
        print(f"  [{e.stage}]  {e.kind}  {e.payload}")

    print("\n=== DERIVED STATE (plan artifact correctly ignored) ===")
    state = build_state(log)
    print("  artifacts:", state["artifacts"])
