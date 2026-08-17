# CLAUDE.md: opencode-worker

Project-specific instructions. OS-level protocol is inherited from `~/.claude/CLAUDE.md`.

## What this is

A connector that lets **Claude Code (Opus, on the Max subscription) delegate scoped agentic
work to a local OpenCode worker** driving an arbitrary model (Qwen3.8-27B is target #1). It
runs over the tool boundary (the local `opencode serve` HTTP API), so it never touches the
Claude subscription auth. The worker-facing protocol is cross-compiled per target by
hoistable, and a graded transfer score proves the retarget. Full rationale and the decision
trail: `dap:docs/specs/opencode-worker-integration.md` (the spec of record).

## Continue here (execution pointer, 2026-08-17)

State, as raw observations (re-verify, do not treat as frozen):
- The connector works end to end. Proven live against `opencode serve` 1.18.18 + Qwen3.8-27B:
  plumbing, agentic multi-step, live mid-turn steer, our-side permission gating, and a first
  graded episode that scored 3/3 with a correct honest-outcome. Evidence scripts in
  `tests/evidence/`; the re-runnable check is `tests/smoke.py`.
- The driver is `src/opencode_worker.py` (library + Bash connector CLI).

Immediate next step (pick up here): run `tests/smoke.py` to confirm the environment, then
advance one of the "Next" items below. The highest-value next work is the graded
co-optimization loop: run more real tasks, and route each divergence to either the per-model
delta overlay or the driver protocol (see the spec, section 7b).

## Environment and how to run

- Start the server: `opencode serve --port 47611 --hostname 127.0.0.1 &`
- Provider (already in `~/.config/opencode/opencode.json`): `mainframe-qwen38`, model
  `qwen3.8-27b`, pointing at the local endpoint `http://192.168.2.43:30801/v1`.
- Bring the model up only if the GPU rail is free (it holds both GPUs and does not preempt;
  scale back to 0 when done, and yield when VAT2 needs the cards):
  `kubectl scale deploy/qwen38-llama-serve --replicas=1` ... `--replicas=0`
  Health: `curl -s http://192.168.2.43:30801/health`. Runbook:
  `mainframe/docs/ops/qwen38-serve.md`.
- Smoke test: `python3 tests/smoke.py` (expects the server up and the model served).
- Drive a session by hand: `python3 src/opencode_worker.py {start,steer,pending,approve,status,final,stop,run} ...`

## Hard-won API facts (reference, do not rediscover)

Against `opencode serve` v2 (`/api`):
- Responses wrap the payload under a top-level `data` key (sometimes with sibling keys).
  Always unwrap `data`. The driver's `_req` does this.
- Create session: `POST /session` with `{model:{providerID,id,variant}, location:{directory}}`;
  the returned session `id` is `ses_...`.
- Prompt / steer: `POST /session/{id}/prompt` with `{prompt:{text}, delivery:"steer"|"queue"}`.
  `steer` injects into the running turn. `POST /session/{id}/interrupt` halts.
- Messages: `GET /session/{id}/message` returns items with `type` in {assistant,user,system}
  (no `role`). An assistant message's `content` is a list of typed parts
  (`reasoning`/`text`/`tool`); the reply text is the `text` parts of the newest assistant
  message.
- Permissions: `GET /session/{id}/permission` lists pending asks as `{id, action, resources,
  ...}` (v2) or `{id, permission, patterns, ...}` (v1). Reply:
  `POST /session/{id}/permission/{id}/reply` with `{reply:"once"|"always"|"reject"}`. Gate a
  tool by setting `permission: {<tool>: "ask"}` in `opencode.json` (per-tool allow/ask/deny;
  `bash` takes wildcard maps). A workdir-local `opencode.json` scopes it to that session.
- The session object (`GET /session/{id}`) has NO usable status/completion field here (`status`
  is absent, `time` has only created/updated). Turn state must be read from the newest assistant
  message's `finish`: `tool-calls` = mid-turn step (keep polling), `stop`/`length` = done,
  `error` = failed turn (with an `error` object). An errored turn does NOT flip any session-level
  flag, so polling the session alone hangs to budget. The driver's `_turn_status`/`overall_status`
  encode this; use them, not `_status_of(session(...))`.
- Qwen is single-slot (`--parallel 1`): do NOT run two worker sessions at once, they serialize.
  It is slow (~44 tok/s with thinking on); budget 120s+ per agentic turn.
- `nvidia-smi` inside the serve container shows "No running processes" and 0% util when idle
  (a PID-namespace artifact + P8 idle state), not a fault. To confirm the GPU is live, sample
  util during a real generation.

## Invariants (check every session)

- **Honest grade.** The worker's "DONE" is not evidence. Verify the real result with your own
  check. Outcome is binary: built only if every check passes, else honest-failure; never
  relabel a failing check.
- **Subscription-safe.** The connector only ever talks to the local opencode server. Do not
  route Claude Code through a gateway/router (that needs API billing, not the subscription).
- **Target is a parameter.** `(model, harness, environment)`, none fixed. OpenCode and Qwen
  are values #1, not fixtures. `resolve_artifacts(target)` keys artifacts by the full target.
- **No em-dashes** in anything Baron reads (he reads them as AI-generated). Use commas/colons.
- **Commit only when asked.** Branch off `main` for new work.

## Repo map

```
src/opencode_worker.py                 driver + Bash connector CLI
src/opencode_worker_mcp.py             MCP server (stdio) wrapping the driver as tools
.mcp.json                              repo MCP config so Claude Code discovers the server
protocol/opencode-worker-protocol.md   model-neutral worker contract (hoist cross-compiles it)
skills/opencode-worker/SKILL.md        the hoistable/Claude-Code skill that bundles this
tests/smoke.py                         re-runnable end-to-end check (library path)
tests/mcp_smoke.py                     re-runnable end-to-end check (MCP stdio path)
tests/evidence/                        the original proof scripts (scratch paths; historical)
README.md                              overview + usage
```

## Next

1. ~~Wrap the connector as an MCP server~~ DONE (2026-08-17): `src/opencode_worker_mcp.py`
   (FastMCP stdio) + `.mcp.json`; tools start/steer/pending/approve/status/final/stop/run.
   Re-runnable check: `tests/mcp_smoke.py`. Remaining polish: system prompt via agent config
   (item 3) so the protocol is not prepended to the task prompt.
2. Grow the graded co-optimization loop: more tasks/targets, routing divergences to the model
   delta overlay or the driver protocol; record earned transfer grades per target.
3. Proper artifact placement: skill to `.opencode/skills/<name>/SKILL.md`, system prompt via
   the agent config (currently the protocol is prepended to the task prompt).
4. Bundle for distribution via hoistable (the cross-compiler + grader).
5. Not this repo: rebalance the Qwen tensor-split toward the 3090 (a `mainframe` k8s tuning
   item; the A4500 is the bottleneck under 0.57/0.43).

## Relationships

- `dap` owns the spec (`docs/specs/opencode-worker-integration.md`, `opencode-worker-protocol.md`).
- `hoistable` owns the cross-compile and the graded transfer score (`emit.py`, `grade/`).
- This repo owns the connector implementation and its packaging as a skill.
