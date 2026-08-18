# opencode-worker

Offload agentic work from Claude Code to a **cheaper local or API model**, subscription-safe,
and trust the result because it is honest-graded. You keep driving Claude Code; a worker (OpenCode
driving any model, e.g. a local Qwen on your GPU) does the labor. **It ships as a skill that sets
itself up in your session — there is nothing to install by hand and no commands to memorize.**

## Why

Claude Code cannot host a foreign-model subagent: its model is session-wide, per-subagent provider
routing is unimplemented, and a router needs an API token, not your Max/Pro subscription. So this
does not fight the harness. It connects over the **tool boundary**: Claude stays the orchestrator
on your subscription, and the worker does multi-step work for free (local) or cheap (API). Nothing
reroutes Claude's auth. What you lose is the cosmetic native-subagent wrapper; what you keep is
everything functional: agentic multi-step work, live mid-turn correction, permission approval under
your control, and an honest pass/fail on the real result.

## Use it — the skill does the work

Two self-building skills. Drop them in your agent's skills folder (or install the plugin); on first
use each one **rebuilds itself against your machine, tests itself, and reports plainly** whether it
works there. You run no setup commands.

- **`opencode-setup`** — an intelligent wizard that stands up (or finds) a worker for *your*
  environment, anywhere on the spectrum from a bare laptop to a hidden GPU rig. It looks around,
  infers, asks you what only you know, and guides you through finding the rest: capture a model you
  already serve, fit and serve a local model to your GPU, or wire up an API provider. It installs
  what is missing and verifies the worker is actually reachable.
- **`opencode-worker`** — delegate a scoped, checkable task to that worker and **honest-grade** it.
  It is the entry point: if no worker exists yet, it invokes `opencode-setup` for you first, then
  drives the worker, gates its permissions under your control, steers it mid-run, and returns a
  binary verdict on the *real* result.

That is the whole user experience: install the skill, ask it to offload a task, approve or steer as
it goes. The skills carry their own recipe and grade themselves on your setup — if they can't reach
the author's quality on your machine, they tell you so instead of quietly doing the wrong thing.

The shippable files are `skills/opencode-worker/opencode-worker.skill.md` and
`skills/opencode-setup/opencode-setup.skill.md` (self-contained; they fetch nothing).

## The honest grade (the point)

The worker's "DONE" is a claim, not evidence. Every outcome is checked by execution against what
the task actually requires — does it do what it must, and only what it must — independent of the
worker's self-report. The result is binary: **built** only when every check passes, otherwise
**honest-failure**. A weak local model that fails *honestly* is safe to delegate to; that discipline
is carried in the skill as prose, followed in your session.

## How it works (internals)

You don't need any of this to use it, but if you're curious:

- **Two sides, one seam.** The Claude-side skills above orchestrate; an opencode-side **worker
  pack** (`packs/<model>__<quant>__<harness>/`) carries the target's system prompt, settings, and
  earned grade. The seam between them is the **target** `(model, quant, harness, settings, env)` —
  every axis a parameter, none a fixture, because a different model/quant/serving-setting needs a
  different pack. See `docs/design/artifact-architecture.md`.
- **Protocol as system prompt.** The worker runs under a strict, model-neutral protocol
  (`protocol/opencode-worker-protocol.md`) delivered as its OpenCode agent's system prompt, not
  prepended per task. Per-target corrections are added only by *measured* divergence.
- **Grounding.** How a target earns its grade: run it on real work, find where it falls off,
  correct the target's delta (prose), re-verify. `skillc` owns the method (`loss = score(reference)
  - score(target)`); this repo carries the connector and its packaging as a skill.
- **The connector** (`src/opencode_worker.py`, and an MCP server `src/opencode_worker_mcp.py`) is
  the deterministic driver the skill's prose leans on — a stable client for `opencode serve`. It is
  build/dev tooling, not something a receiver runs by hand.

## Repo layout

```
skills/opencode-worker/     the Claude-side binder skill (self-building) + its template + SKILL.md
skills/opencode-setup/      the Claude-side setup wizard skill (self-building) + template + SKILL.md
protocol/                   the model-neutral worker protocol (source of truth)
packs/<target>/             the target-keyed worker pack (agent, manifest, earned grade)
seed/rebuild.skill.md       the canonical rebuild recipe stamped into each self-building skill
scripts/                    build_agent.py (compile a pack), emit_skill.py (emit a skill), grounding
src/                        the connector: driver + MCP server (internals)
docs/design/                the architecture and setup-flow design records
tests/                      re-runnable checks (smoke, mcp_smoke, agent_smoke, target keying)
```
