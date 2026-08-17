#!/usr/bin/env python3
"""End-to-end smoke test for the opencode-worker MCP server.

Proves the MCP surface works over its real stdio transport, not just the library underneath:
spawn the server as Claude Code would, list its tools, then drive a real Qwen task through the
stepwise tools (start -> status -> pending/approve -> final) and ground-truth the result on disk,
independent of the worker's self-report (the honest grade).

Prereqs (same as tests/smoke.py):
  1. `opencode serve --port 47611 --hostname 127.0.0.1 &`
  2. A served model + provider in opencode.json (default target: mainframe-qwen38 / qwen3.8-27b).
Env: OPENCODE_BASE (default http://127.0.0.1:47611/api). Exit 0 on PASS.
"""
import os, sys, json, asyncio

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
SERVER = os.path.join(ROOT, "src", "opencode_worker_mcp.py")
BASE = os.environ.get("OPENCODE_BASE", "http://127.0.0.1:47611/api")
WD = os.path.join(ROOT, ".work", "mcp_smoke")

EXPECTED_TOOLS = {"start", "steer", "pending", "approve", "status", "final", "stop", "run"}
TASK = ("You are an OpenCode worker under a strict protocol. Do exactly the task and nothing "
        "more; reply DONE only if the result is actually present, else HONEST-FAILURE.\n\n"
        "TASK: In your working directory create a file mcp_smoke.txt containing exactly the word "
        "OK (uppercase). Then reply DONE only if the file was written.")


def _payload(result):
    """Unwrap a CallToolResult into the tool's dict return, surfacing tool errors readably."""
    if getattr(result, "isError", False):
        text = next((c.text for c in result.content if getattr(c, "type", None) == "text"), "")
        raise RuntimeError(f"MCP tool error: {text}")
    if getattr(result, "structuredContent", None):
        return result.structuredContent
    for c in result.content:
        if getattr(c, "type", None) == "text":
            return json.loads(c.text)
    return {}


async def main():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    os.makedirs(WD, exist_ok=True)
    for f in os.listdir(WD):
        try: os.remove(os.path.join(WD, f))
        except OSError: pass

    env = dict(os.environ, OPENCODE_BASE=BASE)
    params = StdioServerParameters(command=sys.executable, args=[SERVER], env=env)

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1) Tool surface is what the integration promises.
            listed = {t.name for t in (await session.list_tools()).tools}
            missing = EXPECTED_TOOLS - listed
            assert not missing, f"MCP server missing tools: {missing} (has {listed})"
            print("tools:", sorted(listed), flush=True)

            # honest-grade discipline must be stated where it matters: `final` returns a claim.
            final_desc = next(t.description for t in (await session.list_tools()).tools
                              if t.name == "final")
            assert "not evidence" in final_desc.lower() or "claim" in final_desc.lower(), \
                "final tool must document that its output is a claim, not evidence"

            # 2) Drive a real task through the stepwise tools, over the wire.
            started = _payload(await session.call_tool("start", {"task": TASK, "directory": WD}))
            sid = started["session"]
            print("session:", sid, "target:", started.get("target"), flush=True)

            deadline = 260
            step = 3
            elapsed = 0
            st = "running"
            while elapsed < deadline:
                pend = _payload(await session.call_tool("pending", {"session": sid}))["pending"]
                for p in pend:
                    dec = _payload(await session.call_tool(
                        "approve", {"session": sid, "req": p["req"], "decision": "once"}))
                    print("approved:", p["action"], "->", dec.get("decision"), flush=True)
                st = _payload(await session.call_tool("status", {"session": sid}))["status"]
                if st in ("idle", "completed", "done", "error"):
                    break
                await asyncio.sleep(step)
                elapsed += step

            fin = _payload(await session.call_tool("final", {"session": sid}))["final"]
            print("status:", st, flush=True)
            print("final:", repr((fin or "")[:160]), flush=True)

    # 3) Honest grade: verify on disk, independent of the worker's DONE.
    p = os.path.join(WD, "mcp_smoke.txt")
    ok = os.path.exists(p) and open(p).read().strip().upper().startswith("OK")
    print("GROUND-TRUTH mcp_smoke.txt == OK:", ok, flush=True)
    print("RESULT:", "PASS" if ok else "FAIL", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
