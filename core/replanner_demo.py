"""Throwaway demo of the escalation package. Not part of the real system."""
from core.event_log import EventLog, Event
from core.replanner import build_escalation

log = EventLog()
run = "run-001"
# Simulate a verify node that failed its exit gate a few times.
log.append(Event(run, "verify", "node_started", {}))
log.append(Event(run, "verify", "gate_failed", {"gate": "exit", "reason": "1 test failing"}))

pkg = build_escalation("verify", "exit", "1 test failing", attempts=3, log=log)

print("=== ESCALATION PACKAGE (what the human would see) ===")
for k, v in pkg.items():
    print(f"{k}: {v}")
