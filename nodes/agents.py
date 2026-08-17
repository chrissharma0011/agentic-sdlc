"""
agents.py  —  real LLM-backed nodes with a SHARED CONTRACT.

The Architect emits an explicit contract (endpoints, status codes, shapes).
Implement builds TO the contract; Test asserts AGAINST the same contract.
They never see each other's code, but share one spec -> they align.
Verify runs real pytest and self-heals the code toward the frozen tests.
"""

import os
import json
import subprocess
import tempfile
from core.node import Node
from nodes.llm import call_llm, strip_code_fences

REPAIR_BUDGET = 3

# The shared contract for the URL shortener. The Architect commits to this;
# Implement and Test both bind to it. This is the single source of truth that
# stops code and tests from drifting apart.
SHORTENER_CONTRACT = {
    "endpoints": [
        {"method": "POST", "path": "/shorten",
         "request": {"long_url": "string"},
         "response": {"short_code": "string"},
         "status": 200},
        {"method": "GET", "path": "/{short_code}",
         "behavior": "return RedirectResponse to the long URL",
         "status": 307,
         "not_found_status": 404},
        {"method": "GET", "path": "/stats/{short_code}",
         "response": {"clicks": "integer"},
         "status": 200,
         "not_found_status": 404},
    ],
    "storage": "in-memory dict, no database",
    "notes": "Use JSON request bodies (not form data). Redirect uses status 307.",
}

CONTRACT_TEXT = json.dumps(SHORTENER_CONTRACT, indent=2)


def _run_pytest(code, tests):
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
        return proc.returncode == 0, (proc.stdout + proc.stderr)[-800:]
    except Exception as e:
        return False, f"pytest could not run: {e}"


def _repair_code(code, tests, error):
    prompt = (
        "This Python code fails its tests. Fix it.\n\n"
        f"--- CONTRACT (source of truth) ---\n{CONTRACT_TEXT}\n\n"
        f"--- CURRENT CODE ---\n{code}\n\n"
        f"--- TESTS IT MUST PASS (do not change these) ---\n{tests}\n\n"
        f"--- PYTEST FAILURE ---\n{error}\n\n"
        "Return the CORRECTED app.py that passes these tests and matches the "
        "contract. Change as little as possible. No prose, no fences."
    )
    return strip_code_fences(call_llm(prompt))


