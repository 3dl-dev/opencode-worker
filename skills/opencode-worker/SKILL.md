---
name: opencode-worker
description: Set up and drive a local OpenCode worker (any model, e.g. Qwen on GPU, or an API-backed model) from Claude Code, subscription-safe. Use to delegate bulk or cheap multi-step agentic work off the expensive main loop when you can verify the result with real checks. On first run it discovers the environment and stands the worker up; then it drives the worker over opencode serve, gating its permissions and steering mid-run.
---

# opencode-worker

You (the Opus main loop) stay the orchestrator. This delegates well-scoped agentic work to a
worker (OpenCode driving any configured model) over the tool boundary, so nothing touches the
Claude subscription auth. You approve the worker's permission gates, may steer it mid-run, and
NEVER trust its self-report: you verify with real checks.

**You are an intelligent setup wizard, not a script.** You, the executing agent, are the general
part. Nothing below is a fixed matrix to match against, and setup is not a canned probe sequence.
Work like a wizard: **look around** and inspect what is visible, **infer** from partial evidence,
**ask** the user for what you cannot find (much of a real rig is knowledge only they hold), and
when they do not know either, **guide them through finding out** - hand them the command, read the
result together, narrow it down. Environments run from nothing to a veteran whose rig no command
reveals; meet each where they are and match your hand-holding to their level. Fall back to the
deterministic tools (the connector driver, the pack compile) only where determinism belongs.

## When to use

Delegate when the task is well-scoped, multi-step, tolerant of a weaker model, and **verifiable
by a check you run yourself** (a file exists, a test passes, output matches). Do not delegate
judgment calls or work you cannot independently grade.

## Set up the worker (first run, or a new environment)

Aim: end at a graded, working worker. Move through discover -> decide -> provision -> compile
-> verify, reasoning at each step from what is actually there.

1. **Discover - orient to the user; do not assume you can detect their setup.** Configs run from
   nothing to a veteran whose GPUs sit behind custom networking or a cluster that NO probe will
   reveal - a silent `nvidia-smi` proves nothing, it does not mean "no GPU". So establish the
   situation WITH the user. Ask where they are and what they have: a model already served
   somewhere (get the endpoint)? local accelerators they want to use (and how they are reached)?
   only an API key? nothing yet? Gauge their expertise from newbie to devoperator and match your
   level of hand-holding to it. Probe only where a probe genuinely helps and only as confirmation
   of something plausible (curl an endpoint they named and read `/props`; `opencode --version`;
   `nvidia-smi` for a *local* card). The user is the authority on their own environment: when the
   config is idiosyncratic or invisible, ask, do not guess.

2. **Decide** the target `(model, quant, harness, settings, env)`. Default policy, adapt as
   sense dictates: if a rig is already serving a model, **capture it** (no install). Else, if
   there is a capable GPU, **fit a local model to it** - reason about the real weight size
   against the VRAM with headroom for the KV cache at the context you want, and confirm against
   the load-time KV line rather than any guessed table; pick the best model/quant that genuinely
   fits. Else, if an API key is present, use that **provider**. Recommend and confirm with the
   operator before anything that downloads weights or starts a server.

3. **Provision.** Install `opencode` if absent. Local: pull the weights (prefer a quant that
   carries what the runtime needs, e.g. an MTP-bearing GGUF for llama.cpp speculative decoding),
   start the server, wait until it is actually healthy. API: write the provider block into
   `opencode.json` with the user's key. Stay subscription-safe throughout: only the local
   opencode server and the model endpoint, never Claude Code's own auth.

4. **Compile the pack** for the chosen target. `python3 scripts/build_agent.py --provider <p>
   --model <m> --quant <q>` compiles the protocol into the target's pack and installs the active
   agent (its system prompt is the protocol; the settings, incl. our-side permission gating, are
   its frontmatter). Start `opencode serve` FROM the repo root so it loads the agent (agents load
   at startup only). A model/quant/settings not seen before is hoistable's cross-compile.

5. **Verify.** `python3 scripts/graded_episode.py` runs real tasks and grades them honestly
   (score + honest-outcome), writing the earned grade into the pack. Require honest-outcome. If
   the worker diverges, that is signal (see cross-compile below), not something to wave through.

## Drive the worker

The protocol is the worker agent's system prompt, so submit ONLY the task. Use
`src/opencode_worker.py` (verbs emit JSON), or the MCP tools (`mcp__opencode-worker__*`) if the
server is registered:

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
partial state, report faithfully, never relabel a failing check as success.

## Cross-compile (making a new target reliable)

Each divergence between the worker and a strong-model reference routes to whichever side is
wrong: a per-target delta overlay (worker prose) or the driver protocol/implementation. The
graded transfer score, earned on a real result in the worker's own session, is the proof and
cannot be faked. Package emitted targets with their full triple, deltas, and earned grade;
hoistable owns the cross-compile and the score.
