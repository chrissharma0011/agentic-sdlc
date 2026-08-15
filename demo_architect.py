"""Prove the real Architect node produces a genuine design through its gates."""
from core.event_log import EventLog, Event, build_state
from nodes.agents import ArchitectNode

log = EventLog()
run = "run-architect-test"

# Put a spec on the blackboard, like the requirement node would.
log.append(Event(run, "requirement", "artifact_written",
                 {"spec": "URL shortener: shorten a URL, redirect, count clicks"}))

state = build_state(log)
output = ArchitectNode().execute(state, log, run)

print("=== THE ARCHITECT'S DESIGN (real LLM output) ===\n")
print(output["design"])
