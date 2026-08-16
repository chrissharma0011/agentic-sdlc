"""
planner.py  —  generates the task DAG per requirement class.

Greenfield: build from scratch, no human gates (low risk).
Brownfield: changes existing code -> clarify (change-risk questions) + approval
            before modifying (high-impact action per Core Req 4).
Ambiguous:  vague ask -> clarify (spec questions) + approval of resolved spec.
"""

from core.graph import TaskGraph, Task


def classify(requirement: str) -> str:
    r = requirement.lower()
    vague = ["better", "improve", "more reliable", "faster", "nicer", "optimize"]
    if any(w in r for w in vague) and not any(w in r for w in ["add ", "endpoint", "field"]):
        return "ambiguous"
    change = ["add ", "fix", "refactor", "change", "update", "remove", "bug"]
    if any(w in r for w in change):
        return "brownfield"
    return "greenfield"


# Scenario-specific clarifying questions (used by the HumanClarifyNode).
BROWNFIELD_QUESTIONS = [
    "Should backward compatibility with existing endpoints be preserved? (yes/no)",
    "Is it acceptable to change the stored data model for this feature? (yes/no)",
]
AMBIGUOUS_QUESTIONS = [
    "What does the vague term concretely mean here? (e.g. retries / persistence / rate-limiting)",
    "What is the single most important outcome you want from this change?",
]


def _greenfield_graph() -> TaskGraph:
    g = TaskGraph()
    g.add(Task("requirement", acceptance="spec is concrete"))
    g.add(Task("plan", depends_on=["requirement"], acceptance="tasks have criteria"))
    g.add(Task("architect", depends_on=["plan"], acceptance="design names files + contract"))
    g.add(Task("implement", depends_on=["architect"], parallel_group="build",
               acceptance="code builds, no secrets"))
    g.add(Task("test", depends_on=["architect"], parallel_group="build",
               acceptance="tests exist for each endpoint"))
    g.add(Task("verify", depends_on=["implement", "test"], acceptance="all tests pass"))
    g.add(Task("document", depends_on=["verify"], acceptance="README covers usage"))
    g.add(Task("release", depends_on=["document"], acceptance="tests passed + change record"))
    return g


def _brownfield_graph() -> TaskGraph:
    g = TaskGraph()
    g.add(Task("requirement", acceptance="change is concrete"))
    g.add(Task("context_retrieval", depends_on=["requirement"],
               acceptance="impacted files/APIs identified",
               rationale="Core Req 3: understand existing code first"))
    g.add(Task("clarify", depends_on=["context_retrieval"],
               acceptance="change-risk questions answered",
               rationale="human input on change safety"))
    g.add(Task("architect", depends_on=["clarify"],
               acceptance="design cites real files + contract"))
    g.add(Task("approval", depends_on=["architect"],
               acceptance="human approved the change",
               rationale="Core Req 4: approve high-impact action before modifying code"))
    g.add(Task("implement", depends_on=["approval"], parallel_group="build",
               acceptance="change builds, no secrets"))
    g.add(Task("test", depends_on=["approval"], parallel_group="build",
               acceptance="tests cover new + existing behavior"))
    g.add(Task("verify", depends_on=["implement", "test"], acceptance="all tests pass"))
    g.add(Task("document", depends_on=["verify"], acceptance="changelog updated"))
    g.add(Task("release", depends_on=["document"], acceptance="tests passed + change record"))
    return g


def _ambiguous_graph() -> TaskGraph:
    g = TaskGraph()
    g.add(Task("requirement", acceptance="raw request captured"))
    g.add(Task("clarify", depends_on=["requirement"],
               acceptance="ambiguity resolved by human",
               rationale="Core Req 1: do not guess a vague spec"))
    g.add(Task("approval", depends_on=["clarify"],
               acceptance="human approved the resolved spec",
               rationale="confirm the interpretation before building"))
    g.add(Task("plan", depends_on=["approval"], acceptance="tasks have criteria"))
    g.add(Task("architect", depends_on=["plan"], acceptance="design names files + contract"))
    g.add(Task("implement", depends_on=["architect"], parallel_group="build",
               acceptance="code builds, no secrets"))
    g.add(Task("test", depends_on=["architect"], parallel_group="build",
               acceptance="tests exist for each endpoint"))
    g.add(Task("verify", depends_on=["implement", "test"], acceptance="all tests pass"))
    g.add(Task("document", depends_on=["verify"], acceptance="README covers usage"))
    g.add(Task("release", depends_on=["document"], acceptance="tests passed + change record"))
    return g


_BUILDERS = {
    "greenfield": _greenfield_graph,
    "brownfield": _brownfield_graph,
    "ambiguous": _ambiguous_graph,
}


def plan(requirement: str):
    kind = classify(requirement)
    graph = _BUILDERS[kind]()
    plan_artifact = {
        "requirement": requirement,
        "classification": kind,
        "tasks": [{"name": t.name, "depends_on": t.depends_on,
                   "acceptance": t.acceptance, "rationale": t.rationale}
                  for t in graph.all()],
    }
    return graph, plan_artifact
