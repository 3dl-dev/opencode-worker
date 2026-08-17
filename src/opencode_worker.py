#!/usr/bin/env python3
"""opencode_worker v0 - drive an OpenCode worker session over `opencode serve`.

The worker is an OpenCode session; the MODEL is a per-session variant, not a fixture. This
driver is model-neutral: pass any provider/model configured in opencode.json. Qwen3.8-27B
(provider `mainframe-qwen38`) is target #1, the default here, nothing more.

Subscription-safe: talks only to the local opencode server. Touches no Anthropic auth.
This is the reusable inner call path the MCP surface (worker.start/steer/approve/status/stop)
and the graded co-optimization loop both wrap. Proof-first in scratch; moves to hoistable
once validated live.
"""
import os, json, time, re, hashlib, urllib.request, urllib.error

# Repo root, so resolve_artifacts can read a pack's earned grade regardless of caller cwd.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A TARGET is (model, quant, harness, settings, env); every axis is a parameter, none a fixture.
# opencode is harness #1 and qwen3.8-27b @ Q6_K+MTP is model #1 - defaults only. `model` is the
# wire-safe object OpenCode accepts on POST /session ({providerID,id,variant} only); quant and
# settings are SIBLING axes (OpenCode rejects extra keys inside `model`), so the worker pack can
# still be keyed by them.
DEFAULT_MODEL = {"providerID": "mainframe-qwen38", "id": "qwen3.8-27b"}
# Ground truth of the live endpoint (confirmed via /props model_path + mainframe/docs/ops/
# qwen38-serve.md): the served weights are Qwen3.8-27B-**Q6_K** imatrix GGUF, run with MTP
# speculative decoding (`--spec-type draft-mtp`, ~47 tok/s, draft acceptance 0.69). NOT Q8_0 -
# the unsloth Q8_0 carries no MTP head. The pack is quant/settings sensitive, so this must match.
# Serving/behavior settings that key the pack. `permission` is OUR-side gating: the mutating and
# external tools ask (the driver decides), read-only tools stay allowed so the worker can explore
# without gate spam. `spec_decode` records the MTP draft mode (lossless speedup, part of the
# declared config). Compiled into the agent frontmatter by scripts/build_agent.py.
DEFAULT_SETTINGS = {
    "context": 262144,
    "thinking": True,
    "spec_decode": "draft-mtp",
    "permission": {"edit": "ask", "bash": "ask", "webfetch": "ask",
                   "websearch": "ask", "external_directory": "ask"},
}
DEFAULT_TARGET = {"model": DEFAULT_MODEL, "quant": "Q6_K", "harness": "opencode",
                  "settings": DEFAULT_SETTINGS, "env": None}
AGENT_NAME = "opencode-worker"


def _settings_sig(settings):
    """Stable short signature of the settings dict, so a settings change keys a different pack."""
    if not settings:
        return "default"
    return hashlib.sha1(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:8]


def _slug(s):
    return re.sub(r"[^a-z0-9._-]+", "-", str(s).lower()).strip("-")


