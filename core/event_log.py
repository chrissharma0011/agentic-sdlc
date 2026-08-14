"""
event_log.py  —  the spine of the whole system.

Append-only, immutable events. State is computed from the log (event sourcing);
history is never deleted. A rolled-back attempt stays in history but its
artifact is dropped from the derived state.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Event:
    run_id: str
    stage: str
    kind: str
    payload: dict
    ts: str = field(default_factory=_now)


class EventLog:
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
    state = {"artifacts": {}, "history": [], "raw_requirement": ""}
    for e in log.all():
        state["history"].append(f"{e.ts}  [{e.stage}]  {e.kind}")

        if e.stage == "input" and e.kind == "artifact_written":
            # The raw requirement seeded at the start of the run.
            state["raw_requirement"] = e.payload.get("raw", "")

        elif e.kind == "artifact_written":
            state["artifacts"][e.stage] = e.payload

        elif e.kind == "rollback_occurred":
            bad_stage = e.payload.get("rolled_back_node")
            state["artifacts"].pop(bad_stage, None)

    return state
