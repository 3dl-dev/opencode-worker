# Successor prompt: multi-tenancy for the opencode-worker skill

Paste the block below into a fresh session. It carries the research so you do not re-derive it;
verify against the live system, do not treat it as frozen.

---

## Objective

Give the opencode-worker skill **multi-tenancy**: N concurrent worker sessions driven from one
Claude Code session, each keeping the full ~262K context ceiling, with the inference engine
multiplexing them across the GPUs. No static per-slot context cut. When done, Claude fans out M
subagent tasks, they run genuinely concurrently on the local model, each with full context, and
every result is honest-graded.

## What is already true (verify, do not re-litigate)

- The connector + skill work and drive the worker **natively**: a fresh CC session given only a goal
  plus an offload policy runs preflight, delegates each build to the worker, and honest-grades with
  zero step-by-step direction (proven 2026-08-20; capture in `marketing/cc_session.cast`).
- The blocker to parallelism is the **serving config**, not the skill. Today Qwen is served by the
  k3s deployment `qwen38-llama-serve` with `llama-server -c 262144 --parallel 1` (GGUF Q6_K).

## Core finding (the research this is based on)

- llama.cpp `--parallel N` **statically splits** `-c` into N equal slots of c/N. That is the
  262K to 65K cut, and it is the engine's crude model, not a hardware limit. Bumping `--parallel`
  is the wrong fix: it guts per-request context.
- The right mechanism is **continuous batching + paged KV**: one KV pool sized to VRAM; each request
  draws blocks on demand up to a 262K *ceiling* (not a reservation); a shared batch runs concurrent
  requests. A single request can still take the full 262K; many short subagent tasks pack in
  dynamically. Claude just fires N `run` calls and the engine multiplexes.
- Engines that do this:
  - **SGLang (RadixAttention)** is the pick. Paged KV + continuous batching + **prefix caching**.
    Every fan-out subagent hits the same worker-agent system prompt (the protocol), so that prefix is
    computed once and reused across all concurrent calls. Fan-out is its best case.
  - **vLLM (PagedAttention + automatic prefix caching)** is the equivalent, slightly less specialized
    for the shared-prefix pattern.
- Honest scope, so nobody expects a flag flip: this is a **serving swap on the mainframe rail**.
  Different quant (FP8 ~27 GB or AWQ ~15 GB, NOT the current GGUF Q6_K). Spec-decode must be
  re-tuned (both engines have MTP/EAGLE paths; not drop-in). On the 3090 + A4500 (44 GB) a 27B at
  FP8/AWQ plus a paged KV pool fits; achievable concurrency is roughly KV-pool-tokens divided by
  actual-tokens-per-request. Start with AWQ for maximum KV headroom.

## Work, in two layers (route correctly)

1. **Serving substrate (mainframe-owned).** Stand up SGLang serving Qwen3.8-27B (AWQ first) with
   paged KV, a 262K max-model-len ceiling, and prefix caching, on the k3s GPU rail, OpenAI-compatible
   endpoint. Verify: several concurrent requests each able to reach 262K, prefix reuse active, and a
   real wall-clock win versus serial. Replaces `qwen38-llama-serve`. Runbook:
   `mainframe/docs/ops/qwen38-serve.md`. Yield the cards when VAT2 needs them. This likely lands as a
   `mainframe` item; wire the cross-repo rd ref.
2. **Skill and driver multi-tenancy (this repo).**
   - Retire the single-slot assumption. CLAUDE.md line "Qwen is single-slot (`--parallel 1`): do NOT
     run two worker sessions at once, they serialize" becomes false; re-derive it from the live
     engine and rewrite it, do not freeze a new claim in its place.
   - Make concurrent `start`/`run` safe. Audit `src/opencode_worker.py` (the `OpenCodeWorker` class
     is keyed by session id and has no locks/globals today, so this should hold, but confirm no
     shared mutable state in the drive/poll loop) and `src/opencode_worker_mcp.py` (several `run`
     tool calls in flight within one CC session). Confirm `opencode serve` handles concurrent
     sessions to one provider.
   - Target is a parameter: the engine (SGLang vs llama.cpp) is part of `(model, quant, harness,
     settings, env)`. `resolve_artifacts(target)` and `scripts/build_agent.py` should carry the
     engine/settings so the pack keys on it; check nothing hard-codes single-slot.
   - Tests: add `tests/parallel_test.py` that fires >=3 concurrent `run` calls, asserts all build and
     honest-grade pass, and asserts each ran with the full context ceiling (no c/N cut). Ground-source
     discipline: every test runs, none skipped.

## Proof (honest-grade discipline)

- Re-capture a true parallel native fan-out (multiple concurrent worker sessions, engine
  multiplexing) and measure wall-clock against the serial baseline (the 2m52s native run), confirming
  each subagent kept full context. Evidence under `tests/evidence/`. This also unlocks the parallel
  marketing demo; the "serial is honest" framing in `marketing/` then goes away.
- Record the transfer grade per target: `loss = score(reference) - score(target)` on the same tasks.
  skillc owns the grade; target profiles live in `skillc/seed/targets/`.

## Guardrails

- **Subscription-safe.** The connector only ever talks to the local opencode server. The engine swap
  stays behind the same local endpoint; never route Claude Code through a gateway.
- **Honest grade.** The worker's DONE is not evidence; verify with your own check. Outcome is binary.
- **Target is a parameter.** OpenCode, Qwen, and now the serving engine are values, not fixtures.
- No em-dashes in anything Baron reads. Commit only when asked; branch off main.
- Cross-repo: `dap` owns the spec (`docs/specs/opencode-worker-integration.md`, section 7b is the
  co-optimization loop), `skillc` owns the skill build and grade, `mainframe` owns Qwen serving.

## First step

Run `tests/smoke.py` to confirm the environment. Read the spec section 7b and
`mainframe/docs/ops/qwen38-serve.md`. Then decide serving-first (stand up SGLang AWQ, then make the
driver concurrency-safe against the real multiplexing engine) versus driver-first (prove
concurrency-safety against llama.cpp `--parallel N` as a throwaway harness, accepting the temporary
context cut, then swap). Recommendation: serving-first, so the driver is exercised against the engine
it will actually run on.
