"""
scenarios/ambiguous.py  —  ambiguous scenario (vague requirement).
The system detects the request is vague, asks the human what it means
(Core Req 1), gets approval of the resolved spec, then builds it.
Run: python3 -m scenarios.ambiguous
"""

import os
import json
from run import run_pipeline
from core.event_log import build_state
from core.metrics import compute_metrics


REQUIREMENT = "Make the URL shortener more reliable"
RUN_ID = "ambiguous"


if __name__ == "__main__":
    print("=== AMBIGUOUS SCENARIO ===")
    print(f"Requirement: {REQUIREMENT}\n")
    print("(This request is vague on purpose. The system will ask what it means.)\n")

    log, graph, plan_artifact = run_pipeline(REQUIREMENT, RUN_ID)

    print(f"\nClassified as: {plan_artifact['classification']}")
    print(f"Graph tasks: {[t.name for t in graph.all()]}")
    for t in graph.all():
        print(f"  {t.name:16} -> {t.status}")

    state = build_state(log)
    clar = state["artifacts"].get("clarify", {}).get("clarifications", {})
    if clar:
        print("\n=== HOW THE AMBIGUITY WAS RESOLVED (Core Req 1) ===")
        for q, a in clar.items():
            print(f"  Q: {q}\n  A: {a}")

    os.makedirs("runs/ambiguous", exist_ok=True)
    with open("runs/ambiguous/events.jsonl", "w") as f:
        for e in log.all():
            f.write(json.dumps({"ts": e.ts, "stage": e.stage,
                                "kind": e.kind, "payload": e.payload}) + "\n")
    with open("runs/ambiguous/metrics.json", "w") as f:
        json.dump(compute_metrics(log), f, indent=2)
    print("\nSaved audit log to runs/ambiguous/")
