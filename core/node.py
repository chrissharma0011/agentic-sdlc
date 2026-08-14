"""
node.py  —  the base class every agent node inherits from.

The whole governance idea lives here. A node is never just "do the work."
It is always three steps:

    1. ENTRY GATE   — are the preconditions met? (do we have what we need?)
    2. RUN          — do the actual work (later: an LLM call)
    3. EXIT GATE    — does the output meet the acceptance criteria?

If either gate fails, we do NOT pass bad output downstream. We record the
failure as an event, and the controller decides what to do (retry / replan).
This is what turns a task runner into a *governed* pipeline.
"""

from core.event_log import Event, EventLog


class GateError(Exception):
    """Raised when a gate rejects. Carries a human-readable reason."""
    def __init__(self, gate: str, reason: str):
        self.gate = gate          # "entry" or "exit"
        self.reason = reason
        super().__init__(f"{gate} gate failed: {reason}")


class Node:
    """
    Base class. Real nodes (Planner, Architect...) subclass this and override
    entry_gate, run, and exit_gate. The execute() method below wires the three
    steps together the SAME way for every node — that consistency is the point.
    """

    name = "base"   # each subclass sets its own name, e.g. "plan"

    def entry_gate(self, state: dict) -> tuple[bool, str]:
        # Return (ok, reason). Default: always allowed in.
        # Subclasses override to check "is spec present?", "did plan run?", etc.
        return True, ""

    def run(self, state: dict) -> dict:
        # Do the work, return the artifact this node produces.
        # Subclasses override. Base does nothing.
        return {}

    def exit_gate(self, state: dict, output: dict) -> tuple[bool, str]:
        # Return (ok, reason). Default: always accept.
        # Subclasses override to check acceptance criteria on `output`.
        return True, ""

    def execute(self, state: dict, log: EventLog, run_id: str) -> dict:
        """
        The governed lifecycle, identical for every node.
        Records an event at each step so the whole thing is auditable.
        """
        log.append(Event(run_id, self.name, "node_started", {}))

        # --- 1. ENTRY GATE ---
        ok, reason = self.entry_gate(state)
        if not ok:
            log.append(Event(run_id, self.name, "gate_failed", {"gate": "entry", "reason": reason}))
            raise GateError("entry", reason)

        # --- 2. RUN ---
        output = self.run(state)

        # --- 3. EXIT GATE ---
        ok, reason = self.exit_gate(state, output)
        if not ok:
            log.append(Event(run_id, self.name, "gate_failed", {"gate": "exit", "reason": reason}))
            raise GateError("exit", reason)

        # Passed both gates: record the artifact and return it.
        log.append(Event(run_id, self.name, "artifact_written", output))
        log.append(Event(run_id, self.name, "node_passed", {}))
        return output


# --- A tiny concrete node so we can SEE the gates work ---
class DemoPlanNode(Node):
    name = "plan"

    def entry_gate(self, state):
        # We can only plan if a spec exists on the blackboard.
        if "requirement" not in state["artifacts"]:
            return False, "no spec on the blackboard yet"
        return True, ""

    def run(self, state):
        # Pretend to produce a plan.
        return {"tasks": ["build API", "add redirect", "add analytics"]}

    def exit_gate(self, state, output):
        # Acceptance criterion: the plan must contain at least one task.
        if not output.get("tasks"):
            return False, "plan produced no tasks"
        return True, ""


if __name__ == "__main__":
    from core.event_log import build_state

    log = EventLog()
    run = "run-001"

    # Case 1: entry gate should FAIL (no spec on the blackboard).
    print("=== Case 1: run plan with an empty blackboard (entry gate should reject) ===")
    try:
        state = build_state(log)          # empty
        DemoPlanNode().execute(state, log, run)
    except GateError as e:
        print("  rejected as expected ->", e)

    # Now put a spec on the blackboard.
    log.append(Event(run, "requirement", "artifact_written", {"spec": "shorten URLs"}))

    # Case 2: entry gate passes, node runs, exit gate passes.
    print("\n=== Case 2: run plan with a spec present (should pass both gates) ===")
    state = build_state(log)
    output = DemoPlanNode().execute(state, log, run)
    print("  plan produced ->", output)

    print("\n=== The audit log after both cases ===")
    for e in log.all():
        print(f"  [{e.stage}]  {e.kind}  {e.payload}")
