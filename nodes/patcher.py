"""
patcher.py  —  real in-place patching for brownfield changes.

Edits the existing file surgically. Now also honors human REVISE feedback from
the approval gate (e.g. "drop the dashboard") as a hard instruction.
"""

import difflib
from nodes.llm import call_llm, strip_code_fences


def patch_file(existing_code, change_request, impact="", feedback=""):
    """Edit existing_code for change_request. Returns (new_code, diff_text).
    `feedback` is human guidance from the revise gate — honored strictly."""
    feedback_line = ""
    if feedback:
        feedback_line = (
            f"\n--- HUMAN REVISION INSTRUCTION (follow this strictly) ---\n{feedback}\n"
        )

    prompt = (
        "You are making a TARGETED change to an existing Python file. "
        "Make ONLY the requested change. Preserve all existing behavior, "
        "endpoints, and structure exactly. Do not rewrite unrelated code.\n\n"
        f"--- CHANGE REQUESTED ---\n{change_request}\n\n"
        f"--- IMPACT ANALYSIS ---\n{impact}\n"
        f"{feedback_line}\n"
        f"--- CURRENT FILE (app.py) ---\n{existing_code}\n\n"
        "Return the COMPLETE updated file with only the necessary change applied. "
        "No prose, no markdown fences."
    )
    new_code = strip_code_fences(call_llm(prompt))

    diff = difflib.unified_diff(
        existing_code.splitlines(keepends=True),
        new_code.splitlines(keepends=True),
        fromfile="app.py (before)",
        tofile="app.py (after)",
    )
    return new_code, "".join(diff)
