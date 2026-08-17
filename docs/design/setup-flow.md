# End-to-end setup: the skill bootstraps a worker for the user's mix

Status: design skeleton, 2026-08-17. A plan, not a commitment; the phases hold, the Phase-2
specifics depend on which runtimes we support (an open decision, below).

## Why

"The target is a parameter" (`resolve_artifacts(target)`) has a front end we have not built: the
target must be **discovered and provisioned**, not assumed. Shipped as a skill, the Opus loop
starts from a bare machine and has to end at a graded, working worker.

## This is a skill, not a program

The setup is executed by the intelligent agent reading the skill, NOT by a Python classifier that
tries to enumerate every environment and shatters on the first case it did not predict. The agent
runs real commands (`nvidia-smi`, `opencode --version`, curl an endpoint), reads whatever is
actually there, and reasons about it. The skill gives it the PROCEDURE and the judgment cues;
the model supplies the generality. Deterministic tools are invoked only where determinism earns
its place: the connector driver (a stable API client) and the pack compile. Hardware, model,
quant, and provider are open sets handled by the agent's reasoning, never a hardcoded matrix.

## Two distinct units, one seam

Setting up the inference and binding Claude Code to it are DIFFERENT units, not one flow:

- **opencode-setup (the wizard)** owns DISCOVER -> DECIDE -> PROVISION -> VERIFY-REACHABLE. It
  ends at a model opencode can actually reach and the `(model, quant, settings)` it stood up.
- **opencode-worker (the binder)** owns COMPILE -> DRIVE -> GRADE -> CROSS-COMPILE. It takes that
  target and makes Opus able to drive it as a worker.

The seam is the **target**: setup produces one, the binder consumes it. Keeping them separate
means the wizard can serve any environment without dragging in connector internals, and the
connector stays a clean driver that assumes a target exists.

## The pipeline (both units)

```
[ setup: DISCOVER -> DECIDE -> PROVISION -> VERIFY-reachable ]  ==target==>  [ binder: COMPILE -> DRIVE -> GRADE ]
```

- **DISCOVER (orient to the user, do not just probe).** Configs run from nothing to a veteran
  whose accelerators sit behind networking or a cluster that no command reveals - a silent
  `nvidia-smi` means nothing. Much of a real rig is knowledge only the user holds, so establish
  it WITH them: ask what they have and want, gauge newbie-to-devoperator, and probe only where it
  confirms something they named. Output: the situation as the user and the evidence together
  describe it, and the viable directions (capture / local / API). No side effects.
- **DECIDE (target selection).** Pick local-vs-API and the concrete `(model, quant, settings)`.
  Quant-fitting is a real heuristic: largest quant that fits VRAM with the desired KV cache (data
  points in `mainframe/docs/ops/qwen38-serve.md`: Q6_K weights 23.5 GB, 262K KV in 44 GB with
  q8_0 KV). This is where the product-scope decisions live (below).
- **PROVISION (install/serve).** Install opencode if absent. Local: pull the GGUF (MTP-bearing
  quant where available), start the server, wait healthy. API: write the opencode provider config
  with the user's key. Subscription-safe throughout: Claude Code's own auth is never rerouted.
- **COMPILE (cross-compile the pack for the mix).** `resolve_artifacts(target)` -> the pack for
  that exact target. A known target uses its packaged pack; a NEW `(model, quant, settings)` is
  skillc's cross-compile (protocol core + measured overlay -> per-target agent/settings/skills).
  Install the active agent + settings.
- **VERIFY.** Run smoke + a graded episode; require honest-outcome; report the earned grade. On
  failure, surface the divergence (route to the target's delta overlay or the driver protocol).

The skill instructs the agent to run each phase WITH JUDGMENT; skillc owns COMPILE's
cross-compile and the transfer score. The phases above are the shape of the SETUP section of
`skills/opencode-worker/SKILL.md`, written as instructions, not code.

## The skill states a default policy, it does not hardcode a matrix

The agent follows a stated default and adapts: capture an already-served rig first; else, if
there is a GPU, fit and stand up the best local model it can (reasoning about VRAM against real
weight sizes, confirming at load, not against a baked table); else use an API provider whose key
is present. Prefer recommend-and-confirm before anything that downloads or starts a server. None
of local/API, model, quant, or provider is fixed; the agent decides from what it finds.

## First step

Write the SETUP section of the skill (agent instructions for discover -> decide -> provision ->
compile -> verify). No probe program: the executing agent is the general part.
