"""
human_gates.py  —  interactive human-in-the-loop nodes.

HumanClarifyNode : asks questions, records answers.
HumanApprovalNode: three-way gate — approve / reject / revise-with-feedback.
  On 'revise', the human's guidance is stored on the blackboard so the
  downstream implement/patch step honors it.
"""

from core.node import Node
from core.event_log import Event


class HumanClarifyNode(Node):
    def __init__(self, name, questions):
        self._name = name
        self._questions = questions

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
    def __init__(self, name, summary_key, prompt_label):
        self._name = name
        self._summary_key = summary_key
        self._label = prompt_label

    @property
    def name(self):
        return self._name

    def run(self, state):
        summary = state["artifacts"].get(self._summary_key, {})
        print("\n" + "=" * 60)
        print(f"  HUMAN APPROVAL REQUIRED — {self._label}")
        print("=" * 60)
        print(f"  Review:\n  {summary}")
        print("=" * 60)
        print("  Options: 'yes' (approve) / 'no' (reject) / 'revise' (approve with changes)")
        choice = input("  Your decision: ").strip().lower()

        feedback = ""
        if choice == "revise":
            feedback = input("  What should change? ").strip()

        return {
            "approved": choice in ("yes", "y", "revise"),
            "choice": choice,
            "feedback": feedback,
        }

    def exit_gate(self, state, output):
        if not output.get("approved"):
            return False, f"human rejected: {output.get('choice')}"
        return True, ""
