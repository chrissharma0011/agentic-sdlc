"""
scenarios/greenfield.py  —  the greenfield scenario, as a deliverable.
Saves the code that ACTUALLY PASSED: the repaired version if Verify healed it,
otherwise the original. Run:  python3 -m scenarios.greenfield
"""

import os
import json
from run import run_pipeline
from core.event_log import build_state
from core.metrics import compute_metrics


REQUIREMENT = "Build a URL shortener with redirect and click counting"
RUN_ID = "greenfield"


def final_code(state):
    """The code that passed: repaired version if Verify healed it, else original."""
    repaired = state["artifacts"].get("verify", {}).get("repaired_code")
    if repaired:
        return repaired
    return state["artifacts"].get("implement", {}).get("code", "")


def save_artifacts(log, graph, plan_artifact):
    state = build_state(log)
    os.makedirs("runs/greenfield", exist_ok=True)

    code = final_code(state)
    tests = state["artifacts"].get("test", {}).get("tests", "")
    if code:
        with open("shortener/app.py", "w") as f:
            f.write(code)
    if tests:
        with open("shortener/test_app.py", "w") as f:
            f.write(tests)

    with open("runs/greenfield/events.jsonl", "w") as f:
        for e in log.all():
            f.write(json.dumps({"ts": e.ts, "run_id": e.run_id, "stage": e.stage,
                                "kind": e.kind, "payload": e.payload}) + "\n")
    with open("runs/greenfield/plan.json", "w") as f:
        json.dump(plan_artifact, f, indent=2)
    with open("runs/greenfield/metrics.json", "w") as f:
        json.dump(compute_metrics(log), f, indent=2)


if __name__ == "__main__":
    print("=== GREENFIELD SCENARIO ===")
    print(f"Requirement: {REQUIREMENT}\n")

    log, graph, plan_artifact = run_pipeline(REQUIREMENT, RUN_ID)

    print(f"Classified as: {plan_artifact['classification']}")
    for t in graph.all():
        print(f"  {t.name:16} -> {t.status}")

    # Report whether Verify had to self-heal.
    state = build_state(log)
    repairs = state["artifacts"].get("verify", {}).get("repairs_used", 0)
    if repairs:
        print(f"\nVerify self-healed the code in {repairs} repair attempt(s).")

    save_artifacts(log, graph, plan_artifact)
    print("Saved the passing code to shortener/app.py and audit log to runs/greenfield/")
