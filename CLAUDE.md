# CLAUDE.md: opencode-worker

Project-specific instructions. OS-level protocol is inherited from `~/.claude/CLAUDE.md`.

## What this is

A connector that lets **Claude Code (Opus, on the Max subscription) delegate scoped agentic
work to a local OpenCode worker** driving an arbitrary model (Qwen3.8-27B is target #1). It
runs over the tool boundary (the local `opencode serve` HTTP API), so it never touches the
Claude subscription auth. The worker-facing protocol is cross-compiled per target by
skillc, and a graded transfer score proves the retarget. Full rationale and the decision
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

- Start the server FROM THE REPO ROOT so it loads the worker agent: `cd <repo> && opencode
  serve --port 47611 --hostname 127.0.0.1 &`. The protocol is that agent's system prompt; if you
  edit `protocol/opencode-worker-protocol.md`, re-run `python3 scripts/build_agent.py` and restart
  the server (agents load at startup only, no hot reload).
- Provider (already in `~/.config/opencode/opencode.json`): `mainframe-qwen38`, model
  `qwen3.8-27b`, pointing at the local endpoint `http://192.168.2.43:30801/v1`.
- Bring the model up only if the GPU rail is free (it holds both GPUs and does not preempt;
  scale back to 0 when done, and yield when VAT2 needs the cards):
  `kubectl scale deploy/qwen38-llama-serve --replicas=1` ... `--replicas=0`
  Health: `curl -s http://192.168.2.43:30801/health`. Runbook:
  `mainframe/docs/ops/qwen38-serve.md`.
- Smoke tests: `python3 tests/smoke.py` (library path), `python3 tests/mcp_smoke.py` (MCP stdio
  path), `python3 tests/agent_smoke.py` (protocol-via-agent). All expect the server up (from the
  repo root), the model served, and the worker agent loaded.
- Drive a session by hand: `python3 src/opencode_worker.py {start,steer,pending,approve,status,final,stop,run} ...`

## Hard-won API facts (reference, do not rediscover)

Against `opencode serve` v2 (`/api`):
- Responses wrap the payload under a top-level `data` key (sometimes with sibling keys).
  Always unwrap `data`. The driver's `_req` does this.
- Create session: `POST /session` with `{model:{providerID,id,variant}, location:{directory}}`;
  the returned session `id` is `ses_...`.
- Prompt / steer: `POST /session/{id}/prompt` with `{prompt:{text}, delivery:"steer"|"queue"}`.
  A PLAIN prompt (no `delivery`) STARTS the turn; `steer` injects into an ALREADY-running turn and
  will NOT start one (a fresh session given a steer sits idle at zero tokens). `POST
  /session/{id}/interrupt` halts. (Grounding found a cold receiver stuck 6+ min by starting with a
  steer.)
- The session `location.directory` (workdir) MUST live under the dir `opencode serve` was started
  from (its project root). An external dir (e.g. `/tmp/...`) makes every filesystem tool fail with
  a generic `Unable to write`/`executed:false` AND raises NO serviceable gate (external-directory
  hard-denies instead of asking), so the worker misreads a broken sandbox. Our tests only passed
  because `.work/...` is inside the repo; grounding from `/tmp` surfaced this.
- `GET /session/{id}/message` returns items NEWEST-FIRST (index 0 is newest). Find the newest assistant message by max `time.created`, never `[-1]` -- grounding caught a receiver reading a stale mid-turn message and misjudging a finished turn as running.
- Messages: `GET /session/{id}/message` returns items with `type` in {assistant,user,system}
  (no `role`). An assistant message's `content` is a list of typed parts
  (`reasoning`/`text`/`tool`); the reply text is the `text` parts of the newest assistant
  message.
- Permissions: `GET /session/{id}/permission` lists pending asks as `{id, action, resources,
  ...}` (v2) or `{id, permission, patterns, ...}` (v1). Reply:
  `POST /session/{id}/permission/{id}/reply` with `{reply:"once"|"always"|"reject"}`. Gate a
  tool by setting `permission: {<tool>: "ask"}` in `opencode.json` (per-tool allow/ask/deny;
  `bash` takes wildcard maps). A workdir-local `opencode.json` scopes it to that session. Better:
  set the gating in the AGENT frontmatter (`permission: {edit: ask, bash: ask, ...}`) so it is
  target-keyed and travels with the pack; opencode parses it into a ruleset of
  `{action, resource:"*", effect}`. Valid tool keys: read, edit, glob, grep, list, bash, task,
  external_directory, todowrite, question, webfetch, websearch, lsp, doom_loop, skill (no `write`;
  file writes gate under `edit`). The worker pack gates the mutating + external tools, leaves
  read-only allowed. `scripts/build_agent.py` renders this from the target's `settings.permission`.
- Deliver the worker protocol as an OpenCode **agent** system prompt, not prepended per task.
  Agents load from `.opencode/agent/<name>.md` (frontmatter + body = the system prompt) at server
  STARTUP ONLY: no hot reload, and `{file:...}` is NOT expanded in the `prompt`/body (it is stored
  literally). So compile the agent from the protocol (`scripts/build_agent.py` writes the md) and
  RESTART `opencode serve` from the repo root to load it. Sessions get `projectID:"global"`, so the
  per-session `location.directory` is NOT scanned for agents: a workdir-local agent file does
  nothing. Bind a session to the agent with `POST /session {agent:"<name>"}`; an unknown agent
  name is accepted but the turn silently stalls (the driver's `start` guards against this).
  Confirm what loaded via `GET /api/agent` (v2 fields: `id`, `system`).
- The session object (`GET /session/{id}`) has NO usable status/completion field here (`status`
  is absent, `time` has only created/updated). Turn state must be read from the newest assistant
  message's `finish`: `tool-calls` = mid-turn step (keep polling), `stop`/`length` = done,
  `error` = failed turn (with an `error` object). An errored turn does NOT flip any session-level
  flag, so polling the session alone hangs to budget. The driver's `_turn_status`/`overall_status`
  encode this; use them, not `_status_of(session(...))`.
- Concurrency is a SERVING-CONFIG property, not a driver limit (re-derive it each session from
  `/props`, do not freeze it). The driver holds no shared mutable state (`OpenCodeWorker` carries
  only `self.base`; every method is keyed by the `sid` argument; `run()` uses only locals), so N
  concurrent `start`/`run` calls are safe by construction. The serializer is the engine's slot
  config: `GET <model>/props` reports `total_slots` and `default_generation_settings.n_ctx` (the
  per-slot context ceiling). `--parallel N` WITHOUT `--kv-unified` STATICALLY cuts context to
  c/N (n_ctx = 65536 at N=4) and is single-tenant in effect; `--parallel N --kv-unified` shares
  ONE KV pool (n_ctx stays 262144, each request draws up to the full ceiling, continuous batching
  multiplexes the turns). tests/parallel_test.py asserts `total_slots>=N` and `n_ctx==262144`.
  As last proven (2026-08-21, live): the deployment runs `--parallel 4 --kv-unified`, /props shows
  total_slots=4 with per-slot n_ctx=262144, one SHARED 262144 KV pool (VRAM barely rose, not 4x),
  and 3-4 concurrent worker turns overlap. It is shared-pool multiplexing (each request can reach
  the full ceiling; the sum of resident sequence lengths is pool-bounded), not vLLM-style
  independent full windows. The serving axis lives in the target (`settings.serving`) and re-keys
  the pack when it flips. NOTE the mainframe manifest (k8s/qwen38-llama-serve.yaml) still says
  `--parallel 1`; the live change is a patch, so canonize it in the manifest (mainframe-e5e) or a
  re-apply reverts it. It runs ~47 tok/s (Q6_K imatrix + MTP draft-mtp speculative decoding, thinking on; the
  served file is Qwen3.8-27B-Q6_K.gguf, NOT Q8_0 - confirm via `/props` model_path); budget 120s+
  per agentic turn.
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
protocol/opencode-worker-protocol.md   model-neutral worker contract (skillc cross-compiles it)
scripts/build_agent.py                 compile the protocol -> target pack + active agent install
scripts/graded_episode.py              run graded episodes -> write the pack's grade.json
packs/<model>__<quant>__<harness>/     target-keyed worker pack: agent + manifest + grade.json
.opencode/agent/opencode-worker.md     GENERATED active agent install (the server loads this)
skills/opencode-worker/SKILL.md        Claude-side orchestrator skill (target-agnostic)
docs/design/artifact-architecture.md   the two-sided, target-keyed artifact design
tests/smoke.py                         re-runnable end-to-end check (library path)
tests/mcp_smoke.py                     re-runnable end-to-end check (MCP stdio path)
tests/agent_smoke.py                   re-runnable check: protocol delivered via agent config
tests/target_test.py                   offline check: pack keying is model/quant/settings sensitive
tests/evidence/                        the original proof scripts (scratch paths; historical)
README.md                              overview + usage
```

## Next

1. ~~Wrap the connector as an MCP server~~ DONE (2026-08-17): `src/opencode_worker_mcp.py`
   (FastMCP stdio) + `.mcp.json`; tools start/steer/pending/approve/status/final/stop/run.
   Re-runnable check: `tests/mcp_smoke.py`.
2. ~~System prompt via agent config~~ DONE (2026-08-17): the protocol is now the
   `opencode-worker` OpenCode agent's system prompt, compiled by `scripts/build_agent.py`; the
   driver binds the agent on session create and submits only the task (no prepend). Check:
   `tests/agent_smoke.py`.
3. ~~Two-sided, target-keyed artifact architecture~~ DONE (2026-08-17): capturing OpenCode is
   (a) one Claude-side orchestrator skill (target-agnostic, `skills/opencode-worker/`) plus (b) an
   opencode-side worker pack that is model/quant/settings sensitive. The target carries
   `(model, quant, harness, settings, env)`; `resolve_artifacts` keys the pack by the full target;
   `build_agent.py` emits `packs/<model>__<quant>__<harness>/` (agent + manifest + skill-pack),
   compiles the settings (permission gating + sampling) into the agent frontmatter, installs the
   active agent, and records the active target (`--list` / `.opencode/active-target.json`). The
   earned grade travels in the pack (`grade.json`), written by `scripts/graded_episode.py` and
   surfaced by `resolve_artifacts(...).grade`. Design: `docs/design/artifact-architecture.md`.
   Checks: `tests/target_test.py`, `tests/agent_smoke.py`.
4. Grow the graded co-optimization loop: more tasks/targets, routing divergences to the model
   delta overlay or the driver protocol; record earned transfer grades per target.
5. Bundle for distribution via skillc (the self-building skill compiler + grounding).
6. Not this repo: rebalance the Qwen tensor-split toward the 3090 (a `mainframe` k8s tuning
   item; the A4500 is the bottleneck under 0.57/0.43).

## Skill build + test (the process; follow it, do not re-derive)

The two skills (`skills/opencode-worker`, `skills/model-setup`) are skillc self-building files.

**Build (compile).** `SKILL.md` IS the source; author/edit it directly. skillc's canonical 84-line
rebuild recipe is stamped VERBATIM once inside it, fenced by `<!-- BEGIN/END stamped rebuild
recipe -->`; never edit inside that fence, and never add a build script or template language to
re-stamp it (a hand-rolled `emit_skill.py` was removed for exactly that inversion: software instead
of a skill). The recipe's source of truth is skillc at a PINNED TAG, not a copy vendored into this
repo: `git -C ~/projects/skillc show v0.3.0:seed/rebuild.skill.md`. To re-stamp (only when bumping
the pin), replace the fenced span with that exact output and update the pin named in each SKILL's
`<!-- BEGIN stamped rebuild recipe (verbatim from skillc@vX.Y.Z ...) -->` marker. `SKILL.md` is
the CANONICAL, target-agnostic source: it carries no target delta.

**Cross-compile (optional, for a known weak target).** A variant `<name>.<target>.SKILL.md` = the
source + a provenance header (right under the frontmatter) + that target's MEASURED delta, stamped
from `skillc/seed/targets/<target>.md`. qwen-opencode is target #1
(`opencode-worker.qwen-opencode.SKILL.md`). The delta is measured by grounding, never invented; the
grade stays "not yet measured" until a comparative run earns it. Re-derive the variant (a one-time
agent assembly, no committed script) whenever the source changes.

**Test (ouroboros / grounding). A fix is not proven until re-grounded.** Ground the COMPILED file
(the source, and each variant): spawn a FRESH agent (Agent tool, `general-purpose`, NOT a fork)
given ONLY that one `SKILL.md` path and told to read nothing else in the repo. Live env: `opencode
serve` up from the repo root, the worker agent loaded, a model served (bring Qwen up per the
runbook). Have it delegate a small independently-verifiable task and honest-grade it; it reports
built / honest-failure / cannot-build and where the file left it guessing. Route each finding: an
opencode API / drive-loop fact is SKILL CONTENT -> the source; a model-mis-follow habit (relabeling
a failed check, over-probing) is a TARGET DELTA -> `skillc/seed/targets/<target>.md`. Re-stamp the
variant, re-ground. The transfer grade is `loss = score(claude reference) - score(target)` on the
same tasks.

**Public-copy invariant.** No em-dashes (unicode `—` or prose ` -- `), and run the
`avoid-ai-writing` pass over the README + skills before any release.

## Relationships

- `dap` owns the spec (`docs/specs/opencode-worker-integration.md`, `opencode-worker-protocol.md`).
- `skillc` owns the skill build, cross-compile, and grounding (the comparative transfer grade,
  `loss = score(reference) - score(target)`); target profiles live in `skillc/seed/targets/`
  (the `qwen-opencode` target is already seeded). (These moved out of `hoistable` into `skillc`.)
- This repo owns the connector implementation and its packaging as a skill.
