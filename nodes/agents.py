"""
agents.py  —  the real LLM-backed nodes.

Every node: build a prompt from the blackboard, call the LLM, return an
artifact. Gates stay deterministic. Code nodes strip markdown fences; the
Verify node ACTUALLY RUNS pytest and gates on real pass/fail.
"""

import os
import subprocess
import tempfile
from core.node import Node
from nodes.llm import call_llm, strip_code_fences


class RequirementNode(Node):
    name = "requirement"

    def run(self, state):
        raw = state.get("raw_requirement", "")
        prompt = (
            f"Turn this request into a clear, concrete engineering spec:\n'{raw}'\n\n"
            "State what to build, key features, and acceptance criteria. Under 120 words."
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
        prompt = (f"Given this spec:\n{spec}\n\nList the concrete engineering tasks "
                  "to build it, in order, as short bullets. Under 100 words.")
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
        prompt = ("You are designing a small URL shortener service.\n"
                  f"Requirement: {spec}\nPlan: {plan}\n\n"
                  "Produce a concise technical design. Name concrete files (like "
                  "'app.py'), API endpoints, and the data model. Under 200 words.")
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
        last = state.get("last_failure")
        fix_hint = f"\nThe previous attempt failed: {last}. Fix it." if last else ""
        prompt = (f"Implement this design as a single Python FastAPI file:\n{design}\n"
                  f"{fix_hint}\n\n"
                  "Return ONLY the code for app.py — a working URL shortener with "
                  "shorten, redirect, and click-count endpoints using an in-memory "
                  "dict. No prose, no markdown fences.")
        return {"code": strip_code_fences(call_llm(prompt))}

    def exit_gate(self, state, output):
        code = output.get("code", "")
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
        code = state["artifacts"].get("implement", {}).get("code", "")
        prompt = (f"Write pytest tests for this URL shortener code:\n\n{code[:1500]}\n\n"
                  "Use FastAPI's TestClient. Return ONLY test code for test_app.py "
                  "that imports from app. Cover shorten, redirect, click count. "
                  "No prose, no markdown fences.")
        return {"tests": strip_code_fences(call_llm(prompt))}

    def exit_gate(self, state, output):
        if "def test" not in output.get("tests", ""):
            return False, "no test functions found"
        return True, ""


class VerifyNode(Node):
    name = "verify"

    def entry_gate(self, state):
        if "implement" not in state["artifacts"] or "test" not in state["artifacts"]:
            return False, "need both code and tests to verify"
        return True, ""

    def run(self, state):
        code = state["artifacts"].get("implement", {}).get("code", "")
        tests = state["artifacts"].get("test", {}).get("tests", "")

        # Write code + tests to a temp dir and actually run pytest.
        tmp = tempfile.mkdtemp(prefix="verify_")
        with open(os.path.join(tmp, "app.py"), "w") as f:
            f.write(code)
        with open(os.path.join(tmp, "test_app.py"), "w") as f:
            f.write(tests)

        try:
            proc = subprocess.run(
                ["python3", "-m", "pytest", "test_app.py", "-q"],
                cwd=tmp, capture_output=True, text=True, timeout=60,
            )
            passed = proc.returncode == 0
            output_tail = (proc.stdout + proc.stderr)[-500:]
        except Exception as e:
            passed = False
            output_tail = f"pytest could not run: {e}"

        return {"result": "all tests pass" if passed else "tests failed",
                "passed": passed, "pytest_output": output_tail}

    def exit_gate(self, state, output):
        if not output.get("passed"):
            tail = output.get("pytest_output", "")[-200:]
            return False, f"tests did not pass: {tail}"
        return True, ""


class DocumentNode(Node):
    name = "document"

    def entry_gate(self, state):
        if "verify" not in state["artifacts"]:
            return False, "nothing verified to document"
        return True, ""

    def run(self, state):
        design = state["artifacts"].get("architect", {})
        prompt = (f"Write a short README for this URL shortener:\n{design}\n\n"
                  "Cover what it does, how to run it, and the endpoints. Under 150 words.")
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
        from core.policy import check_policy
        ok, reason = check_policy("tests_must_pass_before_release", state=state)
        if not ok:
            return False, reason
        return True, ""


class ContextRetrievalNode(Node):
    name = "context_retrieval"

    def entry_gate(self, state):
        if "requirement" not in state["artifacts"]:
            return False, "no change request to analyze"
        return True, ""

    def run(self, state):
        code = ""
        path = "shortener/app.py"
        if os.path.exists(path):
            with open(path) as f:
                code = f.read()
        else:
            code = "(no existing shortener found)"
        spec = state["artifacts"].get("requirement", {})
        prompt = (f"Existing URL shortener code:\n\n{code[:2000]}\n\n"
                  f"Change requested: {spec}\n\n"
                  "Identify which functions, endpoints, and data structures this "
                  "change impacts. Be specific. Under 150 words.")
        return {"impacted": call_llm(prompt), "existing_code_found": bool(code)}

    def exit_gate(self, state, output):
        if len(output.get("impacted", "")) < 20:
            return False, "impact analysis too thin"
        return True, ""


class ClarifyNode(Node):
    name = "clarify"

    def entry_gate(self, state):
        if "requirement" not in state["artifacts"]:
            return False, "nothing to clarify"
        return True, ""

    def run(self, state):
        spec = state["artifacts"].get("requirement", {})
        prompt = (f"This request is vague: {spec}\n\n"
                  "List the specific ambiguities to resolve, and the reasonable "
                  "default assumption for each. Format 'Ambiguity -> Assumption'. "
                  "Under 150 words.")
        return {"clarification": call_llm(prompt), "resolved_by": "logged assumptions"}

    def exit_gate(self, state, output):
        if "->" not in output.get("clarification", ""):
            return False, "no ambiguity/assumption pairs produced"
        return True, ""


REAL_NODES = {
    "requirement": RequirementNode,
    "plan": PlanNode,
    "architect": ArchitectNode,
    "implement": ImplementNode,
    "test": TestNode,
    "verify": VerifyNode,
    "document": DocumentNode,
    "release": ReleaseNode,
    "context_retrieval": ContextRetrievalNode,
    "clarify": ClarifyNode,
}
