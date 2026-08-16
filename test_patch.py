"""Test the patcher on the real app.py — prove it edits surgically."""
from nodes.patcher import patch_file

with open("shortener/app.py") as f:
    existing = f.read()

new_code, diff = patch_file(existing, "Add a GET /health endpoint that returns {'status': 'ok'}")

print("=== DIFF (what changed) ===")
print(diff if diff else "(no changes)")
print("\n=== Did existing endpoints survive? ===")
print("has /shorten:", "/shorten" in new_code)
print("has /stats:", "/stats" in new_code)
print("has redirect:", "RedirectResponse" in new_code)
print("has NEW /health:", "/health" in new_code)