def resolve_artifacts(target):
    """Select the compiled artifacts for this exact target. Everything the worker pack carries -
    the OpenCode agent (system prompt), the skill-pack, the settings, the stacked deltas, and the
    earned grade - is keyed by the FULL target (model, quant, harness, settings, env), because a
    weaker model / different quant / different serving settings needs a different pack. v0 emits
    one pack (the default qwen target); a real registry replaces this body without changing
    callers. The Claude-side orchestrator skill is target-agnostic and lives outside the pack."""
    model = target.get("model", {})
    mid = model.get("id")
    quant = target.get("quant") or "unspecified"
    harness = target.get("harness", "opencode")
    settings = target.get("settings") or {}
    sig = _settings_sig(settings)
    env = target.get("env")
    key = f"model={mid};quant={quant};harness={harness};settings={sig};env={env}"
    slug = _slug(f"{mid}__{quant}__{harness}")
    pack_dir = f"packs/{slug}"
    # The earned grade travels IN the pack: scripts/graded_episode.py writes grade.json there.
    grade = None
    gpath = os.path.join(_ROOT, pack_dir, "grade.json")
    if os.path.exists(gpath):
        try:
            with open(gpath) as f:
                grade = json.load(f)
        except (OSError, ValueError):
            grade = None
    return {
        "key": key,
        # opencode-side worker pack (target-keyed source) + the active install the server loads
        "pack_dir": pack_dir,
        "pack_manifest": f"{pack_dir}/manifest.json",
        "pack_agent": f"{pack_dir}/agent/{AGENT_NAME}.md",
        "agent": AGENT_NAME,
        "agent_file": f".opencode/agent/{AGENT_NAME}.md",
        "system_prompt": "protocol/opencode-worker-protocol.md",   # protocol source (compiled in)
        "settings": settings,
        "settings_sig": sig,
        # Claude-side orchestrator skill: one skill, target-agnostic, NOT part of the pack.
        "skill_claude": "skills/opencode-worker/SKILL.md",
        "deltas": ["qwen-opencode"] if mid == "qwen3.8-27b" else [],
        "grade": grade,         # the pack's earned honest-outcome grade, or None if unearned
        "version": "v0",
    }

