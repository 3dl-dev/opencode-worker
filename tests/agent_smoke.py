#!/usr/bin/env python3
"""Prove the worker protocol is delivered via the OpenCode agent's system prompt, not prepended.

Three checks:
  1. The server loaded the `opencode-worker` agent, and its system prompt IS the protocol
     (distinctive protocol phrases present, full length), i.e. scripts/build_agent.py + a server
     restart wired the protocol in.
  2. A session started via the driver submits ONLY the task yet is bound to that agent
     (session.agent == the resolved agent), so the protocol reaches the worker with no prepend.
  3. The task still completes, ground-truthed on disk independent of the worker's self-report.

Prereqs (same as tests/smoke.py) PLUS: the agent must be compiled and loaded --
  python3 scripts/build_agent.py && restart `opencode serve` from the repo root.
Env: OPENCODE_BASE (default http://127.0.0.1:47611/api). Exit 0 on PASS.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from opencode_worker import OpenCodeWorker, DEFAULT_TARGET, resolve_artifacts

BASE = os.environ.get("OPENCODE_BASE", "http://127.0.0.1:47611/api")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WD = os.path.join(ROOT, ".work", "agent_smoke")
os.makedirs(WD, exist_ok=True)
for f in os.listdir(WD):
    try: os.remove(os.path.join(WD, f))
    except OSError: pass

AGENT = resolve_artifacts(DEFAULT_TARGET)["agent"]
PROTOCOL = os.path.join(ROOT, resolve_artifacts(DEFAULT_TARGET)["system_prompt"])
TASK = ("TASK: In your working directory create a file agent_smoke.txt containing exactly the "
        "word OK (uppercase). Then reply DONE only if the file was written.")

w = OpenCodeWorker(BASE)

# 1) The agent is loaded and its system prompt is the protocol.
raw = w._req("GET", "/agent")
agents = raw if isinstance(raw, list) else raw.get("agents", [])
match = next((a for a in agents if (a.get("id") or a.get("name")) == AGENT), None)
assert match, f"agent '{AGENT}' not loaded (have {[a.get('id') for a in agents]}); " \
              "run scripts/build_agent.py and restart opencode serve from the repo root"
system = match.get("system") or match.get("prompt") or ""
proto = open(PROTOCOL).read()
# distinctive protocol phrases, so a stub or a different prompt fails loudly
for phrase in ("honest-failure", "authoritative correction", "the checks are the authority"):
    assert phrase in system, f"agent system prompt missing protocol phrase: {phrase!r}"
assert len(system) > 0.9 * len(proto.strip()), \
    f"agent system prompt too short ({len(system)}) vs protocol ({len(proto.strip())})"
print(f"agent '{AGENT}' loaded; system prompt = protocol ({len(system)} chars)", flush=True)

# 2) Driver binds the agent; only the task is submitted (no protocol text).
sid = w.start(TASK, WD, target=DEFAULT_TARGET)
bound = w.session(sid).get("agent")
assert bound == AGENT, f"session agent is {bound!r}, expected {AGENT!r}"
print(f"session {sid} bound to agent {bound}", flush=True)

# drive it to completion with auto-approve, then 3) ground-truth on disk.
last = None
import time
t0 = time.time()
while time.time() - t0 < 260:
    for p in w.pending(sid):
        w.reply(sid, w.req_id(p), "once")
    st = w.overall_status(sid)
    if st != last: print("status:", st, flush=True); last = st
    if st in ("idle", "completed", "done", "error"): break
    time.sleep(3)

fin = w._last_assistant(sid)
print("final:", repr((fin or "")[:160]), flush=True)
path = os.path.join(WD, "agent_smoke.txt")
ok = os.path.exists(path) and open(path).read().strip().upper().startswith("OK")
print("GROUND-TRUTH agent_smoke.txt == OK:", ok, flush=True)
print("RESULT:", "PASS" if ok else "FAIL", flush=True)
sys.exit(0 if ok else 1)
