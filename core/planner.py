"""
planner.py  —  generates the task DAG from a requirement (dynamic, not hardcoded).

Three steps:
  1. classify()      -> greenfield / brownfield / ambiguous (keyword rules for now,
                        LLM later). This decides the graph SHAPE.
  2. emit graph      -> a DIFFERENT TaskGraph per class. This is the proof that the
                        graph is generated per requirement, not fixed.
  3. plan artifact   -> a readable plan.json (classification + rationale + each
                        task's acceptance criterion). The criteria become the gates.

Keyword classification is a deterministic placeholder; the LLM replaces it next.
"""

from core.graph import TaskGraph, Task


def classify(requirement: str) -> str:
    """Decide the requirement type. Simple, transparent keyword rules."""
    r = requirement.lower()

    # Ambiguous: vague asks with no concrete target.
    vague = ["better", "improve", "more reliable", "faster", "nicer", "optimize"]
    if any(w in r for w in vague) and not any(w in r for w in ["add ", "endpoint", "field"]):
        return "ambiguous"

    # Brownfield: changing something that already exists.
    change = ["add ", "fix", "refactor", "change", "update", "remove", "bug"]
    if any(w in r for w in change):
        return "brownfield"

    # Default: building something new.
    return "greenfield"


def _greenfield_graph() -> TaskGraph:
    g = TaskGraph()
    g.add(Task("requirement", acceptance="spec is concrete and unambiguous",
               rationale="normalize the request"))
    g.add(Task("plan", depends_on=["requirement"],
               acceptance="every task has an owner and criteria",
               rationale="decompose into a task graph"))
    g.add(Task("architect", depends_on=["plan"],
               acceptance="design names concrete files and APIs",
               rationale="design the system from scratch"))
    g.add(Task("implement", depends_on=["architect"], parallel_group="build",
               acceptance="code builds and contains no secrets",
               rationale="write the code"))
    g.add(Task("test", depends_on=["architect"], parallel_group="build",
               acceptance="tests exist for each endpoint",
               rationale="write tests in parallel with code"))
    g.add(Task("verify", depends_on=["implement", "test"],
               acceptance="all tests pass",
               rationale="run tests and policy checks"))
    g.add(Task("document", depends_on=["verify"],
               acceptance="README covers setup and usage",
               rationale="document the result"))
    g.add(Task("release", depends_on=["document"],
               acceptance="tests passed and change record filed",
               rationale="human-gated release"))
    return g


def _brownfield_graph() -> TaskGraph:
    g = TaskGraph()
    g.add(Task("requirement", acceptance="change is concrete",
               rationale="normalize the change request"))
    # THE difference: brownfield must read existing code before designing.
    g.add(Task("context_retrieval", depends_on=["requirement"],
               acceptance="impacted files and APIs identified",
               rationale="Core Req 3: understand existing code before changing it"))
    # Note: no heavy 'plan' node — a scoped change skips full decomposition.
    g.add(Task("architect", depends_on=["context_retrieval"],
               acceptance="design cites the real files it will change",
               rationale="design the change against actual code"))
    g.add(Task("implement", depends_on=["architect"], parallel_group="build",
               acceptance="change builds and contains no secrets",
               rationale="make the change"))
    g.add(Task("test", depends_on=["architect"], parallel_group="build",
               acceptance="new and existing tests cover the change",
               rationale="test the change without breaking existing behavior"))
    g.add(Task("verify", depends_on=["implement", "test"],
               acceptance="all tests pass",
               rationale="regression check"))
    g.add(Task("document", depends_on=["verify"],
               acceptance="changelog updated",
               rationale="record what changed"))
    g.add(Task("release", depends_on=["document"],
               acceptance="tests passed and change record filed",
               rationale="human-gated release"))
    return g


def _ambiguous_graph() -> TaskGraph:
    g = TaskGraph()
    g.add(Task("requirement", acceptance="raw request captured",
               rationale="capture the vague ask"))
    # THE difference: a human clarify gate BEFORE any planning happens.
    g.add(Task("clarify", depends_on=["requirement"],
               acceptance="ambiguity resolved by a human or assumptions logged",
               rationale="requirement is underspecified — do not guess"))
    g.add(Task("plan", depends_on=["clarify"],
               acceptance="every task has an owner and criteria",
               rationale="plan only after the ask is clear"))
    g.add(Task("architect", depends_on=["plan"],
               acceptance="design names concrete files and APIs",
               rationale="design against the clarified requirement"))
    g.add(Task("implement", depends_on=["architect"], parallel_group="build",
               acceptance="code builds and contains no secrets",
               rationale="write the code"))
    g.add(Task("test", depends_on=["architect"], parallel_group="build",
               acceptance="tests exist for each endpoint",
               rationale="write tests in parallel"))
    g.add(Task("verify", depends_on=["implement", "test"],
               acceptance="all tests pass",
               rationale="run tests and policy checks"))
    g.add(Task("document", depends_on=["verify"],
               acceptance="README covers setup and usage",
               rationale="document the result"))
    g.add(Task("release", depends_on=["document"],
               acceptance="tests passed and change record filed",
               rationale="human-gated release"))
    return g


_BUILDERS = {
    "greenfield": _greenfield_graph,
    "brownfield": _brownfield_graph,
    "ambiguous": _ambiguous_graph,
}


def plan(requirement: str) -> tuple[TaskGraph, dict]:
    """
    The Planner entry point. Returns (graph, plan_artifact).
    The graph is executable; the plan_artifact is the auditable record.
    """
    kind = classify(requirement)
    graph = _BUILDERS[kind]()

    plan_artifact = {
        "requirement": requirement,
        "classification": kind,
        "rationale": f"classified as '{kind}' from the requirement wording",
        "tasks": [
            {"name": t.name, "depends_on": t.depends_on,
             "acceptance": t.acceptance, "rationale": t.rationale}
            for t in graph.all()
        ],
    }
    return graph, plan_artifact
