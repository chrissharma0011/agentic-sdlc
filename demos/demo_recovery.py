"""
demo_recovery.py  —  OFFLINE demonstration of the recovery machinery.

Runs WITHOUT an API key. Uses synthetic nodes to force failures so you can
watch, in the event log, the full governed-recovery sequence actually fire:

    retry (bounded)  ->  rollback (append-only)  ->  dynamic re-plan
    (inject a repair task + reroute)  ->  recovery to green

This exists because the happy-path committed runs show success_rate 1.0 with
zero retries/rollbacks; this demo makes the reliability features reproducible
for a reviewer with no setup.

Run:  python3 -m demos.demo_recovery
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.graph import TaskGraph, Task, DONE
from core.node import Node
from core.controller import Controller
from core.metrics import compute_metrics


class OK(Node):
    def __init__(self, n, art=None):
        self._n = n; self._art = art or {"ok": True}
    @property
    def name(self): return self._n
    def run(self, state): return self._art


class VerifyFailsUntilRepaired(Node):
    """Fails verification until a repair artifact appears — forcing the
    controller to retry, roll back, and then dynamically re-plan."""
    name = "verify"
    def run(self, state):
        return {"passed": "repair" in state["artifacts"]}
    def exit_gate(self, state, output):
        if not output.get("passed"):
            return False, "generated tests did not pass"
        return True, ""


def main():
    g = TaskGraph()
    g.add(Task("architect"))
    g.add(Task("implement", depends_on=["architect"], parallel_group="build"))
    g.add(Task("test", depends_on=["architect"], parallel_group="build"))
    g.add(Task("verify", depends_on=["implement", "test"]))

    nodes = {
        "architect": OK("architect", {"design": "d", "contract": {"endpoints": [1]}}),
        "implement": OK("implement", {"code": "c"}),
        "test": OK("test", {"tests": "t"}),
        "verify": VerifyFailsUntilRepaired(),
        "repair": OK("repair", {"code": "repaired"}),   # offline repair stub
    }

    print("=== OFFLINE RECOVERY DEMO ===")
    print("Forcing a verification failure to show retry -> rollback -> re-plan.\n")

    ctrl = Controller(g, nodes, "demo-recovery")
    log = ctrl.run()

    print("=== EVENT LOG (the governed-recovery sequence) ===")
    for e in log.all():
        print(f"  [{e.stage:12}] {e.kind}")

    print("\n=== FINAL STATUSES ===")
    for t in g.all():
        print(f"  {t.name:12} -> {t.status}")

    print("\n=== RELIABILITY METRICS (folded from the log) ===")
    for k, v in compute_metrics(log).items():
        print(f"  {k}: {v}")

    print("\nNote: 'replan_injected' above is the graph mutating at runtime — a")
    print("repair task was inserted and verify was rerouted to depend on it.")


if __name__ == "__main__":
    main()
