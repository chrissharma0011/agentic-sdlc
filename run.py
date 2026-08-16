"""
run.py  —  entry point. Builds the graph via the Planner, wires the right nodes
(human gates + brownfield patching), and runs the pipeline.
"""

from core.planner import plan, BROWNFIELD_QUESTIONS, AMBIGUOUS_QUESTIONS
from core.controller import Controller
from core.event_log import Event
from core.node import Node
from nodes.agents import REAL_NODES, PatchImplementNode
from nodes.human_gates import HumanClarifyNode, HumanApprovalNode


class PassThrough(Node):
    def __init__(self, name):
        self._name = name
    @property
    def name(self):
        return self._name
    def run(self, state):
        return {"note": f"{self._name} not implemented"}


def build_human_nodes(classification):
    nodes = {}
    if classification == "brownfield":
        nodes["clarify"] = HumanClarifyNode("clarify", BROWNFIELD_QUESTIONS)
        nodes["approval"] = HumanApprovalNode("approval", "context_retrieval",
                                              "approve change to existing code")
    elif classification == "ambiguous":
        nodes["clarify"] = HumanClarifyNode("clarify", AMBIGUOUS_QUESTIONS)
        nodes["approval"] = HumanApprovalNode("approval", "clarify",
                                              "approve the resolved spec")
    return nodes


def run_pipeline(requirement: str, run_id: str):
    graph, plan_artifact = plan(requirement)
    classification = plan_artifact["classification"]

    nodes = {}
    human_nodes = build_human_nodes(classification)

    for task in graph.all():
        if task.name in human_nodes:
            nodes[task.name] = human_nodes[task.name]
        elif task.name == "implement" and classification == "brownfield":
            # Brownfield PATCHES the existing file instead of regenerating.
            nodes[task.name] = PatchImplementNode()
        elif task.name in REAL_NODES:
            nodes[task.name] = REAL_NODES[task.name]()
        else:
            nodes[task.name] = PassThrough(task.name)

    controller = Controller(graph, nodes, run_id)
    controller.log.append(Event(run_id, "input", "artifact_written", {"raw": requirement}))
    log = controller.run()
    return log, graph, plan_artifact


if __name__ == "__main__":
    requirement = "Build a URL shortener with redirect and click counting"
    log, graph, plan_artifact = run_pipeline(requirement, "run-greenfield")
    print(f"Classified as: {plan_artifact['classification']}")
    for t in graph.all():
        print(f"  {t.name:16} -> {t.status}")
