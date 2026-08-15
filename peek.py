"""Peek at the actual artifacts the last run produced."""
from run import run_pipeline
from core.event_log import build_state

log, graph, plan_artifact = run_pipeline(
    "Build a URL shortener with redirect and click counting", "run-peek")
state = build_state(log)

print("=== GENERATED CODE (app.py) ===\n")
print(state["artifacts"].get("implement", {}).get("code", "no code"))
print("\n=== GENERATED TESTS ===\n")
print(state["artifacts"].get("test", {}).get("tests", "no tests"))
