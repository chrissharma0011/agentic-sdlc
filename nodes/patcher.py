"""
patcher.py  —  real in-place patching for brownfield changes.

Instead of regenerating from scratch, we EDIT the existing file: give the LLM
the exact current code and instruct it to make ONLY the requested change,
preserving everything else. Then we produce a real diff so the change is
provably surgical (a reviewer sees exactly which lines moved).
"""

import difflib
from nodes.llm import call_llm, strip_code_fences


def patch_file(existing_code: str, change_request: str, impact: str = "") -> tuple[str, str]:
    """
    Edit existing_code to satisfy change_request. Returns (new_code, diff_text).
    The prompt forces a surgical edit: return the FULL file, change only what's needed.
    """
    prompt = (
        "You are making a TARGETED change to an existing Python file. "
        "Make ONLY the requested change. Preserve all existing behavior, "
        "endpoints, and structure exactly. Do not rewrite or reformat unrelated code.\n\n"
        f"--- CHANGE REQUESTED ---\n{change_request}\n\n"
        f"--- IMPACT ANALYSIS ---\n{impact}\n\n"
        f"--- CURRENT FILE (app.py) ---\n{existing_code}\n\n"
        "Return the COMPLETE updated file with only the necessary change applied. "
        "No prose, no markdown fences."
    )
    new_code = strip_code_fences(call_llm(prompt))

    # Produce a real unified diff so the change is visible and provably surgical.
    diff = difflib.unified_diff(
        existing_code.splitlines(keepends=True),
        new_code.splitlines(keepends=True),
        fromfile="app.py (before)",
        tofile="app.py (after)",
    )
    diff_text = "".join(diff)
    return new_code, diff_text