class RequirementNode(Node):
    name = "requirement"

    def run(self, state):
        raw = state.get("raw_requirement", "")
        prompt = (f"Turn this request into a clear engineering spec:\n'{raw}'\n\n"
                  "State what to build, key features, acceptance criteria. Under 120 words.")
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
        prompt = (f"Given this spec:\n{spec}\n\nList concrete engineering tasks in "
                  "order, as short bullets. Under 100 words.")
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
        # The Architect DERIVES the contract from the spec (agent-derived source
        # of truth). If this is a CHANGE to existing code that introduces new
        # endpoints, the contract is EXTENDED so implement, patch, and test all
        # bind to the same evolved contract (prevents behavior drift on new paths).
        contract = self._derive_contract(spec)
        change_text = "%s %s" % (spec.get("raw", ""), spec.get("spec", ""))
        existing = "context_retrieval" in state["artifacts"]  # brownfield/patch path
        if existing:
            contract = self._extend_contract_for_change(contract, change_text)
        prompt = (f"Design a URL shortener for this spec:\n{spec}\n\n"
                  f"It must implement this contract:\n{json.dumps(contract, indent=2)}\n\n"
                  "Write a 100-word design describing app.py implementing this "
                  "contract. Name the file app.py.")
        design_text = call_llm(prompt)
        return {"design": design_text, "contract": contract}

    def _extend_contract_for_change(self, contract, change_text):
        """If a brownfield change introduces new endpoint(s), add them to the
        contract so implement/patch/test all agree on the new behavior. If the
        change touches only existing endpoints, the contract is returned
        unchanged. Failures leave the contract untouched (safe)."""
        try:
            existing_paths = [e.get("path") for e in contract.get("endpoints", [])]
            prompt = (
                "You maintain an API contract. Here is the current contract:\n"
                f"{json.dumps(contract, indent=2)}\n\n"
                f"A change was requested:\n{change_text}\n\n"
                "If the change adds a NEW endpoint not already in the contract, "
                "return ONLY a JSON array of the new endpoint object(s) to ADD, "
                'each as {"method","path","response","status"}. Pin exact '
                "response field names and status codes. If the change only affects "
                "EXISTING endpoints (or adds a field to one), return an empty array []. "
                "Return ONLY the JSON array, no prose, no fences."
            )
            raw = strip_code_fences(call_llm(prompt))
            additions = json.loads(raw)
            if not isinstance(additions, list) or not additions:
                return contract  # nothing new; existing-endpoint change
            merged = dict(contract)
            merged["endpoints"] = list(contract.get("endpoints", []))
            for ep in additions:
                if isinstance(ep, dict) and ep.get("path") not in existing_paths:
                    merged["endpoints"].append(ep)
            return merged
        except Exception:
            return contract  # any failure -> leave contract unchanged (safe)

    def _derive_contract(self, spec):
        """Ask the LLM to emit the API contract as JSON from the spec, pinning the
        EXACT response field names so implement and test cannot drift. Falls back
        to the fully-specified reference contract if the derived one is malformed
        or missing required fields (defensive + reliable)."""
        prompt = (
            "You are an API architect. From this spec, emit a JSON contract for a "
            "URL shortener API. Return ONLY valid JSON (no prose, no fences). "
            "You MUST use these EXACT field names so code and tests agree:\n"
            '  - POST /shorten : request {"long_url": "string"} -> response '
            '{"short_code": "string"}, status 200\n'
            '  - GET /{short_code} : redirect (RedirectResponse), status 307, '
            "404 if unknown\n"
            '  - GET /stats/{short_code} : response {"clicks": "integer"}, status '
            "200, 404 if unknown\n"
            'Shape: {"endpoints":[{"method","path","request","response","status"}],'
            '"storage":"in-memory dict"}\n\nSpec:\n' + str(spec)
        )
        try:
            raw = strip_code_fences(call_llm(prompt))
            derived = json.loads(raw)
            paths = {e.get("path") for e in derived.get("endpoints", [])}
            required = {"/shorten", "/{short_code}", "/stats/{short_code}"}
            if not required.issubset(paths):
                return SHORTENER_CONTRACT
            # Validate the exact response fields are present; else use reference.
            fields = json.dumps(derived)
            if "short_code" not in fields or "clicks" not in fields:
                return SHORTENER_CONTRACT
            return derived
        except Exception:
            return SHORTENER_CONTRACT

    def exit_gate(self, state, output):
        design = output.get("design", "")
        contract = output.get("contract")
        if ".py" not in design:
            return False, "design does not name any concrete file"
        if not contract or not contract.get("endpoints"):
            return False, "no valid contract derived"
        return True, ""


