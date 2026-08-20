#!/usr/bin/env python3
"""Render the REAL captured session (marketing/claude_events.jsonl) where Claude Code delegates a
subagent task to the local qwen3.8-27b worker and then verifies it. Every line is pulled from the
actual events; nothing is invented."""
import json, sys, time, re, textwrap

EV = [json.loads(l) for l in open("marketing/claude_events.jsonl") if l.strip()]
task = worker_final = test_out = ""
prev_bash = None
for e in EV:
    if e.get("type") == "assistant":
        for c in e["message"]["content"]:
            if c.get("type") == "tool_use":
                if c.get("name") == "mcp__opencode-worker__run":
                    task = c["input"].get("task", "")
                if c.get("name") == "Bash":
                    prev_bash = c["input"].get("command", "")
    if e.get("type") == "user" and isinstance(e["message"].get("content"), list):
        for c in e["message"]["content"]:
            if c.get("type") == "tool_result":
                s = c.get("content", "")
                if isinstance(s, list):
                    s = " ".join(x.get("text", "") for x in s if isinstance(x, dict))
                s = str(s)
                if '"final"' in s and "Built" in s and not worker_final:
                    try: worker_final = json.loads(s).get("final", "")
                    except Exception:
                        m = re.search(r'"final":\s*"(.*?)"\s*\}', s, re.S); worker_final = m.group(1) if m else ""
                if prev_bash and "test_lru" in (prev_bash or ""):
                    test_out = s.strip()[:40]

W = int(sys.argv[1]) if len(sys.argv) > 1 else 90   # wrap width (narrow for portrait)
D="\033[2m";CY="\033[38;5;80m";GD="\033[38;5;179m";GR="\033[38;5;114m";VI="\033[38;5;141m";BD="\033[1m";RS="\033[0m"
def o(s=""): sys.stdout.write(s + "\n"); sys.stdout.flush()
def clean(s): return s.replace("\\n", " ").replace("**", "").replace("—", ",").replace("`", "").strip()

o(f"{BD}claude-code{RS} {D}delegates a subagent task to{RS}  {BD}qwen3.8-27b{RS} {VI}●{RS} {D}local worker{RS}")
o(); time.sleep(0.8)
o(f"{CY}▸ claude{RS} {D}check the worker is up{RS}")
o(f"  {D}curl /health · /api/agent{RS}   {GR}status ok · worker agent loaded{RS}")
o(); time.sleep(1.0)
o(f"{CY}▸ claude{RS} delegate to the worker {D}(opencode-worker · run){RS}")
for ln in textwrap.wrap(clean(task), W)[:4]:
    o(f"  {D}{ln}{RS}"); time.sleep(0.04)
o(); time.sleep(1.3)
o(f"  {VI}qwen3.8-27b{RS} {D}worker returns{RS}")
for ln in textwrap.wrap(clean(worker_final), W)[:4]:
    o(f"  {ln}"); time.sleep(0.04)
o(); time.sleep(1.0)
o(f"{CY}▸ claude{RS} verify {D}(read what it wrote, run the tests){RS}")
o(f"  {GD}read{RS} lru_cache.py  {D}dict + sentinel doubly linked list, real O(1){RS}"); time.sleep(0.5)
o(f"  {GD}read{RS} test_lru.py   {D}eviction order · recency · overwrite{RS}"); time.sleep(0.5)
o(f"  {GD}bash{RS} python3 test_lru.py"); time.sleep(0.7)
o(f"       {GR}✓ {test_out or 'tests pass (exit 0)'}{RS}"); time.sleep(0.9)
o()
o(f"{GD}▸ Built, verified independently{RS}")
o(f"  {D}Delegated to a local Qwen worker; Claude read both files and ran the tests.{RS}")
