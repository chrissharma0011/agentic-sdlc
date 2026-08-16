"""
overwrite_guard.py  —  safety net so a new build never silently destroys
existing work. Before greenfield overwrites shortener/app.py, ask the human.
"""

import os


def confirm_overwrite(path="shortener/app.py"):
    if not os.path.exists(path):
        return True
    print("\n" + "!" * 60)
    print(f"  WARNING: {path} already exists.")
    print("  A new build will OVERWRITE the existing shortener.")
    print("!" * 60)
    choice = input("  Overwrite existing work? (yes/no): ").strip().lower()
    return choice in ("yes", "y")
