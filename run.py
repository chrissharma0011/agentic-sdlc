"""
run.py  —  entry point. Wires the pieces together and runs one full pipeline.

For now the nodes are STUBS: they do trivial fake work so we can watch the
whole machine execute end to end. Real LLM-backed nodes replace these later.
"""

from core.graph import TaskGraph, Task
from core.node import Node
from core.controller import Controller


# --- Stub nodes: each just writes a small artifact so we can see flow ---
class StubNode(Node):
    """A node that produces a fixed artifact. Used to test the machine."""
    def __init__(self, name, artifact):
        self._name = name
        self._artifact = artifact

    # 'name' is a class attr on Node; we override via property for stubs.
    @property
    def name(self):
        return self._name

    def run(self, state):
        return self._artifact


def build_greenfield_graph() -> TaskGraph:
    """The task graph for building the shortener from scratch."""
    g = TaskGraph()
    g.add(Task("requirement"))
    g.add(Task("plan", depends_on=["requirement"]))
    g.add(Task("architect", depends_on=["plan"]))
    g.add(Task("implement", depends_on=["architect"], parallel_group="build"))
    g.add(Task("test", depends_on=["architect"], parallel_group="build"))
    g.add(Task("verify", depends_on=["implement", "test"]))
    g.add(Task("document", depends_on=["verify"]))
    g.add(Task("release", depends_on=["document"]))
    return g


def build_nodes() -> dict:
    """One stub node per task, each writing a placeholder artifact."""
    return {
        "requirement": StubNode("requirement", {"spec": "shorten URLs + redirect + click count"}),
        "plan":        StubNode("plan", {"tasks": ["api", "redirect", "analytics"]}),
        "architect":   StubNode("architect", {"design": "FastAPI + in-memory map"}),
        "implement":   StubNode("implement", {"code": "app.py written"}),
        "test":        StubNode("test", {"tests": "test_app.py written"}),
        "verify":      StubNode("verify", {"result": "all tests pass"}),
        "document":    StubNode("document", {"docs": "README updated"}),
        "release":     StubNode("release", {"release": "change record filed"}),
    }


if __name__ == "__main__":
    graph = build_greenfield_graph()
    nodes = build_nodes()
    controller = Controller(graph, nodes, run_id="run-greenfield-001")

    log = controller.run()

    print("=== FULL RUN — event log ===")
    for e in log.all():
        print(f"  [{e.stage:12}] {e.kind:18} {e.payload}")

    print("\n=== FINAL TASK STATUSES ===")
    for task in graph.all():
        print(f"  {task.name:12} -> {task.status}")
