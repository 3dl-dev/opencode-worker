# Artifact architecture: two sides, one target-keyed worker pack

Status: design of record for THIS repo's artifact layout, 2026-08-17. A plan, re-derive
against the code; the spec of record stays `dap:docs/specs/opencode-worker-integration.md`.

## The shape

Capturing an OpenCode worker is not one artifact. It is two, on opposite sides of the tool
boundary:

1. **Claude side (orchestrator skill).** One skill, `skills/opencode-worker/SKILL.md`. It runs
   in the Opus loop and is **target-agnostic**: it teaches Opus to resolve the target, install
   the right worker pack, drive the connector (the MCP tools / CLI), approve permission gates,
   steer mid-run, and HONEST-GRADE the result with its own checks. It does not encode any one
   model's quirks; those live in the worker pack.

2. **OpenCode side (worker pack).** A bundle the *worker* runs under, **keyed by the full
   target** and therefore sensitive to model, quant, and serving/sampling settings. It holds:
   - the **system prompt** — the OpenCode agent (`.opencode/agent/<name>.md`), compiled from the
     protocol core plus this target's measured delta overlay;
   - a **skill-pack** — any OpenCode skills the worker itself uses (`.opencode/skills/...`),
     target-specific where a weaker model needs them;
   - **settings** — the opencode.json fragments for this target: permission gating, model +
     variant, sampling (temperature/top_p), context.

The same protocol prose, driven on a different (model, quant, settings), is a different pack. A
grade is earned per target, so the pack is where a target's measured corrections accumulate.

## Target = (model, quant, harness, settings, env)

Every axis is a parameter, none a fixture. The wire model object OpenCode accepts on
`POST /session` is only `{providerID, id, variant}` (extra keys rejected), so quant and settings
are **sibling** axes on the target, never folded into `model`:

```
{
  "model":    {"providerID": "mainframe-qwen38", "id": "qwen3.8-27b"},  # wire-safe
  "quant":    "Q8_0",
  "harness":  "opencode",
  "settings": {"context": 262144, "thinking": true},                    # behavior-affecting
  "env":      null
}
```

`resolve_artifacts(target)` keys everything by this whole tuple: `key` includes the quant and a
stable signature of `settings`, so a settings change routes to a different pack / grade rather
than silently reusing the wrong one.

## Layout and flow

```
skills/opencode-worker/SKILL.md            Claude-side orchestrator skill (target-agnostic)
protocol/opencode-worker-protocol.md       protocol source (core + measured overlays)
packs/<model>__<quant>__<harness>/         the worker pack SOURCE for a target
  agent/opencode-worker.md                 compiled system prompt for this target
  manifest.json                            exact model/quant/settings + resolve key
  (opencode.json, skills/ ...)             settings + skill-pack (added as measured)
.opencode/agent/opencode-worker.md         the ACTIVE install the server loads at startup
```

Flow: `scripts/build_agent.py --provider ... --model ... --quant ...` compiles the protocol into
the target's pack AND installs the active agent; restart `opencode serve` from the repo root
(agents load at startup only). The driver binds each session to the agent and submits only the
task. Because OpenCode loads one fixed agent path, exactly one target is "active" at a time;
installing selects it.

## Implemented vs pending

- Implemented:
  - target carries model/quant/settings; `resolve_artifacts` keys the pack by the full target;
  - the system prompt is delivered via the agent (not prepended);
  - `build_agent.py` emits the pack (agent + manifest) and installs the active agent for a target;
  - **settings are compiled into the agent frontmatter**: our-side permission gating (mutating +
    external tools ask, read-only allowed) and sampling, so gating is explicit and target-keyed,
    not a server default;
  - **install selection**: one target is active at a time, recorded in
    `.opencode/active-target.json`; `build_agent.py --list` shows packs and the active one; the
    pack's OpenCode **skill-pack** (`packs/<slug>/skills/`) installs to `.opencode/skills/`.
- Pending:
  - the skill-pack is honestly empty until a real divergence is measured (overlays/skills are
    added from measured episodes, never invented);
  - wiring the earned grade into `resolve_artifacts(...).grade` (needs the graded loop);
  - hoistable owns the cross-compile that emits a pack per target and the graded transfer score.