class OpenCodeWorker:
    def __init__(self, base):
        self.base = base.rstrip("/")          # e.g. http://127.0.0.1:47611/api

    def _req(self, method, path, body=None, timeout=180):
        url = self.base + path
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{method} {path} -> {e.code}: {e.read().decode()[:400]}")
        if not raw.strip():
            return {}
        obj = json.loads(raw)
        # OpenCode v2 /api wraps list/object payloads under a top-level "data" key
        # (sometimes alongside pagination/meta keys); unwrap whenever present.
        if isinstance(obj, dict) and "data" in obj:
            return obj["data"]
        return obj

    # --- control surface ---------------------------------------------------
    def agents(self):
        """Agent ids the server loaded at startup (v2: id; v1: name)."""
        r = self._req("GET", "/agent")
        items = r if isinstance(r, list) else r.get("agents", [])
        return [a.get("id") or a.get("name") for a in items]

    def start(self, task, directory, target=None, agent=None):
        """worker.start: create a session for `target` in `directory`, submit `task`.

        The worker runs under an OpenCode agent whose system prompt IS the protocol (compiled to
        .opencode/agent/<agent>.md by scripts/build_agent.py), so we submit only the task, never
        the protocol. `agent` defaults to the target's resolved agent. The server loads agents at
        startup only, so we check it is present and fail loud: an unknown agent otherwise creates
        a session that silently stalls (no system prompt, no error)."""
        target = target or DEFAULT_TARGET
        agent = agent or resolve_artifacts(target).get("agent")
        if agent and agent not in self.agents():
            raise RuntimeError(
                f"agent '{agent}' is not loaded by the server. Compile it "
                f"(python3 scripts/build_agent.py) and (re)start `opencode serve` from the repo "
                f"root so .opencode/agent/{agent}.md is loaded. Loaded: {self.agents()}")
        body = {"model": target["model"], "location": {"directory": directory}}
        if agent:
            body["agent"] = agent
        s = self._req("POST", "/session", body)
        sid = s.get("id")
        if not sid:
            raise RuntimeError(f"no session id in create response: {json.dumps(s)[:300]}")
        self._req("POST", f"/session/{sid}/prompt", {"prompt": {"text": task}})
        return sid

    def steer(self, sid, msg):
        """worker.steer: inject an authoritative correction into the running turn."""
        return self._req("POST", f"/session/{sid}/prompt",
                         {"prompt": {"text": msg}, "delivery": "steer"})

    def pending(self, sid):
        """permission asks currently blocking."""
        r = self._req("GET", f"/session/{sid}/permission")
        return r if isinstance(r, list) else r.get("requests", r.get("permissions", []))

    def reply(self, sid, req_id, decision):
        """worker.approve: decision in {once, always, reject}."""
        assert decision in ("once", "always", "reject")
        return self._req("POST", f"/session/{sid}/permission/{req_id}/reply",
                         {"reply": decision})

    def interrupt(self, sid):
        """worker.stop."""
        return self._req("POST", f"/session/{sid}/interrupt", {})

    def messages(self, sid):
        r = self._req("GET", f"/session/{sid}/message")
        return r if isinstance(r, list) else r.get("messages", [])

    def session(self, sid):
        return self._req("GET", f"/session/{sid}")

    # --- orchestration -----------------------------------------------------
    def run(self, task, directory, target=None, approve=lambda p: "once", poll=3.0, budget=600,
            agent=None):
        """Run a task to completion. `approve(permission)->decision` is the policy hook the
        driver routes to the Opus loop / operator. Prints one filtered line per event."""
        target = target or DEFAULT_TARGET
        art = resolve_artifacts(target)
        print(f"[worker] target {art['key']} agent={agent or art.get('agent')} "
              f"deltas={art['deltas']} grade={art['grade']}", flush=True)
        sid = self.start(task, directory, target=target, agent=agent)
        print(f"[worker] session {sid} started", flush=True)
        t0, last = time.time(), None
        while time.time() - t0 < budget:
            for p in self.pending(sid):
                dec = approve(p)
                self.reply(sid, self.req_id(p), dec)
                print(f"[worker] permission {self.describe(p)} -> {dec}", flush=True)
            status = self._turn_status(sid)
            if status != last:
                print(f"[worker] status={status}", flush=True); last = status
            if status == "error":
                err = self._turn_error(sid)
                print(f"[worker] error: {err.get('message', err)}", flush=True)
                break
            if status in ("idle", "completed", "done"):
                break
            time.sleep(poll)
        return sid, self._last_assistant(sid)

    @staticmethod
    def describe(p):
        """Human label for a pending permission, so the operator sees WHAT they approve.
        v2 objects use action+resources; v1 use permission+patterns. `id` is shared."""
        act = p.get("action") or p.get("permission") or "?"
        detail = p.get("resources") or p.get("patterns") or p.get("metadata") or ""
        return f"{act} {detail}".strip()

    @staticmethod
    def req_id(p):
        return p.get("id") or p.get("requestID") or p.get("callID")

    @staticmethod
    def _status_of(info):
        if isinstance(info.get("status"), str):
            return info["status"]
        t = info.get("time", {})
        if isinstance(t, dict) and t.get("completed"):
            return "idle"
        return "running"

    def _newest_assistant(self, sid):
        """The newest assistant message by creation time, or None. Turn status/finish/error all
        derive from this: opencode's session object carries no reliable status here."""
        newest, newest_t = None, -1
        for m in self.messages(sid):
            if m.get("type") != "assistant":
                continue
            tm = m.get("time")
            t = tm.get("created", 0) if isinstance(tm, dict) else (tm or 0)
            if t >= newest_t:
                newest_t, newest = t, m
        return newest

    def _turn_status(self, sid):
        """Turn status derived from the newest assistant message, since opencode's session object
        exposes no completion/status field. Terminal finishes: 'stop'/'length' -> idle (done);
        'error' (or an error field) -> error. An intermediate agentic step finishes with
        'tool-calls' and is NOT terminal (the turn continues) -> running. No assistant message
        yet, or one still generating, is also running. So this never cuts a healthy multi-step
        turn short, but it does detect real completion (which the session status never reports)."""
        m = self._newest_assistant(sid)
        if not m:
            return "running"
        if m.get("finish") == "error" or m.get("error"):
            return "error"
        tm = m.get("time") or {}
        completed = isinstance(tm, dict) and tm.get("completed")
        if completed and m.get("finish") in ("stop", "length"):
            return "idle"
        return "running"

    def _turn_error(self, sid):
        """The error on the newest assistant message if it finished with one, else None."""
        m = self._newest_assistant(sid)
        if m and (m.get("finish") == "error" or m.get("error")):
            return m.get("error") or {"type": "error", "message": "turn finished with error"}
        return None

    def overall_status(self, sid):
        """Public turn status: running | idle | error (see _turn_status)."""
        return self._turn_status(sid)

    def _last_assistant(self, sid):
        # messages: type in {assistant,user,system}; assistant.content is a list of typed
        # parts (reasoning/text/tool). The reply is the newest assistant message's text parts.
        best, best_t = "", -1
        for m in self.messages(sid):
            if m.get("type") != "assistant" or not isinstance(m.get("content"), list):
                continue
            tm = m.get("time")
            t = tm.get("created", 0) if isinstance(tm, dict) else (tm or 0)
            texts = [p.get("text", "") for p in m["content"]
                     if p.get("type") == "text" and p.get("text")]
            if texts and t >= best_t:
                best_t, best = t, "\n".join(texts).strip()
        return best


