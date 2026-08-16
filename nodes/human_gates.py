"""
human_gates.py  —  interactive human-in-the-loop nodes.

Two governance moments, both block-and-wait for typed input:
  - HumanClarifyNode  (Type B): the system ASKS the human questions, the human
    answers, and the answers go onto the blackboard for downstream nodes.
  - HumanApprovalNode (Type A): the system SHOWS the human the impact/plan and
    requires explicit approval before a high-impact action (change/release).

Both record their events, so the human's input is part of the audit trail.
"""

from core.node import Node
from core.event_log import Event


class HumanClarifyNode(Node):
    """Asks scenario-specific questions and records the human's answers."""

    def __init__(self, name, questions):
        self._name = name
        self._questions = questions   # list of question strings

    @property
    def name(self):
        return self._name

    def run(self, state):
        print("\n" + "-" * 60)
        print("  HUMAN CLARIFICATION NEEDED")
        print("-" * 60)
        answers = {}
        for q in self._questions:
            ans = input(f"  Q: {q}\n  > ").strip()
            answers[q] = ans
        print("-" * 60)
        return {"clarifications": answers}

    def exit_gate(self, state, output):
        if not output.get("clarifications"):
            return False, "no answers captured"
        return True, ""


class HumanApprovalNode(Node):
    """Shows the human what will happen and requires explicit approval."""

    def __init__(self, name, summary_key, prompt_label):
        self._name = name
        self._summary_key = summary_key      # which upstream artifact to show
        self._label = prompt_label

    @property
    def name(self):
        return self._name

    def run(self, state):
        # Show the relevant upstream artifact (e.g. the impact analysis).
        summary = state["artifacts"].get(self._summary_key, {})
        print("\n" + "=" * 60)
        print(f"  HUMAN APPROVAL REQUIRED — {self._label}")
        print("=" * 60)
        print(f"  Review:\n  {summary}")
        print("=" * 60)
        choice = input("  Approve to proceed? (yes/no): ").strip().lower()
        return {"approved": choice in ("yes", "y"), "choice": choice}

    def exit_gate(self, state, output):
        if not output.get("approved"):
            return False, f"human rejected: {output.get('choice')}"
        return True, ""
