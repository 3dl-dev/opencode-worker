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
import json, time, urllib.request, urllib.error

# A TARGET is the full triple; every axis is a parameter, none a fixture.
# opencode is harness #1 and qwen3.8-27b is model #1 - defaults only.
DEFAULT_MODEL = {"providerID": "mainframe-qwen38", "id": "qwen3.8-27b"}
DEFAULT_TARGET = {"model": DEFAULT_MODEL, "harness": "opencode", "env": None}

def resolve_artifacts(target):
    """Select the compiled artifacts for this exact target. Tracking lives here: the skill +
    system-prompt variant, the deltas stacked, and the earned grade are all keyed by
    (model, harness, env). v0 returns the single known target's set; a real registry replaces
    this body without changing callers."""
    model = target.get("model", {})
    harness = target.get("harness", "opencode")
    key = f"model={model.get('id')};harness={harness};env={target.get('env')}"
    return {
        "key": key,
        "skill": None,          # -> place at .opencode/skills/<name>/SKILL.md
        "system_prompt": None,  # -> inject via agent config
        "deltas": ["qwen-opencode"] if model.get("id") == "qwen3.8-27b" else [],
        "grade": None,          # -> filled from the transfer-score record for this target
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
    def start(self, task, directory, target=None):
        """worker.start: create a session for `target` in `directory`, submit `task`."""
        target = target or DEFAULT_TARGET
        s = self._req("POST", "/session", {
            "model": target["model"],
            "location": {"directory": directory},
        })
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
    def run(self, task, directory, target=None, approve=lambda p: "once", poll=3.0, budget=600):
        """Run a task to completion. `approve(permission)->decision` is the policy hook the
        driver routes to the Opus loop / operator. Prints one filtered line per event."""
        target = target or DEFAULT_TARGET
        art = resolve_artifacts(target)
        print(f"[worker] target {art['key']} deltas={art['deltas']} grade={art['grade']}", flush=True)
        sid = self.start(task, directory, target=target)
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
    ps = sub.add_parser("start"); ps.add_argument("--dir", required=True); ps.add_argument("--task", required=True); _tgt_args(ps)
    pt = sub.add_parser("steer"); pt.add_argument("--session", required=True); pt.add_argument("--msg", required=True)
    pp_ = sub.add_parser("pending"); pp_.add_argument("--session", required=True)
    pa = sub.add_parser("approve"); pa.add_argument("--session", required=True); pa.add_argument("--req", required=True); pa.add_argument("--decision", default="once", choices=["once", "always", "reject"])
    pst = sub.add_parser("status"); pst.add_argument("--session", required=True)
    pf = sub.add_parser("final"); pf.add_argument("--session", required=True)
    psp = sub.add_parser("stop"); psp.add_argument("--session", required=True)
    pr = sub.add_parser("run"); pr.add_argument("--dir", required=True); pr.add_argument("--task", required=True); pr.add_argument("--auto", default="once", choices=["once", "always", "reject"]); _tgt_args(pr)
    a = ap.parse_args(); w = OpenCodeWorker(a.base)
    def _tgt(a): return {"model": {"providerID": a.provider, "id": a.model}, "harness": "opencode", "env": None}
    if a.cmd == "start":
        print(_json.dumps({"session": w.start(a.task, a.dir, target=_tgt(a))}))
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
        sid, final = w.run(a.task, a.dir, target=_tgt(a), approve=lambda p: a.auto)
        print(_json.dumps({"session": sid, "final": final}))
