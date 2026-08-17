#!/usr/bin/env python3
"""Canonical runnable smoke test for the opencode-worker connector.

Confirms the whole path works: create a Qwen-pinned OpenCode session, run a real agentic task
under the protocol, auto-approve any permission gate, then verify the result on disk
independent of the model's self-report (the honest grade).

Prereqs:
  1. `opencode serve --port 47611 --hostname 127.0.0.1 &`
  2. A served model + a provider in ~/.config/opencode/opencode.json (default target:
     provider mainframe-qwen38, model qwen3.8-27b). Bring the model up if needed and free it
     when done (see CLAUDE.md).
Env: OPENCODE_BASE (default http://127.0.0.1:47611/api).
Exit 0 on PASS.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from opencode_worker import OpenCodeWorker, DEFAULT_TARGET, resolve_artifacts

BASE = os.environ.get("OPENCODE_BASE", "http://127.0.0.1:47611/api")
WD = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".work", "smoke"))
os.makedirs(WD, exist_ok=True)
for f in os.listdir(WD):
    try: os.remove(os.path.join(WD, f))
    except OSError: pass

PROTO = ("You are an OpenCode worker under a strict protocol. Do exactly the task and nothing "
         "more. The outcome is binary: reply DONE only if the required result is actually "
         "present; otherwise reply HONEST-FAILURE. Never claim success on a failing check.")
TASK = ("TASK: In your working directory create a file smoke.txt containing exactly the word "
        "OK (uppercase). Then reply DONE only if the file was written.")

w = OpenCodeWorker(BASE)
print("target:", resolve_artifacts(DEFAULT_TARGET)["key"], flush=True)
sid, final = w.run(PROTO + "\n\n" + TASK, WD, target=DEFAULT_TARGET,
                   approve=lambda p: "once", budget=260)
p = os.path.join(WD, "smoke.txt")
ok = os.path.exists(p) and open(p).read().strip().upper().startswith("OK")
print("session:", sid)
print("final:", repr((final or "")[:160]))
print("GROUND-TRUTH smoke.txt == OK:", ok)
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