if __name__ == "__main__":
    # Bash-callable connector: the Opus loop drives a worker session stepwise, JSON out,
    # subscription-safe (only ever talks to the local opencode server).
    import argparse, json as _json
    ap = argparse.ArgumentParser(description="OpenCode worker connector")
    ap.add_argument("--base", default="http://127.0.0.1:47611/api")
    sub = ap.add_subparsers(dest="cmd", required=True)
    def _tgt_args(pp):
        pp.add_argument("--provider", default=DEFAULT_MODEL["providerID"])
        pp.add_argument("--model", default=DEFAULT_MODEL["id"])
        pp.add_argument("--quant", default=DEFAULT_TARGET["quant"])
        pp.add_argument("--agent", default=None, help="worker agent (default: target's resolved agent)")
    ps = sub.add_parser("start"); ps.add_argument("--dir", required=True); ps.add_argument("--task", required=True); _tgt_args(ps)
    pt = sub.add_parser("steer"); pt.add_argument("--session", required=True); pt.add_argument("--msg", required=True)
    pp_ = sub.add_parser("pending"); pp_.add_argument("--session", required=True)
    pa = sub.add_parser("approve"); pa.add_argument("--session", required=True); pa.add_argument("--req", required=True); pa.add_argument("--decision", default="once", choices=["once", "always", "reject"])
    pst = sub.add_parser("status"); pst.add_argument("--session", required=True)
    pf = sub.add_parser("final"); pf.add_argument("--session", required=True)
    psp = sub.add_parser("stop"); psp.add_argument("--session", required=True)
    pr = sub.add_parser("run"); pr.add_argument("--dir", required=True); pr.add_argument("--task", required=True); pr.add_argument("--auto", default="once", choices=["once", "always", "reject"]); _tgt_args(pr)
    a = ap.parse_args(); w = OpenCodeWorker(a.base)
    def _tgt(a): return {"model": {"providerID": a.provider, "id": a.model}, "quant": a.quant,
                         "harness": "opencode", "settings": DEFAULT_SETTINGS, "env": None}
    if a.cmd == "start":
        print(_json.dumps({"session": w.start(a.task, a.dir, target=_tgt(a), agent=a.agent)}))
    elif a.cmd == "steer":
        w.steer(a.session, a.msg); print(_json.dumps({"ok": True}))
    elif a.cmd == "pending":
        print(_json.dumps([{"req": w.req_id(p), "action": w.describe(p)} for p in w.pending(a.session)]))
    elif a.cmd == "approve":
        w.reply(a.session, a.req, a.decision); print(_json.dumps({"ok": True, "decision": a.decision}))
    elif a.cmd == "status":
        print(_json.dumps({"status": w.overall_status(a.session)}))
    elif a.cmd == "final":
        print(w._last_assistant(a.session) or "")
    elif a.cmd == "stop":
        w.interrupt(a.session); print(_json.dumps({"ok": True}))
    elif a.cmd == "run":
        sid, final = w.run(a.task, a.dir, target=_tgt(a), approve=lambda p: a.auto, agent=a.agent)
        print(_json.dumps({"session": sid, "final": final}))
