"""
planner.py  —  generates the task DAG per requirement class.

Greenfield: build from scratch, no gates.
Brownfield: change existing code -> context_retrieval + clarify + approval + patch.
Ambiguous:  vague ask -> clarify + approval, THEN routes to build-or-patch based
            on whether an app already exists (Option A: patch if it exists).
"""

import os
from core.graph import TaskGraph, Task

APP_PATH = "shortener/app.py"


def classify(requirement: str) -> str:
    r = requirement.lower()
    vague = ["better", "improve", "more reliable", "faster", "nicer", "optimize", "reliable"]
    if any(w in r for w in vague) and not any(w in r for w in ["add ", "endpoint", "field"]):
        return "ambiguous"
    change = ["add ", "fix", "refactor", "change", "update", "remove", "bug"]
    if any(w in r for w in change):
        return "brownfield"
    return "greenfield"


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
               acceptance="change-risk questions answered"))
    g.add(Task("architect", depends_on=["clarify"], acceptance="design cites real files"))
    g.add(Task("approval", depends_on=["architect"],
               acceptance="human approved the change",
               rationale="Core Req 4: approve high-impact action"))
    g.add(Task("implement", depends_on=["approval"], parallel_group="build",
               acceptance="change builds, no secrets"))
    g.add(Task("test", depends_on=["approval"], parallel_group="build",
               acceptance="tests cover new + existing behavior"))
    g.add(Task("verify", depends_on=["implement", "test"], acceptance="all tests pass"))
    g.add(Task("document", depends_on=["verify"], acceptance="changelog updated"))
    g.add(Task("release", depends_on=["document"], acceptance="tests passed + change record"))
    return g


def _ambiguous_build_graph() -> TaskGraph:
    """Vague AND nothing exists yet -> clarify, then BUILD new."""
    g = TaskGraph()
    g.add(Task("requirement", acceptance="raw request captured"))
    g.add(Task("clarify", depends_on=["requirement"],
               acceptance="ambiguity resolved by human",
               rationale="Core Req 1: do not guess a vague spec"))
    g.add(Task("approval", depends_on=["clarify"], acceptance="human approved resolved spec"))
    g.add(Task("plan", depends_on=["approval"], acceptance="tasks have criteria"))
    g.add(Task("architect", depends_on=["plan"], acceptance="design names files + contract"))
    g.add(Task("implement", depends_on=["architect"], parallel_group="build",
               acceptance="code builds, no secrets"))
    g.add(Task("test", depends_on=["architect"], parallel_group="build",
               acceptance="tests exist"))
    g.add(Task("verify", depends_on=["implement", "test"], acceptance="all tests pass"))
    g.add(Task("document", depends_on=["verify"], acceptance="README covers usage"))
    g.add(Task("release", depends_on=["document"], acceptance="tests passed + change record"))
    return g


def _ambiguous_patch_graph() -> TaskGraph:
    """Vague AND an app already exists -> clarify, then PATCH the existing thing."""
    g = TaskGraph()
    g.add(Task("requirement", acceptance="raw request captured"))
    g.add(Task("context_retrieval", depends_on=["requirement"],
               acceptance="impacted files identified",
               rationale="improving existing code -> read it first"))
    g.add(Task("clarify", depends_on=["context_retrieval"],
               acceptance="ambiguity resolved by human",
               rationale="Core Req 1: do not guess a vague spec"))
    g.add(Task("approval", depends_on=["clarify"], acceptance="human approved resolved spec"))
    g.add(Task("architect", depends_on=["approval"], acceptance="design cites real files"))
    g.add(Task("implement", depends_on=["architect"], parallel_group="build",
               acceptance="change builds, no secrets"))
    g.add(Task("test", depends_on=["architect"], parallel_group="build",
               acceptance="tests cover new + existing"))
    g.add(Task("verify", depends_on=["implement", "test"], acceptance="all tests pass"))
    g.add(Task("document", depends_on=["verify"], acceptance="changelog updated"))
    g.add(Task("release", depends_on=["document"], acceptance="tests passed + change record"))
    return g


def plan(requirement: str):
    kind = classify(requirement)

    if kind == "greenfield":
        graph = _greenfield_graph()
    elif kind == "brownfield":
        graph = _brownfield_graph()
    else:  # ambiguous: route to patch or build based on what exists (Option A)
        if os.path.exists(APP_PATH):
            graph = _ambiguous_patch_graph()
            kind = "ambiguous (patch existing)"
        else:
            graph = _ambiguous_build_graph()
            kind = "ambiguous (build new)"

    plan_artifact = {
        "requirement": requirement,
        "classification": kind,
        "tasks": [{"name": t.name, "depends_on": t.depends_on,
                   "acceptance": t.acceptance, "rationale": t.rationale}
                  for t in graph.all()],
    }
    return graph, plan_artifact
