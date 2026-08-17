# opencode-worker

Connect Claude Code to an **arbitrary (OpenCode, model) worker**, subscription-safe, and make
any given (model, harness) reliable with a hoistable cross-compile that carries a graded
transfer score.

## Why this exists

Claude Code cannot host a foreign-model subagent: its model is session-wide, per-subagent
provider routing is unimplemented, and a router needs an API token (not a Max/Pro
subscription). So this does not fight the harness. It connects over the **tool boundary**:
Opus stays the orchestrator on your subscription, and a worker (OpenCode driving any model,
e.g. a local Qwen on GPU) does the labor for free. Nothing reroutes Claude's auth.

What you lose is the cosmetic native-subagent wrapper. What you keep is everything functional:
agentic multi-step work, live mid-turn correction, and permission approval under your control.

## Architecture

- **Driver / connector** (`src/opencode_worker.py`): drives `opencode serve` over its HTTP
  API. Bash-callable verbs, JSON out: `start / steer / pending / approve / status / final /
  stop / run`. The Opus loop drives a worker session through these.
- **MCP server** (`src/opencode_worker_mcp.py`): the same control surface as MCP tools over
  stdio, so Claude Code drives a worker with tool calls instead of the Bash CLI. Discovered
  via the repo `.mcp.json`. Same inner call path, same subscription-safety.
- **Target** = `(model, harness, environment)`, every axis a parameter. `resolve_artifacts(target)`
  keys the skill / system-prompt / deltas / grade by the full target. OpenCode is harness #1,
  Qwen3.8-27B is model #1, neither is a fixture.
- **Protocol contract** (`protocol/opencode-worker-protocol.md`): the model-neutral prose the
  worker runs under. Per-model deltas are added only by measured divergence. This is what
  `hoist` cross-compiles per target; the graded transfer score proves the retarget worked.

## Control surface (proven, ground-truthed)

| Capability | Evidence (`tests/`) |
|---|---|
| Plumbing (create/status/pending/messages/interrupt) | `structural_test.py` |
| Agentic multi-step | `proof_run.py`, wrote `notes.txt` = apple/banana/cherry |
| Live mid-turn steer | `steer_proof.py`, redirected apples to oranges at 12s; final file all oranges |
| Our-side permissions | `perm_proof.py`, `write` gated `ask`, written only after driver approval |
| First graded episode | `graded_episode.py`, Qwen under protocol scored 3/3 AND honestly said DONE only after the test passed |

All checks are independent of the model's self-report (the honest-grade discipline).

## Use

Prerequisites: `opencode` (>= 1.18.18), a provider in `~/.config/opencode/opencode.json`
(here `mainframe-qwen38`), and a served model. Then:

```bash
opencode serve --port 47611 --hostname 127.0.0.1 &
# drive a worker session:
python3 src/opencode_worker.py start --dir /path/to/work --task "..."   # -> {"session": "ses_..."}
python3 src/opencode_worker.py pending --session ses_...                 # gates awaiting decision
python3 src/opencode_worker.py approve --session ses_... --req <id> --decision once
python3 src/opencode_worker.py steer   --session ses_... --msg "correction"
python3 src/opencode_worker.py status  --session ses_...
python3 src/opencode_worker.py final   --session ses_...
# or all-in-one with an auto-approve policy:
python3 src/opencode_worker.py run --dir /path/to/work --task "..." --auto once
```

Or drive it from Claude Code as an **MCP server** (same control surface, cleaner than the CLI).
The repo `.mcp.json` registers it, so Claude Code exposes the tools `mcp__opencode-worker__{start,
steer, pending, approve, status, final, stop, run}`. Run it standalone with:

```bash
OPENCODE_BASE=http://127.0.0.1:47611/api python3 src/opencode_worker_mcp.py   # stdio
```

`final` returns the worker's self-report, which is a claim, not evidence: ground-truth the real
result yourself before treating a task as built (the honest grade). Re-runnable end-to-end check:
`python3 tests/mcp_smoke.py`.

Subscription-safe: the connector only ever talks to the local opencode server.

## Status

Working solution at the connector level, now exposed as an MCP server for Claude Code
(`src/opencode_worker_mcp.py` + `.mcp.json`). Next: expand the graded co-optimization loop
across more tasks and targets (routing each divergence to the model delta or the driver
protocol); deliver the protocol as a system prompt via agent config (not prepended to the
task); bundle as a hoistable skill (`skills/opencode-worker/`).

Spec of record: `dap:docs/specs/opencode-worker-integration.md`.
