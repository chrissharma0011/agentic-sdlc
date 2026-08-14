"""
policy.py  —  guardrails enforced AS CODE, checked at gates.

A policy is a named rule that inspects state/output and returns (ok, reason).
Policies are checked cross-cutting AT GATES, not as a separate node that could
be routed around — a rule enforced at every relevant gate cannot be bypassed.
"""


def no_secrets_in_code(output):
    """SECURITY: produced code must not contain hardcoded secrets."""
    code = str(output.get("code", ""))
    banned = ["sk-", "password =", "api_key =", "AKIA", "secret ="]
    for token in banned:
        if token in code:
            return False, f"possible hardcoded secret found: '{token}'"
    return True, ""


def tests_must_pass_before_release(state):
    """CHANGE-CONTROL: cannot release unless verify recorded a pass."""
    verify = state.get("artifacts", {}).get("verify")
    if not verify:
        return False, "no verify result on the blackboard — cannot release"
    result = str(verify.get("result", "")).lower()
    if "pass" not in result:
        return False, f"verify did not pass — cannot release (saw: {verify})"
    return True, ""


POLICIES = {
    "no_secrets_in_code": no_secrets_in_code,
    "tests_must_pass_before_release": tests_must_pass_before_release,
}


def check_policy(name, **kwargs):
    """Run one policy by name. Returns (ok, reason)."""
    policy = POLICIES[name]
    return policy(**kwargs)
