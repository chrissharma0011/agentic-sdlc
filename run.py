"""
run.py  —  entry point. Runs the full pipeline with real LLM-backed nodes.

The Planner generates the graph from the requirement. The raw requirement is
seeded onto the blackboard as the first event, so the RequirementNode reads it
the same clean way every node reads its inputs.
"""

from core.planner import plan
from core.controller import Controller
from core.event_log import Event
from core.node import Node
from nodes.agents import REAL_NODES


class PassThrough(Node):
    """Temporary node for tasks without a real implementation yet
    (context_retrieval, clarify). We build these next."""
    def __init__(self, name):
        self._name = name

    @property
    def name(self):
        return self._name

    def run(self, state):
        return {"note": f"{self._name} not yet implemented"}


def run_pipeline(requirement: str, run_id: str):
    graph, plan_artifact = plan(requirement)

    nodes = {}
    for task in graph.all():
        if task.name in REAL_NODES:
            nodes[task.name] = REAL_NODES[task.name]()
        else:
            nodes[task.name] = PassThrough(task.name)

    controller = Controller(graph, nodes, run_id)
    # Seed the raw requirement as the first event on the blackboard.
    controller.log.append(Event(run_id, "input", "artifact_written",
                                {"raw": requirement}))
    log = controller.run()
    return log, graph, plan_artifact


if __name__ == "__main__":
    requirement = "Build a URL shortener with redirect and click counting"
    run_id = "run-greenfield-real"

    log, graph, plan_artifact = run_pipeline(requirement, run_id)

    print("=== PLAN ARTIFACT ===")
    print(f"  classified as: {plan_artifact['classification']}")
    print(f"  tasks: {[t['name'] for t in plan_artifact['tasks']]}")

    print("\n=== RUN EVENTS ===")
    for e in log.all():
        print(f"  [{e.stage:14}] {e.kind}")

    print("\n=== FINAL STATUSES ===")
    for t in graph.all():
        print(f"  {t.name:16} -> {t.status}")
