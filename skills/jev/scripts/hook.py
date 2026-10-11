#!/usr/bin/env python3
"""Tiny hook launcher: check the on/off switch before loading jev.py, so a switched-off hook
costs one small file read instead of importing the whole client on every prompt."""
import json
import os
import sys
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else ""
switch = {"prompt": "router", "permission": "perms"}.get(mode)
try:
    home = Path(os.environ.get("JEV_HOME") or Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "jev")
    on = bool(json.loads((home / "state.json").read_text()).get(switch))
except Exception:
    on = False
if not switch or not on:
    sys.exit(0)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jev  # noqa: E402

sys.exit(jev.hook_prompt() if mode == "prompt" else jev.hook_permission())
