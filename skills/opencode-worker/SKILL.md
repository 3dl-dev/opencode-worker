---
name: opencode-worker
description: Set up and drive a local OpenCode worker (any model, e.g. Qwen on GPU, or an API-backed model) from Claude Code, subscription-safe. Use to delegate bulk or cheap multi-step agentic work off the expensive main loop when you can verify the result with real checks. On first run it discovers the environment and stands the worker up; then it drives the worker over opencode serve, gating its permissions and steering mid-run.
---

# opencode-worker

You (the Opus main loop) stay the orchestrator. This delegates well-scoped agentic work to a
worker (OpenCode driving any configured model) over the tool boundary, so nothing touches the
Claude subscription auth. You approve the worker's permission gates, may steer it mid-run, and
NEVER trust its self-report: you verify with real checks.

**This is a skill, not a program.** Where you set the worker up, you use judgment on what you
actually find: run the commands, read the output, reason about it, adapt. Nothing below is a
fixed matrix of hardware/models/providers to match against; it is the procedure and the cues.
Fall back to the deterministic tools (the connector driver, the pack compile) only where they
belong.

## When to use

Delegate when the task is well-scoped, multi-step, tolerant of a weaker model, and **verifiable
by a check you run yourself** (a file exists, a test passes, output matches). Do not delegate
judgment calls or work you cannot independently grade.

## Set up the worker (first run, or a new environment)

Aim: end at a graded, working worker. Move through discover -> decide -> provision -> compile
-> verify, reasoning at each step from what is actually there.

1. **Discover.** Look, do not assume. Is a model already served? (curl the provider baseURLs in
   `~/.config/opencode/opencode.json`, or the endpoint you were told; llama.cpp `/props` reports
   `model_path`, from which you can read the quant.) Is `opencode` installed (`opencode
   --version`)? Is there a GPU and how much VRAM (`nvidia-smi`)? Are there API keys in the env
   (any `*_API_KEY`)? Whatever you find is the situation; handle it, do not force it into a
   category.

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
