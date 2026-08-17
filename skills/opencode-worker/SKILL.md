---
name: opencode-worker
description: Bind Claude Code to an existing OpenCode worker (any model, e.g. Qwen on GPU or an API-backed model) and drive it, subscription-safe. Use to delegate bulk or cheap multi-step agentic work off the expensive main loop when you can verify the result with real checks. Assumes a reachable model + opencode already exist; if not, run the opencode-setup wizard first. Drives the worker over opencode serve, gating its permissions and steering mid-run.
---

# opencode-worker (the binder)

You (the Opus main loop) stay the orchestrator. This binds Claude Code to a worker (OpenCode
driving an already-reachable model) over the tool boundary, so nothing touches the Claude
subscription auth. You approve the worker's permission gates, may steer it mid-run, and NEVER
trust its self-report: you verify with real checks.

This is the BINDING unit, distinct from setup, and it is the entry point. It needs a target: a
model opencode can reach, named by its `(model, quant, settings)`.

## First: ensure a target exists (call the wizard if needed)

Check whether a reachable worker target is already in place (opencode configured, a model endpoint
that answers). If there is one, use it. If there is NOT, INVOKE the **opencode-setup** skill - the
inference wizard - which discovers/provisions a model for this user and hands back the target;
then continue here. Compose it by invoking the skill, never by importing its internals. Do not
try to stand up inference yourself: that is the wizard's whole job, across environments you cannot
predict.

## When to use

Delegate when the task is well-scoped, multi-step, tolerant of a weaker model, and **verifiable
by a check you run yourself** (a file exists, a test passes, output matches). Do not delegate
judgment calls or work you cannot independently grade.

## Prepare the pack for the target

The worker runs under an OpenCode agent whose system prompt IS the protocol (not prepended to
the task). Compile the pack for the target and install its active agent:

- `python3 scripts/build_agent.py --provider <p> --model <m> --quant <q>` compiles the protocol
  into `packs/<target>/` and installs the active agent (settings, incl. our-side permission
  gating, are its frontmatter). A model/quant/settings not seen before is hoistable's
  cross-compile.
- Start `opencode serve` FROM the repo root so it loads the agent (agents load at startup only).

## Drive the worker

Submit ONLY the task (the protocol is the agent's system prompt). Use `src/opencode_worker.py`
(verbs emit JSON), or the MCP tools (`mcp__opencode-worker__*`) if the server is registered:

1. `start --dir <workdir> --task "<task>"` -> `{"session": "ses_..."}` (binds the worker agent).
2. Loop: `pending --session <s>` shows gates awaiting your decision, each with its concrete
   action (e.g. `edit ['x.py']`). Decide per policy or escalate, then `approve --session <s>
   --req <id> --decision once|reject`.
3. `steer --session <s> --msg "<authoritative correction>"` injects a correction into the running
   turn. Log every correction as a candidate cross-compile delta.
4. `status --session <s>` until it is `idle`/`error`; then `final --session <s>` for the reply.

## The honest grade (non-negotiable)

The worker's "DONE" is not evidence. Run your own acceptance check against the real result.
Outcome is binary: **built** only if every check passes; otherwise **honest-failure** - tear down
partial state, report faithfully, never relabel a failing check as success. `scripts/
graded_episode.py` runs this discipline over real tasks and records the earned grade in the pack.

## Cross-compile (making a new target reliable)

Each divergence between the worker and a strong-model reference routes to whichever side is
wrong: a per-target delta overlay (worker prose) or the driver protocol/implementation. The
graded transfer score, earned on a real result in the worker's own session, is the proof and
cannot be faked. Package emitted targets with their full triple, deltas, and earned grade;
hoistable owns the cross-compile and the score.
