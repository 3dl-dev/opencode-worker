---
name: opencode-worker
description: Delegate a scoped agentic task from Claude Code to a local OpenCode worker (any model, e.g. Qwen on GPU), subscription-safe. Use for bulk or cheap multi-step work you want off the expensive main loop, when you can verify the result with real checks. Drives the worker over opencode serve; you approve its permission gates and can steer it mid-run.
---

# opencode-worker

You (the Opus main loop) stay the orchestrator. This delegates a well-scoped agentic task to
a local worker (OpenCode driving any configured model) and drives it over the tool boundary,
so nothing touches the Claude subscription auth. You approve the worker's permission gates and
may correct it mid-run. You NEVER trust the worker's self-report; you verify with real checks.

## When to use

Delegate when the task is: well-scoped, multi-step, tolerant of a weaker model, and
**verifiable by a check you run yourself** (a file exists, a test passes, output matches).
Do not delegate judgment calls, or work you cannot independently grade.

## Preconditions (resolve, do not assume)

1. `opencode` installed; a provider for the model in `~/.config/opencode/opencode.json`.
2. The model is served (for the local Qwen target: `kubectl get deploy qwen38-llama-serve`;
   scale to 1 only if the GPU rail is free, and scale back to 0 when done).
3. Start the server: `opencode serve --port 47611 --hostname 127.0.0.1 &`.

## Drive the worker

Use `src/opencode_worker.py` (verbs emit JSON):

1. `start --dir <workdir> --task "<task>"` -> `{"session": "ses_..."}`. Prepend the protocol
   contract (`protocol/opencode-worker-protocol.md`) to the task so the worker runs under it.
2. Loop: `pending --session <s>` shows gates awaiting your decision, each with the concrete
   action (e.g. `write ['x.py']`). Decide per policy or escalate to the operator, then
   `approve --session <s> --req <id> --decision once|reject`.
3. To correct course, `steer --session <s> --msg "<authoritative correction>"` (injects into
   the running turn). Log every correction as a candidate cross-compile delta.
4. `status --session <s>` until idle; then `final --session <s>` for the reply.

## The honest grade (non-negotiable)

The worker's "DONE" is not evidence. Run your own acceptance check against the real result.
Outcome is binary: **built** only if every check passes; otherwise **honest-failure**, tear
down partial state, report faithfully, never relabel a failing check as success.

## Cross-compile (making a new target reliable)

Each divergence between the worker and a strong-model reference routes to whichever side is
wrong: a per-model delta overlay (worker prose) or the driver protocol/implementation itself.
The graded transfer score, run on a real result in the worker's own session, is the proof and
cannot be faked. Package emitted targets with their triple, deltas, and earned grade.
