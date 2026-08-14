"""
replanner.py  —  decides what happens when a node fails.

Two responsibilities, kept separate from the controller on purpose:
  1. Build the ESCALATION PACKAGE (diagnosis + proposed fixes + lineage)
     that gets handed to a human when retries are exhausted.
  2. (Later) insert repair tasks into the graph when a human approves a fix.

Right now the diagnosis and fixes are STUBS — canned text. At step 7, when
nodes are LLM-backed, the same structure gets a real model-generated diagnosis.
The container is built now; the judgment drops in later.
"""

from core.event_log import EventLog, Event


def build_escalation(node_name: str, gate: str, reason: str,
                     attempts: int, log: EventLog) -> dict:
    """
    Assemble the decision-ready package for the human.

    - what failed: node + gate + the criterion it violated (from the log, exact)
    - attempts: how many tries were burned (proves it's not a flake)
    - diagnosis: WHY it likely failed (stub now, LLM later)
    - proposed_fixes: concrete options the human can approve (stub now, LLM later)
    - lineage: the recent events so the human can audit the path, not just the end
    """
    # Lineage: pull this node's own event trail so the human sees the full story.
    lineage = [
        f"[{e.stage}] {e.kind} {e.payload}"
        for e in log.for_stage(node_name)
    ]

    # Diagnosis + fixes are canned for now. The SHAPE is what matters —
    # step 7 replaces these two fields with real LLM output.
    diagnosis = (
        f"The '{node_name}' node failed its {gate} gate {attempts} times. "
        f"Criterion violated: {reason}. "
        f"Likely cause: the upstream artifact did not satisfy this node's "
        f"acceptance criteria (placeholder diagnosis — LLM-generated at step 7)."
    )
    proposed_fixes = [
        f"Insert a repair task before '{node_name}' to correct the artifact, then re-run.",
        f"Roll back to the design stage and revise, then re-run '{node_name}'.",
        "Reject and stop the run for manual investigation.",
    ]

    return {
        "failed_node": node_name,
        "gate": gate,
        "reason": reason,
        "attempts": attempts,
        "diagnosis": diagnosis,
        "proposed_fixes": proposed_fixes,
        "lineage": lineage,
    }


def present_and_await(package: dict, log: EventLog, run_id: str) -> str:
    """
    Block-and-wait human gate. Print the package, record that we're waiting,
    then take the human's decision from input(). The decision is itself logged —
    so even the human override is in the audit trail.

    Returns the human's raw choice (a string) for the controller to act on.
    """
    log.append(Event(run_id, "human_gate", "awaiting_human", {
        "failed_node": package["failed_node"],
        "attempts": package["attempts"],
    }))

    print("\n" + "=" * 64)
    print("  HUMAN DECISION REQUIRED — automated retries exhausted")
    print("=" * 64)
    print(f"  Failed node : {package['failed_node']}")
    print(f"  Gate        : {package['gate']}")
    print(f"  Attempts    : {package['attempts']}")
    print(f"\n  DIAGNOSIS:\n    {package['diagnosis']}")
    print("\n  PROPOSED FIXES:")
    for i, fix in enumerate(package["proposed_fixes"], start=1):
        print(f"    {i}. {fix}")
    print("\n  DECISION LINEAGE (this node's event trail):")
    for line in package["lineage"]:
        print(f"    - {line}")
    print("\n" + "=" * 64)

    choice = input("  Enter fix number to approve, or 'stop' to halt: ").strip()

    log.append(Event(run_id, "human_gate", "human_decided", {"choice": choice}))
    return choice
