"""Quick test of the policy engine — not part of the real system."""
from core.policy import check_policy

print("=== Security policy: no secrets in code ===")
clean = {"code": "def shorten(url): return hash(url)"}
dirty = {"code": "api_key = 'sk-12345'  # oops"}
print("  clean code ->", check_policy("no_secrets_in_code", output=clean))
print("  dirty code ->", check_policy("no_secrets_in_code", output=dirty))

print("\n=== Change-control policy: tests must pass before release ===")
passed = {"artifacts": {"verify": {"result": "all tests pass"}}}
failed = {"artifacts": {"verify": {"result": "1 test failing"}}}
missing = {"artifacts": {}}
print("  tests passed ->", check_policy("tests_must_pass_before_release", state=passed))
print("  tests failed ->", check_policy("tests_must_pass_before_release", state=failed))
print("  no verify    ->", check_policy("tests_must_pass_before_release", state=missing))
