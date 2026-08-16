"""
build.py  —  the front door. Type any requirement; it runs the pipeline with a
fresh run_id, saves the generated/patched code to disk, and warns before
overwriting existing work on a fresh build.

Usage:
    python3 build.py "make a url shortener"
    python3 build.py "add a click counter to the shortener"
    python3 build.py "make it more reliable"
"""

import sys
from datetime import datetime
from run import run_pipeline
from core.event_log import build_state
from core.overwrite_guard import confirm_overwrite

APP_PATH = "shortener/app.py"
TEST_PATH = "shortener/test_app.py"


def save_code(state, classification):
    arts = state["artifacts"]
    verify = arts.get("verify", {})
    # The code that passed: repaired/patched version if present, else implement.
    code = verify.get("repaired_code") or arts.get("implement", {}).get("code", "")
    tests = arts.get("test", {}).get("tests", "")

    if not code:
        print("\nNo code produced to save.")
        return

    if classification == "brownfield":
        # Patching preserves existing work by design — no overwrite warning.
        with open(APP_PATH, "w") as f:
            f.write(code)
        print(f"\nPatched {APP_PATH} (existing behavior preserved).")
    else:
        # Fresh build: guard against silently destroying existing work.
        if confirm_overwrite(APP_PATH):
            with open(APP_PATH, "w") as f:
                f.write(code)
            if tests:
                with open(TEST_PATH, "w") as f:
                    f.write(tests)
            print(f"\nWrote {APP_PATH}")
        else:
            print(f"\nKept existing {APP_PATH} (not overwritten).")


def main():
    if len(sys.argv) < 2:
        print('Usage: python3 build.py "your requirement here"')
        raise SystemExit(1)

    requirement = " ".join(sys.argv[1:])
    run_id = "run-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")

    print(f"\n=== NEW REQUEST ===")
    print(f'Requirement: "{requirement}"')
    print(f"Run ID: {run_id}\n")

    log, graph, plan_artifact = run_pipeline(requirement, run_id)
    classification = plan_artifact["classification"]

    print(f"Classified as: {classification}")
    print("\nPipeline:")
    for t in graph.all():
        print(f"  {t.name:16} -> {t.status}")

    state = build_state(log)
    arts = state["artifacts"]

    if arts.get("implement", {}).get("diff"):
        print("\n=== PATCH DIFF ===")
        print(arts["implement"]["diff"])

    if arts.get("verify", {}).get("passed"):
        print("\n✓ Verified: tests pass.")
    elif "verify" in arts:
        print("\n✗ Verification did not pass.")

    save_code(state, classification)
    print(f"\nRun complete. Run ID: {run_id}")


if __name__ == "__main__":
    main()
