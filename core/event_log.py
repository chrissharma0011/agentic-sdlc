"""
event_log.py  —  the spine of the whole system.

Append-only, immutable events. State is computed from the log (event sourcing);
history is never deleted. A rolled-back attempt stays in history but its
artifact is dropped from the derived state.

DURABILITY: an EventLog can be given a `path`. When it is, every appended event
is immediately written to that JSONL file (one event per line, append-only), and
an existing file is replayed on construction. Because state is a fold over the
log, this yields crash-recovery for free: kill the process mid-run, restart with
the same path, and the run resumes exactly where it stopped. Without a path, the
log is in-memory only (unchanged legacy behavior).
"""

import json
import os
import threading
from dataclasses import dataclass, field, asdict
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
    def __init__(self, path: str | None = None):
        self._events: list[Event] = []
        self._path = path
        self._lock = threading.Lock()   # parallel nodes append concurrently
        if path and os.path.exists(path):
            self._replay(path)          # resume from a prior (possibly crashed) run

    def _replay(self, path: str) -> None:
        """Load events from disk into memory (crash recovery)."""
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                self._events.append(Event(**d))

    def append(self, event: Event) -> Event:
        with self._lock:
            self._events.append(event)
            if self._path:
                # Durable write: flush each event as it happens, not at the end.
                with open(self._path, "a") as f:
                    f.write(json.dumps(asdict(event)) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
        return event

    def all(self) -> list[Event]:
        return list(self._events)

    def for_stage(self, stage: str) -> list[Event]:
        return [e for e in self._events if e.stage == stage]

    def latest(self, kind: str) -> Event | None:
        matches = [e for e in self._events if e.kind == kind]
        return matches[-1] if matches else None

    def completed_stages(self) -> set[str]:
        """Stages that already passed (used to skip work on resume)."""
        return {e.stage for e in self._events if e.kind == "node_passed"}


def build_state(log: EventLog) -> dict:
    state = {"artifacts": {}, "history": [], "raw_requirement": ""}
    for e in log.all():
        state["history"].append(f"{e.ts}  [{e.stage}]  {e.kind}")

        if e.stage == "input" and e.kind == "artifact_written":
            state["raw_requirement"] = e.payload.get("raw", "")

        elif e.kind == "artifact_written":
            state["artifacts"][e.stage] = e.payload

        elif e.kind == "rollback_occurred":
            bad_stage = e.payload.get("rolled_back_node")
            state["artifacts"].pop(bad_stage, None)

    return state
