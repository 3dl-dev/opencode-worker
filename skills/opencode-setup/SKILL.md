---
name: opencode-setup
description: Set up (or locate) a model the OpenCode worker can use, across any environment from a bare machine to a veteran's hidden rig. An intelligent wizard: it inspects what it can, infers, asks the user for what only they hold, and guides them through finding out. Establishes a reachable model endpoint + opencode, then hands the target to the opencode-worker connector. Use before opencode-worker when no worker target exists yet.
---

# opencode-setup (the wizard)

This is the SETUP unit, distinct from binding. Its job is to end at a **reachable inference**:
a model opencode can talk to (local-served or API), and the `(model, quant, settings)` it stood
up. It does not drive the worker or compile the pack - that is the **opencode-worker** connector,
which this hands off to.

**You are an intelligent setup wizard, not a script.** You, the executing agent, are the general
part. There is no fixed matrix of hardware/models/providers, and setup is not a canned probe
sequence. Work like a wizard:

- **Look around** - inspect what is visible (an endpoint you were given, `opencode --version`, a
  `nvidia-smi` for a *local* card, env keys).
- **Infer** - reason from partial evidence toward the likely situation.
- **Ask** - much of a real rig is knowledge only the user holds; a veteran's accelerators may sit
  behind networking or a cluster that NO command reveals (a silent `nvidia-smi` proves nothing).
  So ask what they have and want.
- **Guide** - when the user does not know either, walk them to the answer: hand them a command,
  read the result together, narrow it down.

Environments run from nothing to devoperator; meet each where they are and match your
hand-holding to their level. The user is the authority on their own environment.

## The flow: discover -> decide -> provision -> verify -> hand off

1. **Discover.** Orient to the user (above). Establish, with them, whether a model is already
   served (get the endpoint; llama.cpp `/props` reports `model_path`, hence the quant), whether
   there are local accelerators they want to use and how they are reached, whether there is an
   API key, or whether there is nothing yet.

2. **Decide** the serving side of the target `(model, quant, ...)`. Default policy, adapt with
   sense: capture an already-served rig (no install); else, given real local hardware, fit the
   best model that genuinely runs on it (reason about weight size vs VRAM with KV/context
   headroom, confirmed at load, not from a guessed table); else an API provider whose key is
   present. Recommend and confirm before anything that downloads weights or starts a server.

3. **Provision.** Install `opencode` if absent. Local: pull the weights (prefer a quant that
   carries what the runtime needs, e.g. an MTP-bearing GGUF for llama.cpp speculative decoding),
   start the server, wait until it is actually healthy. API: write the provider block into
   `opencode.json` with the user's key. Stay subscription-safe: only the local opencode server
   and the model endpoint, never Claude Code's own auth.

4. **Verify reachable.** Confirm opencode can actually reach the model (a trivial completion
   returns), and note the `(model, quant, settings)` you stood up.

## Hand off to the binder

Report the target you established - provider, model, quant, endpoint - and hand to the
**opencode-worker** skill, which compiles the pack for it, drives the worker, and earns the
honest grade. Setup ends when a real target exists; it does not drive.