class ImplementNode(Node):
    name = "implement"

    def entry_gate(self, state):
        if "architect" not in state["artifacts"]:
            return False, "no design to implement"
        return True, ""

    def run(self, state):
        # Bind to the contract, not to any test.
        prompt = (
            "Implement a URL shortener as a single FastAPI file app.py.\n\n"
            f"You MUST match this contract exactly:\n{json.dumps(state['artifacts'].get('architect', {}).get('contract', SHORTENER_CONTRACT), indent=2)}\n\n"
            "Use JSON request bodies. POST /shorten returns {\"short_code\": ...}. "
            "GET /stats/{short_code} returns {\"clicks\": ...}. The redirect endpoint "
            "returns RedirectResponse (status 307). Use these EXACT field names. "
            "IMPORTANT error paths from the contract: for an UNKNOWN short_code, "
            "BOTH GET /{short_code} and GET /stats/{short_code} MUST raise "
            "HTTPException(status_code=404). Implement exactly the endpoints in the "
            "contract and no others. "
            "Use an in-memory dict for storage. "
            "Return ONLY the code for app.py. No prose, no markdown fences."
        )
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
        # Bind to the SAME contract, independently of the implementation code.
        prompt = (
            "Write pytest tests for a URL shortener using FastAPI TestClient.\n\n"
            f"Test against this contract exactly:\n{json.dumps(state['artifacts'].get('architect', {}).get('contract', SHORTENER_CONTRACT), indent=2)}\n\n"
            "Import the app from app (import app). Use JSON bodies. "
            "POST /shorten returns {\"short_code\": ...}; GET /stats/{short_code} "
            "returns {\"clicks\": ...}. Assert these EXACT field names. "
            "CRITICAL for the redirect test: create the client with "
            "TestClient(app, follow_redirects=False) and assert status_code == 307 "
            "and the 'location' header equals the long URL. "
            "Test ONLY the behaviors declared in the contract above and NOTHING "
            "else. Do NOT invent endpoints, fields, or status codes that are not "
            "in the contract (no health/readiness/503/500 tests, no auth tests). "
            "Where the contract gives a not_found_status of 404, add a test that an "
            "UNKNOWN short_code returns 404 for that endpoint. "
            "Cover: shorten (200), redirect (307), stats clicks (200), and the "
            "404 not-found paths the contract declares. "
            "Return ONLY test code for test_app.py. No prose, no fences."
        )
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
        # Prefer repaired code from a dynamic re-plan, else the original implement.
        repair_art = state["artifacts"].get("repair", {})
        code = repair_art.get("code") or state["artifacts"].get("implement", {}).get("code", "")
        tests = state["artifacts"].get("test", {}).get("tests", "")
        passed, output = _run_pytest(code, tests)
        repairs = 0
        while not passed and repairs < REPAIR_BUDGET:
            repairs += 1
            code = _repair_code(code, tests, output)
            passed, output = _run_pytest(code, tests)
        return {"result": "all tests pass" if passed else "tests failed",
                "passed": passed, "repairs_used": repairs,
                "repaired_code": code if repairs > 0 else None,
                "pytest_output": output}

    def exit_gate(self, state, output):
        if not output.get("passed"):
            return False, f"tests did not pass after repairs: {output.get('pytest_output','')[-200:]}"
        return True, ""


class DocumentNode(Node):
    name = "document"

    def entry_gate(self, state):
        if "verify" not in state["artifacts"]:
            return False, "nothing verified to document"
        return True, ""

    def run(self, state):
        prompt = (f"Write a short README for a URL shortener with this contract:\n"
                  f"{CONTRACT_TEXT}\n\nCover what it does, how to run it, the "
                  "endpoints. Under 150 words.")
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
                  "List specific ambiguities and the reasonable default assumption "
                  "for each. Format 'Ambiguity -> Assumption'. Under 150 words.")
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


class PatchImplementNode(Node):
    """Brownfield implement: PATCH the existing app.py surgically, not regenerate."""
    name = "implement"

    def entry_gate(self, state):
        if "architect" not in state["artifacts"]:
            return False, "no design to implement"
        return True, ""

    def run(self, state):
        import os
        from nodes.patcher import patch_file

        path = "shortener/app.py"
        existing = ""
        if os.path.exists(path):
            with open(path) as f:
                existing = f.read()

        change = state["artifacts"].get("requirement", {}).get("raw", "")
        impact = state["artifacts"].get("context_retrieval", {}).get("impacted", "")

        feedback = state["artifacts"].get("approval", {}).get("feedback", "")
        # Pass the (possibly extended) contract so the patch honors declared
        # behavior for any new endpoints — keeps patch and tests aligned.
        contract = state["artifacts"].get("architect", {}).get("contract", {})
        new_code, diff = patch_file(existing, change, impact, feedback, contract)
        return {"code": new_code, "diff": diff, "patched": True}

    def exit_gate(self, state, output):
        code = output.get("code", "")
        if "def " not in code and "@app" not in code:
            return False, "patched output does not look like real code"
        # A patch that changed nothing is suspicious.
        if not output.get("diff", "").strip():
            return False, "patch produced no changes"
        return True, ""
