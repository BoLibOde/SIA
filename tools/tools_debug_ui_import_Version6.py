#!/usr/bin/env python3
# Debug helper to diagnose why "module 'ui' has no attribute 'run'" or similar import issues.
# Run from the project root: python tools/debug_ui_import.py
#
# It prints:
# - current working directory and sys.path
# - whether a ui.py exists in the project root (and its path)
# - which ui module Python actually imports (ui.__file__)
# - whether ui.run exists, and its signature (if present)
# - first N lines of the ui.py source (for quick inspection)
# - checks for likely circular import (ui importing device at module level)
# - attempts an importlib.reload(ui) and repeats the checks
#
# This is a read-only helper; it does not call ui.run or start Pygame.

import os
import sys
import importlib
import inspect
import traceback
from pathlib import Path

PRINT_SOURCE_LINES = 80

def print_header(title):
    print("\n" + "="*80)
    print(title)
    print("="*80)

def list_sys_path():
    print_header("Working directory and sys.path")
    print("cwd:", os.getcwd())
    for i, p in enumerate(sys.path):
        print(f"{i:02d}: {p}")

def find_local_ui_file():
    print_header("Looking for ui.py files in project tree (project root and immediate files)")
    cwd = Path.cwd()
    candidates = list(cwd.glob("ui.py")) + list(cwd.glob("*/ui.py")) + list(cwd.glob("**/ui.py"))
    # deduplicate by resolved path
    seen = set()
    unique = []
    for p in candidates:
        try:
            rp = str(p.resolve())
        except Exception:
            rp = str(p)
        if rp not in seen:
            seen.add(rp)
            unique.append(p)
    if not unique:
        print("No ui.py found under project root (cwd).")
    else:
        for p in unique:
            print("Found ui.py:", p, " -> ", str(p.resolve()))
    return unique

def import_and_inspect_ui():
    print_header("Importing module named 'ui'")
    try:
        # If 'ui' already loaded, show location
        if 'ui' in sys.modules:
            print("ui already in sys.modules ->", getattr(sys.modules['ui'], "__file__", "<built-in/module>"))
        ui = importlib.import_module("ui")
        print("Imported ui:", getattr(ui, "__file__", "<unknown>"))
    except Exception as e:
        print("Failed to import ui (exception). Traceback:")
        traceback.print_exc()
        return None

    try:
        print_header("ui module quick attributes")
        print("module file:", getattr(ui, "__file__", None))
        print("has attribute 'run':", hasattr(ui, "run"))
        if hasattr(ui, "run"):
            try:
                sig = inspect.signature(ui.run)
                print("ui.run signature:", sig)
            except Exception as ee:
                print("Could not get signature of ui.run:", ee)
        print("dir(ui) (top-level names):")
        names = [n for n in dir(ui) if not n.startswith("__")]
        print(", ".join(names))
    except Exception:
        traceback.print_exc()

    # Try to read the source file and show first lines for inspection
    ui_file = getattr(ui, "__file__", None)
    if ui_file:
        try:
            print_header(f"First {PRINT_SOURCE_LINES} lines of {ui_file}")
            with open(ui_file, "r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f):
                    if i >= PRINT_SOURCE_LINES:
                        break
                    # show line number and content
                    print(f"{i+1:03d}: {line.rstrip()}")
        except Exception as e:
            print("Failed to read ui file:", e)

    # Heuristic: check if ui source imports device at top-level (possible circular import)
    if ui_file:
        try:
            with open(ui_file, "r", encoding="utf-8", errors="replace") as f:
                top = "".join([next(f) for _ in range(40)])  # first ~40 lines
            if "import device" in top or "from device" in top:
                print_header("Potential circular import warning")
                print("ui.py appears to import device at module level (first ~40 lines).")
                print("This can cause a circular import: device -> ui and ui -> device.")
                print("If ui imports device at top-level, move that import inside run() or remove it and use callbacks.")
        except StopIteration:
            pass
        except Exception:
            pass

    return ui

def try_reload(ui_module):
    print_header("Attempting importlib.reload(ui) to refresh module (if already loaded)")
    try:
        ui2 = importlib.reload(ui_module)
        print("Reloaded ui module:", getattr(ui2, "__file__", "<unknown>"))
        print("has run after reload:", hasattr(ui2, "run"))
        if hasattr(ui2, "run"):
            try:
                print("ui.run signature after reload:", inspect.signature(ui2.run))
            except Exception:
                pass
        return ui2
    except Exception:
        print("Reload failed. Traceback:")
        traceback.print_exc()
        return None

def main():
    list_sys_path()
    found = find_local_ui_file()

    ui = import_and_inspect_ui()
    if ui is None:
        print_header("Attempt fallback: try loading ui.py by path if found in project")
        if found:
            # try to load the first discovered ui.py as a module using importlib.machinery
            from importlib.machinery import SourceFileLoader
            try:
                p = str(found[0].resolve())
                print("Loading", p, "as module 'ui_local_debug'")
                ui_local = SourceFileLoader("ui_local_debug", p).load_module()
                print("Loaded ui_local_debug, has run:", hasattr(ui_local, "run"))
                if hasattr(ui_local, "run"):
                    try:
                        print("Signature:", inspect.signature(ui_local.run))
                    except Exception:
                        pass
            except Exception:
                print("Failed to load ui.py via SourceFileLoader. Traceback:")
                traceback.print_exc()
        else:
            print("No local ui.py to attempt loading.")
    else:
        # If ui imported, attempt reload and re-check
        ui2 = try_reload(ui)
        if ui2 and hasattr(ui2, "run"):
            print_header("ui.run appears present after reload. Done.")
            return

    print_header("Summary / next steps")
    print("1) Ensure the ui.py you edited is the one Python imports. The debug output above shows ui.__file__ if import succeeded.")
    print("2) If ui.__file__ points to a different file, fix your working directory / PYTHONPATH or remove that conflicting module.")
    print("3) If ui.py imports device at module level (circular import), move that import into run() or stop importing device there; use the callback approach.")
    print("4) If you want, paste the output of this script here (the whole terminal output) and I will point to the exact mismatch.")
    print("\nDone.")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)