"""
demo_failure.py  —  watch the recovery loop run live.

We swap in a 'verify' node that FAILS its exit gate every time. Then we run
the pipeline and watch the controller:
    retry (3x) -> rollback each time (history kept) -> escalate to a human.

This is the differentiator: reliability shown, not claimed.
"""

from core.graph import TaskGraph, Task
from core.node import Node
from core.controller import Controller
from run import StubNode, build_greenfield_graph, build_nodes


class AlwaysFailsVerify(Node):
    """A verify node whose exit gate never passes — simulates a broken test."""
    name = "verify"

    def run(self, state):
        # It 'runs' fine and produces a result...
        return {"result": "ran the test suite"}

    def exit_gate(self, state, output):
        # ...but the acceptance criterion always fails.
        # Note: state['attempt'] and state['last_failure'] are available here —
        # a real node could adapt. Ours fails on purpose to force escalation.
        return False, "1 of 4 tests failing (redirect returns 404)"


if __name__ == "__main__":
    graph = build_greenfield_graph()
    nodes = build_nodes()
    nodes["verify"] = AlwaysFailsVerify()      # swap the good verify for the broken one

    controller = Controller(graph, nodes, run_id="run-failure-demo")
    log = controller.run()

    print("\n=== EVENT LOG AFTER THE RUN ===")
    for e in log.all():
        print(f"  [{e.stage:12}] {e.kind:20} {e.payload}")

# --- metrics on the failure run ---
from core.metrics import print_metrics
print()
print_metrics(log)
