"""
scenarios/brownfield.py  —  brownfield scenario (change existing code).
Reads the existing shortener, asks change-risk questions, requires approval
before modifying, then implements + verifies. Run: python3 -m scenarios.brownfield
"""

import os
import json
from run import run_pipeline
from core.event_log import build_state
from core.metrics import compute_metrics


REQUIREMENT = "Add a stats reset endpoint to the existing URL shortener"
RUN_ID = "brownfield"


if __name__ == "__main__":
    print("=== BROWNFIELD SCENARIO ===")
    print(f"Requirement: {REQUIREMENT}\n")

    if not os.path.exists("shortener/app.py"):
        print("No existing shortener. Run greenfield first: python3 -m scenarios.greenfield")
        raise SystemExit(1)

    log, graph, plan_artifact = run_pipeline(REQUIREMENT, RUN_ID)

    print(f"\nClassified as: {plan_artifact['classification']}")
    print(f"Graph tasks: {[t.name for t in graph.all()]}")
    for t in graph.all():
        print(f"  {t.name:18} -> {t.status}")

    state = build_state(log)
    impact = state["artifacts"].get("context_retrieval", {}).get("impacted", "")
    if impact:
        print("\n=== IMPACT ANALYSIS (Core Req 3) ===")
        print(impact)

    os.makedirs("runs/brownfield", exist_ok=True)
    with open("runs/brownfield/events.jsonl", "w") as f:
        for e in log.all():
            f.write(json.dumps({"ts": e.ts, "stage": e.stage,
                                "kind": e.kind, "payload": e.payload}) + "\n")
    with open("runs/brownfield/metrics.json", "w") as f:
        json.dump(compute_metrics(log), f, indent=2)
    print("\nSaved audit log to runs/brownfield/")
