"""Synthetic test of the new controller: parallel exec, replan, approval-resume."""
import sys, builtins
sys.path.insert(0, '/tmp/asdlc/agentic-sdlc-main')

from core.graph import TaskGraph, Task, DONE
from core.node import Node, GateError
from core.controller import Controller
from core.event_log import build_state

# --- Test 1: parallel group runs concurrently, whole graph completes ---
class OK(Node):
    def __init__(self, n): self._n = n
    @property
    def name(self): return self._n
    def run(self, state): return {"ok": True}

def make_graph():
    g = TaskGraph()
    g.add(Task("architect"))
    g.add(Task("implement", depends_on=["architect"], parallel_group="build"))
    g.add(Task("test", depends_on=["architect"], parallel_group="build"))
    g.add(Task("verify", depends_on=["implement", "test"]))
    return g

g = make_graph()
nodes = {n: OK(n) for n in ["architect","implement","test","verify"]}
ctrl = Controller(g, nodes, "t1")
log = ctrl.run()
statuses = {t.name: t.status for t in g.all()}
assert all(s == DONE for s in statuses.values()), f"FAIL: {statuses}"
kinds = [e.kind for e in log.all()]
assert "parallel_start" in kinds and "parallel_join" in kinds, "FAIL: no parallel events"
print("TEST 1 PASS: parallel group ran concurrently, all tasks done")

# --- Test 2: verify fails -> replan injects repair -> loop back ---
class FailOnce(Node):
    """verify fails until a 'repair' artifact exists."""
    def __init__(self, n): self._n = n
    @property
    def name(self): return self._n
    def run(self, state):
        if self._n == "verify" and "repair" not in state["artifacts"]:
            raise GateError("exit", "tests failed")
        return {"ok": True}

g2 = make_graph()
# add architect dep chain for repair to attach to (repair depends_on architect)
nodes2 = {n: FailOnce(n) for n in ["architect","implement","test","verify"]}
nodes2["repair"] = OK("repair")  # repair node available when injected
ctrl2 = Controller(g2, nodes2, "t2")
log2 = ctrl2.run()
kinds2 = [e.kind for e in log2.all()]
assert "replan_injected" in kinds2, f"FAIL: no replan. kinds={set(kinds2)}"
assert g2.get("verify").status == DONE, f"FAIL: verify not done: {g2.get('verify').status}"
assert "repair" in [t.name for t in g2.all()], "FAIL: repair task not in graph"
print("TEST 2 PASS: verify failure injected a repair task and looped back to green")

# --- Test 3: approval loop is CLOSED (approve -> resume, not halt) ---
attempts = {"count": 0}
class FailTwiceThenHuman(Node):
    def __init__(self, n): self._n = n
    @property
    def name(self): return self._n
    def run(self, state):
        if self._n == "document":
            attempts["count"] += 1
            # fail forever via retries so it escalates (document can't replan)
            if attempts["count"] <= 3:
                raise GateError("exit", "doc failed")
        return {"ok": True}

g3 = TaskGraph()
g3.add(Task("architect"))
g3.add(Task("document", depends_on=["architect"]))
nodes3 = {"architect": OK("architect"), "document": FailTwiceThenHuman("document")}
# simulate human approving (typing anything but 'stop'), then it should resume & pass
inputs = iter(["approve"])
builtins.input = lambda *a, **k: next(inputs)
# stub the LLM diagnosis to avoid API call
import core.replanner as rp
rp._llm_diagnosis = lambda *a, **k: "DIAGNOSIS: test\nFIXES:\n1. retry"
ctrl3 = Controller(g3, nodes3, "t3")
log3 = ctrl3.run()
kinds3 = [e.kind for e in log3.all()]
assert "human_approved_fix" in kinds3, "FAIL: no approval event"
assert "run_finished" in kinds3, f"FAIL: did not resume/finish after approval. kinds={kinds3}"
assert g3.get("document").status == DONE, "FAIL: document not done after approval"
print("TEST 3 PASS: approval loop CLOSED - human approve resumed the run to completion")

print("\nALL CONTROLLER TESTS PASSED")
