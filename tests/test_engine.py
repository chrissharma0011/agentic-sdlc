"""
Engine tests for the orchestrator control logic.

These run WITHOUT an API key: they use synthetic in-memory nodes and stub the
human input, so they are deterministic and fast. They exercise the three
behaviors that are hardest to eyeball and most likely to regress:
  1. concurrent fork-join execution
  2. dynamic re-planning (graph mutation) on verify failure
  3. the closed human-approval loop (approve -> resume, not halt)

Run:  python3 -m pytest tests/test_engine.py -v
   or: python3 tests/test_engine.py   (falls back to running all tests)
"""

import sys
import os
import builtins

# Make the project root importable however this file is invoked.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.graph import TaskGraph, Task, DONE
from core.node import Node, GateError
from core.controller import Controller


class OK(Node):
    """A node that always succeeds, writing a fixed artifact."""
    def __init__(self, n, art=None):
        self._n = n
        self._art = art or {"ok": True}
    @property
    def name(self):
        return self._n
    def run(self, state):
        return self._art


def _base_graph():
    g = TaskGraph()
    g.add(Task("architect"))
    g.add(Task("implement", depends_on=["architect"], parallel_group="build"))
    g.add(Task("test", depends_on=["architect"], parallel_group="build"))
    g.add(Task("verify", depends_on=["implement", "test"]))
    return g


def test_parallel_fork_join():
    """implement and test share a parallel_group -> run concurrently, sync at verify."""
    g = _base_graph()
    nodes = {n: OK(n) for n in ["architect", "implement", "test", "verify"]}
    ctrl = Controller(g, nodes, "t-parallel")
    log = ctrl.run()
    kinds = [e.kind for e in log.all()]
    assert all(t.status == DONE for t in g.all())
    assert "parallel_start" in kinds and "parallel_join" in kinds


def test_dynamic_replanning():
    """verify fails until a repair artifact exists -> controller injects repair,
    reroutes, and loops back to green. Uses an OFFLINE repair stub."""
    class VerifyUntilRepaired(Node):
        name = "verify"
        def run(self, state):
            if "repair" not in state["artifacts"]:
                return {"passed": False}
            return {"passed": True}
        def exit_gate(self, state, output):
            if not output.get("passed"):
                return False, "tests failed"
            return True, ""

    g = _base_graph()
    nodes = {
        "architect": OK("architect", {"design": "d", "contract": {"endpoints": [1]}}),
        "implement": OK("implement", {"code": "c"}),
        "test": OK("test", {"tests": "t"}),
        "verify": VerifyUntilRepaired(),
        "repair": OK("repair", {"code": "repaired"}),   # offline stub; controller respects it
    }
    ctrl = Controller(g, nodes, "t-replan")
    log = ctrl.run()
    kinds = [e.kind for e in log.all()]
    assert "replan_injected" in kinds
    assert "repair" in [t.name for t in g.all()]
    assert g.get("verify").status == DONE


def test_approval_loop_closes(monkeypatch=None):
    """After retries are exhausted, human 'approve' RESUMES the run to completion
    (not halt). Stubs input() and the LLM diagnosis so it runs offline."""
    attempts = {"n": 0}

    class FailThenPass(Node):
        name = "document"
        def run(self, state):
            attempts["n"] += 1
            if attempts["n"] <= 3:
                return {"bad": True}
            return {"ok": True}
        def exit_gate(self, state, output):
            if output.get("bad"):
                return False, "doc failed"
            return True, ""

    g = TaskGraph()
    g.add(Task("architect"))
    g.add(Task("document", depends_on=["architect"]))
    nodes = {"architect": OK("architect"), "document": FailThenPass()}

    # stub human input (approve) and the LLM diagnosis
    saved_input = builtins.input
    builtins.input = lambda *a, **k: "approve"
    import core.replanner as rp
    saved_diag = rp._llm_diagnosis
    rp._llm_diagnosis = lambda *a, **k: "DIAGNOSIS: test\nFIXES:\n1. retry"
    try:
        ctrl = Controller(g, nodes, "t-approve")
        log = ctrl.run()
    finally:
        builtins.input = saved_input
        rp._llm_diagnosis = saved_diag

    kinds = [e.kind for e in log.all()]
    assert "human_approved_fix" in kinds
    assert "run_finished" in kinds
    assert g.get("document").status == DONE


if __name__ == "__main__":
    # Allow running directly; run all tests and report, without halting on first fail.
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS: {name}")
            except Exception as e:
                failures += 1
                print(f"FAIL: {name} -> {e}")
    print("\n" + ("ALL ENGINE TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED"))
    sys.exit(1 if failures else 0)
