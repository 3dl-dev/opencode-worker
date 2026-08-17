#!/usr/bin/env python3
"""opencode-worker MCP server: the Claude Code integration surface for the connector.

Wraps the model-neutral driver in `opencode_worker.py` as MCP tools so the Opus loop drives a
worker session through tool calls (cleaner than the Bash CLI, same inner call path). The tools
mirror the documented worker control surface: start / steer / pending / approve / status /
final / stop / run.

Subscription-safe: every tool talks only to the local `opencode serve` HTTP API. Touches no
Anthropic auth. The MODEL is a per-session variant passed on `start`/`run`, not a fixture;
Qwen3.8-27B (provider `mainframe-qwen38`) is the default target, nothing more.

Honest-grade discipline (invariant): the worker's "DONE" is a claim, not evidence. `final`
returns the worker's raw self-report; the caller (Opus) MUST verify the real result with its
own ground-truth check before treating the task as built. These tools never grade.

Transport: stdio (one server process per Claude Code session). Run:
  OPENCODE_BASE=http://127.0.0.1:47611/api python3 src/opencode_worker_mcp.py
Claude Code discovers it via the repo `.mcp.json`.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp.server.fastmcp import FastMCP

from opencode_worker import OpenCodeWorker, DEFAULT_MODEL, DEFAULT_TARGET, DEFAULT_SETTINGS, resolve_artifacts

BASE = os.environ.get("OPENCODE_BASE", "http://127.0.0.1:47611/api")
_worker = OpenCodeWorker(BASE)

mcp = FastMCP("opencode-worker")


def _target(provider: str, model: str, quant: str = "") -> dict:
    """Build the target. quant/settings default to the qwen target; harness=opencode, env=None."""
    return {"model": {"providerID": provider, "id": model},
            "quant": quant or DEFAULT_TARGET["quant"], "harness": "opencode",
            "settings": DEFAULT_SETTINGS, "env": None}


@mcp.tool()
def start(task: str, directory: str,
          provider: str = DEFAULT_MODEL["providerID"],
          model: str = DEFAULT_MODEL["id"], agent: str = "") -> dict:
    """Create a worker session for (provider, model) in `directory` and submit `task`.

    Returns {session, target, agent}. The session id (ses_...) is the handle for every other
    tool. This does not block for completion: poll `status`, service `pending`, and read `final`
    yourself. `directory` should be an absolute path the worker is allowed to edit in. The worker
    runs under an OpenCode agent whose system prompt is the protocol, so submit ONLY the task,
    not the protocol; `agent` defaults to the target's resolved agent (leave empty).
    """
    art = resolve_artifacts(_target(provider, model))
    sid = _worker.start(task, directory, target=_target(provider, model), agent=agent or None)
    return {"session": sid, "target": art["key"], "agent": agent or art.get("agent"),
            "deltas": art["deltas"]}


@mcp.tool()
def steer(session: str, message: str) -> dict:
    """Inject an authoritative mid-turn correction into the running worker turn (delivery=steer).

    Use this to redirect the worker without stopping it. The worker's protocol treats a steer as
    a correction to obey immediately. Returns {ok}.
    """
    _worker.steer(session, message)
    return {"ok": True}


@mcp.tool()
def pending(session: str) -> dict:
    """List permission asks currently blocking the worker.

    Returns {pending: [{req, action}]}. Each `req` is the id to pass to `approve`; `action` is a
    human label of what the worker wants to do (e.g. the tool + resources). An empty list means
    nothing is gated right now. A gated worker waits: it will not proceed until you `approve`.
    """
    items = [{"req": _worker.req_id(p), "action": _worker.describe(p)} for p in _worker.pending(session)]
    return {"pending": items}


@mcp.tool()
def approve(session: str, req: str, decision: str = "once") -> dict:
    """Answer a pending permission ask. `decision` is one of: once, always, reject.

    `once` allows this call, `always` allows it and future matching calls, `reject` denies it (a
    denial is a decision the worker must respect, not an obstacle for it to route around). `req`
    comes from `pending`. Returns {ok, decision}.
    """
    if decision not in ("once", "always", "reject"):
        raise ValueError("decision must be one of: once, always, reject")
    _worker.reply(session, req, decision)
    return {"ok": True, "decision": decision}


@mcp.tool()
def status(session: str) -> dict:
    """Report whether the worker turn is still running or has settled.

    Returns {status}: one of running, idle, completed, done, error. `idle`/`completed`/`done`
    mean the turn finished (read `final`); `error` means the turn failed (e.g. the model endpoint
    dropped), stop polling; `running` means keep polling and servicing `pending`.
    """
    return {"status": _worker.overall_status(session)}


@mcp.tool()
def final(session: str) -> dict:
    """Return the worker's latest assistant reply text (its self-report).

    Returns {final}. THIS IS A CLAIM, NOT EVIDENCE: a worker saying "DONE" does not mean the task
    is built. Before treating the task as complete, run your own ground-truth check on the real
    result (file on disk, test passing, service healthy). Never relabel a failing check as done.
    """
    return {"final": _worker._last_assistant(session) or ""}


@mcp.tool()
def stop(session: str) -> dict:
    """Interrupt the worker's running turn. Returns {ok}."""
    _worker.interrupt(session)
    return {"ok": True}


@mcp.tool()
def run(task: str, directory: str,
        provider: str = DEFAULT_MODEL["providerID"],
        model: str = DEFAULT_MODEL["id"],
        auto: str = "once", budget: int = 600, agent: str = "") -> dict:
    """One-shot: start a session, auto-answer every permission with `auto`, block until the turn
    settles or `budget` seconds elapse, then return {session, final}.

    Convenience for fire-and-forget with a fixed permission policy. It BLOCKS and auto-approves,
    so it forfeits the two things the stepwise tools give you: per-ask permission control and
    live mid-turn steer. Prefer start + poll for anything you want to supervise. `final` is still
    only the worker's claim: ground-truth it yourself. `auto` is once|always|reject. Submit only
    the task; `agent` defaults to the target's resolved agent (leave empty).
    """
    if auto not in ("once", "always", "reject"):
        raise ValueError("auto must be one of: once, always, reject")
    sid, fin = _worker.run(task, directory, target=_target(provider, model),
                           approve=lambda p: auto, budget=budget, agent=agent or None)
    return {"session": sid, "final": fin or ""}


if __name__ == "__main__":
    mcp.run(transport="stdio")
