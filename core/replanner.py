"""
replanner.py  —  decides what happens when a node fails.

Builds the ESCALATION PACKAGE handed to a human when retries are exhausted.
The diagnosis and proposed fixes are now LLM-GENERATED: the model reads the
real failure output and the artifacts and explains what went wrong and how to
fix it. This is advisory — the human still makes the decision.
"""

from core.event_log import EventLog, Event, build_state


def _llm_diagnosis(node_name, reason, state):
    """Ask the LLM to explain the failure and propose fixes. Falls back to
    canned text if the call fails, so escalation never breaks."""
    try:
        from nodes.llm import call_llm
        artifacts = state.get("artifacts", {})
        code = artifacts.get("implement", {}).get("code", "")[:1500]
        tests = artifacts.get("test", {}).get("tests", "")[:1000]

        prompt = (
            f"A software pipeline's '{node_name}' step failed after 3 retries.\n\n"
            f"Failure output:\n{reason}\n\n"
            f"Generated code:\n{code}\n\n"
            f"Generated tests:\n{tests}\n\n"
            "In under 120 words: (1) explain the ROOT CAUSE of the failure "
            "specifically, and (2) give 2-3 concrete proposed fixes. "
            "Format:\nDIAGNOSIS: ...\nFIXES:\n1. ...\n2. ..."
        )
        return call_llm(prompt)
    except Exception as e:
        return (f"DIAGNOSIS: '{node_name}' failed its gate: {reason}\n"
                f"FIXES:\n1. Correct the artifact and re-run.\n"
                f"2. Roll back to design and revise.\n"
                f"(LLM diagnosis unavailable: {e})")


def build_escalation(node_name, gate, reason, attempts, log):
    """Assemble the decision-ready package for the human."""
    lineage = [f"[{e.stage}] {e.kind} {e.payload}" for e in log.for_stage(node_name)]
    state = build_state(log)

    diagnosis = _llm_diagnosis(node_name, reason, state)

    return {
        "failed_node": node_name,
        "gate": gate,
        "reason": reason,
        "attempts": attempts,
        "diagnosis": diagnosis,
        "lineage": lineage,
    }


def present_and_await(package, log, run_id):
    """Block-and-wait human gate. Print the package, log the wait, take input."""
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
    print(f"\n  LLM DIAGNOSIS & PROPOSED FIXES:\n")
    for line in package["diagnosis"].splitlines():
        print(f"    {line}")
    print("\n  DECISION LINEAGE (this node's event trail):")
    for line in package["lineage"]:
        print(f"    - {line}")
    print("\n" + "=" * 64)

    choice = input("  Enter a fix to approve, or 'stop' to halt: ").strip()
    log.append(Event(run_id, "human_gate", "human_decided", {"choice": choice}))
    return choice
