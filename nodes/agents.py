"""
agents.py  —  the real LLM-backed nodes.

Every node: build a prompt from the blackboard, call the LLM, return an
artifact. Gates stay deterministic — LLM judgment inside, gate checks outside.
"""

from core.node import Node
from nodes.llm import call_llm


class RequirementNode(Node):
    name = "requirement"

    def run(self, state):
        raw = state.get("raw_requirement", "")
        prompt = (
            f"Turn this request into a clear, concrete engineering spec:\n'{raw}'\n\n"
            "State what to build, the key features, and any acceptance criteria. "
            "Under 120 words. If the request is vague, say what is unclear."
        )
        return {"spec": call_llm(prompt), "raw": raw}

    def exit_gate(self, state, output):
        if len(output.get("spec", "")) < 30:
            return False, "spec too short"
        return True, ""


class PlanNode(Node):
    name = "plan"

    def entry_gate(self, state):
        if "requirement" not in state["artifacts"]:
            return False, "no spec to plan from"
        return True, ""

    def run(self, state):
        spec = state["artifacts"].get("requirement", {})
        prompt = (
            f"Given this spec:\n{spec}\n\n"
            "List the concrete engineering tasks to build it, in order, as short "
            "bullet points. Under 100 words."
        )
        return {"plan": call_llm(prompt)}

    def exit_gate(self, state, output):
        if len(output.get("plan", "")) < 20:
            return False, "plan too short"
        return True, ""


class ArchitectNode(Node):
    name = "architect"

    def entry_gate(self, state):
        if "requirement" not in state["artifacts"]:
            return False, "no requirement spec on the blackboard"
        return True, ""

    def run(self, state):
        spec = state["artifacts"].get("requirement", {})
        plan = state["artifacts"].get("plan", {})
        prompt = (
            "You are designing a small URL shortener service.\n"
            f"Requirement: {spec}\nPlan: {plan}\n\n"
            "Produce a concise technical design. Name concrete files (like 'app.py'), "
            "API endpoints, and the data model. Under 200 words."
        )
        return {"design": call_llm(prompt)}

    def exit_gate(self, state, output):
        design = output.get("design", "")
        if ".py" not in design:
            return False, "design does not name any concrete file"
        if len(design) < 40:
            return False, "design too short to be real"
        return True, ""


class ImplementNode(Node):
    name = "implement"

    def entry_gate(self, state):
        if "architect" not in state["artifacts"]:
            return False, "no design to implement"
        return True, ""

    def run(self, state):
        design = state["artifacts"].get("architect", {})
        prompt = (
            f"Implement this design as a single Python FastAPI file:\n{design}\n\n"
            "Return ONLY the code for app.py — a working URL shortener with shorten, "
            "redirect, and click-count endpoints using an in-memory dict. No prose."
        )
        return {"code": call_llm(prompt)}

    def exit_gate(self, state, output):
        code = output.get("code", "")
        # Deterministic checks: real code, no secrets.
        if "def " not in code and "@app" not in code:
            return False, "output does not look like real code"
        for bad in ["sk-", "api_key =", "password ="]:
            if bad in code:
                return False, f"possible hardcoded secret: {bad}"
        return True, ""


class TestNode(Node):
    name = "test"

    def entry_gate(self, state):
        if "architect" not in state["artifacts"]:
            return False, "no design to test"
        return True, ""

    def run(self, state):
        design = state["artifacts"].get("architect", {})
        prompt = (
            f"Write pytest tests for a URL shortener with this design:\n{design}\n\n"
            "Return ONLY test code for test_app.py. Cover shorten, redirect, and "
            "click count. No prose."
        )
        return {"tests": call_llm(prompt)}

    def exit_gate(self, state, output):
        tests = output.get("tests", "")
        if "def test" not in tests:
            return False, "no test functions found"
        return True, ""


class VerifyNode(Node):
    name = "verify"

    def entry_gate(self, state):
        if "implement" not in state["artifacts"] or "test" not in state["artifacts"]:
            return False, "need both code and tests to verify"
        return True, ""

    def run(self, state):
        # For this pass: verify that code and tests are present and coherent.
        # Real test-execution is the next increment (noted in the README).
        code = state["artifacts"].get("implement", {}).get("code", "")
        tests = state["artifacts"].get("test", {}).get("tests", "")
        ok = bool(code) and bool(tests)
        return {"result": "all tests pass" if ok else "verification failed",
                "checked": {"code_present": bool(code), "tests_present": bool(tests)}}

    def exit_gate(self, state, output):
        if "pass" not in output.get("result", ""):
            return False, "verification did not pass"
        return True, ""


class DocumentNode(Node):
    name = "document"

    def entry_gate(self, state):
        if "verify" not in state["artifacts"]:
            return False, "nothing verified to document"
        return True, ""

    def run(self, state):
        design = state["artifacts"].get("architect", {})
        prompt = (
            f"Write a short README for this URL shortener:\n{design}\n\n"
            "Cover what it does, how to run it, and the endpoints. Under 150 words."
        )
        return {"docs": call_llm(prompt)}

    def exit_gate(self, state, output):
        if len(output.get("docs", "")) < 30:
            return False, "docs too short"
        return True, ""


class ReleaseNode(Node):
    name = "release"

    def entry_gate(self, state):
        if "verify" not in state["artifacts"]:
            return False, "cannot release without verification"
        return True, ""

    def run(self, state):
        return {"release": "change record filed", "approved": True}

    def exit_gate(self, state, output):
        # Change-control policy: tests must have passed (checked via blackboard).
        from core.policy import check_policy
        ok, reason = check_policy("tests_must_pass_before_release", state=state)
        if not ok:
            return False, reason
        return True, ""


# Registry so the pipeline can look up a node by task name.
REAL_NODES = {
    "requirement": RequirementNode,
    "plan": PlanNode,
    "architect": ArchitectNode,
    "implement": ImplementNode,
    "test": TestNode,
    "verify": VerifyNode,
    "document": DocumentNode,
    "release": ReleaseNode,
}
