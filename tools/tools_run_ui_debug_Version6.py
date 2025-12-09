#!/usr/bin/env python3
# Debug runner: directly calls ui.run with device callbacks and logs entry/exit.
# Run from project root: python tools/run_ui_debug.py

import logging
import time
import sys
from pathlib import Path

# ensure project root is on sys.path (should be automatically when run from project root)
print("cwd:", Path.cwd())
print("sys.path[0]:", sys.path[0])

logging.basicConfig(level=logging.INFO)
_LOG = logging.getLogger("run_ui_debug")

# Import the modules
try:
    import device
    import ui
except Exception as e:
    _LOG.exception("Failed to import device or ui: %s", e)
    sys.exit(1)

# Sanity checks
_LOG.info("Imported device from: %s", getattr(device, "__file__", "<unknown>"))
_LOG.info("Imported ui from: %s", getattr(ui, "__file__", "<unknown>"))
_LOG.info("ui.run exists: %s", hasattr(ui, "run"))

# Verify ui.run signature
try:
    import inspect
    if hasattr(ui, "run"):
        _LOG.info("ui.run signature: %s", inspect.signature(ui.run))
except Exception:
    pass

# Prepare callbacks to pass (use device's functions)
callbacks = {
    "get_counts": getattr(device, "get_counts", None),
    "get_override_info": getattr(device, "get_override_info", None),
    "get_upload_info": getattr(device, "get_upload_info", None),
    "get_latest_sensor": getattr(device, "get_latest_sensor", None),
    "calculate_avg_smiley": getattr(device, "calculate_avg_smiley", None),
    "pct_round": getattr(device, "pct_round", None),
    "on_vote": getattr(device, "on_vote", None),
    "on_upload": getattr(device, "on_upload", None),
}

_LOG.info("Callbacks prepared; existence: %s", {k: (v is not None) for k, v in callbacks.items()})

# Check we have all callbacks
missing = [k for k, v in callbacks.items() if v is None]
if missing:
    _LOG.error("Missing callbacks in device module: %s", missing)
    print("Please ensure device.py exports these functions. Exiting.")
    sys.exit(1)

# Call ui.run and time how long it runs (it should block until you close the window)
try:
    _LOG.info("Entering ui.run (UI should open now). Close the window to continue.")
    start = time.time()
    ui.run(
        callbacks["get_counts"],
        callbacks["get_override_info"],
        callbacks["get_upload_info"],
        callbacks["get_latest_sensor"],
        callbacks["calculate_avg_smiley"],
        callbacks["pct_round"],
        callbacks["on_vote"],
        callbacks["on_upload"],
    )
    duration = time.time() - start
    _LOG.info("ui.run returned after %.1f seconds", duration)
except Exception as e:
    _LOG.exception("ui.run raised an exception: %s", e)
    raise