#!/usr/bin/env python3
"""Multi-tenancy check: N concurrent worker sessions, full context, engine-multiplexed.

This is the done-spec for opencodeworker-670. It proves two independent things and reports a
third:

  1. DRIVER concurrency-safety (this repo owns this, engine-independent). Fire N `run()` calls
     concurrently from ONE process on ONE OpenCodeWorker instance. Assert: every task builds
     (ground-truth check on disk, never the worker's self-report), every honest-outcome matches,
     and the N sessions are DISTINCT (no cross-session state bleed in the driver). The driver holds
     no mutable state beyond `self.base`, so this must hold; the test is the standing proof.

  2. SERVING multi-tenancy invariant (the substrate must provide it; mainframe owns the config).
     Read the model endpoint's /props. Assert total_slots >= N AND the per-slot context ceiling
     (default_generation_settings.n_ctx) == the full model context. This is the machine-checkable
     "no static c/N cut": llama.cpp `--parallel N` WITHOUT `--kv-unified` reports n_ctx = c/N
     (e.g. 65536 for 262144/4) and FAILS here; WITH `--kv-unified` it stays 262144 (one shared KV
     pool, each request may draw up to the full ceiling) and PASSES. vLLM/SGLang paged-KV report
     the full max-model-len the same way.

  3. Wall-clock overlap (reported, not asserted): concurrent wall-clock vs the slowest single
     task. Continuous batching multiplexes the N turns, so concurrent time should be well under
     the serial sum. Printed as an efficiency signal; the pass/fail gates are (1) and (2).

Ground-source discipline: nothing here is skipped. Against a single-slot engine, (2) FAILS
loudly (slots=1 < N) - that is the honest state "the driver is safe but the substrate is not yet
multi-tenant", not a green light. The suite goes green only once the serving config is unified
N-slot.

Prereqs (same as tests/smoke.py):
  1. `opencode serve --port 47611 --hostname 127.0.0.1 &` (from the repo root)
  2. The target model served with a unified N-slot KV pool.
Env:
  OPENCODE_BASE     driver -> opencode server (default http://127.0.0.1:47611/api)
  MODEL_PROPS_URL   model endpoint /props for the serving invariant
                    (default http://192.168.2.43:30801/props, the mainframe qwen rail)
  PARALLEL_N        number of concurrent workers (default 3)
Exit 0 on PASS.
"""
import os, sys, json, time, threading, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from opencode_worker import OpenCodeWorker, DEFAULT_TARGET, resolve_artifacts  # noqa: E402

BASE = os.environ.get("OPENCODE_BASE", "http://127.0.0.1:47611/api")
PROPS_URL = os.environ.get("MODEL_PROPS_URL", "http://192.168.2.43:30801/props")
N = int(os.environ.get("PARALLEL_N", "3"))
# The full context ceiling this target must preserve per request (no c/N cut). Sourced from the
# declared target settings so it tracks the pack, not a magic number.
FULL_CTX = int((DEFAULT_TARGET.get("settings") or {}).get("context", 262144))
BUDGET = int(os.environ.get("PARALLEL_BUDGET", "480"))


def serving_invariant():
    """Read /props and check the substrate offers N unified slots at the full context ceiling.
    Returns (ok, detail_dict). A single request must be able to reach FULL_CTX while N run
    concurrently, i.e. slots >= N and per-slot n_ctx == FULL_CTX (one shared pool, not c/N)."""
    try:
        with urllib.request.urlopen(PROPS_URL, timeout=15) as r:
            props = json.loads(r.read().decode())
    except (urllib.error.URLError, ValueError, OSError) as e:
        return False, {"error": f"cannot read {PROPS_URL}: {e}"}
    slots = props.get("total_slots")
    n_ctx = (props.get("default_generation_settings") or {}).get("n_ctx")
    ok = isinstance(slots, int) and slots >= N and n_ctx == FULL_CTX
    return ok, {"total_slots": slots, "per_slot_n_ctx": n_ctx,
                "required_slots": f">={N}", "required_n_ctx": FULL_CTX,
                "model": (props.get("model_path") or "?").split("/")[-1]}


# One independently-verifiable task per worker: write a distinct token to a distinct file, and
# claim DONE only if written. Ground-truth = the file holds the token; honest = the DONE claim
# matches ground truth. Distinct tokens/files make cross-session bleed detectable.
def make_task(i):
    token = f"PARALLEL-{i}-OK"
    fname = f"para_{i}.txt"
    task = (f"TASK: In your working directory create a file {fname} containing exactly the text "
            f"{token} (nothing else). Then reply DONE only if the file was written.")
    return token, fname, task


def build_ok(wd, fname, token):
    p = os.path.join(wd, fname)
    try:
        return os.path.exists(p) and open(p).read().strip() == token
    except OSError:
        return False


def worker_run(i, results, worker):
    token, fname, task = make_task(i)
    wd = os.path.join(ROOT, ".work", "parallel", f"w{i}")
    os.makedirs(wd, exist_ok=True)
    for f in os.listdir(wd):
        try: os.remove(os.path.join(wd, f))
        except OSError: pass
    t0 = time.time()
    sid, final = worker.run(task, wd, target=DEFAULT_TARGET, approve=lambda p: "once", budget=BUDGET)
    dt = time.time() - t0
    built = build_ok(wd, fname, token)
    claimed_done = "DONE" in (final or "").upper()
    honest = (claimed_done == built)  # DONE iff actually built; a false DONE or false failure is dishonest
    results[i] = {"i": i, "session": sid, "built": built, "claimed_done": claimed_done,
                  "honest": honest, "seconds": round(dt, 1), "final": (final or "")[:80]}


def main():
    art = resolve_artifacts(DEFAULT_TARGET)
    print(f"[parallel] target {art['key']}", flush=True)
    print(f"[parallel] N={N} concurrent workers, full-ctx ceiling={FULL_CTX}", flush=True)

    # (2) serving invariant first: it is cheap and tells us if multi-tenancy is even provisioned.
    serving_ok, serving_detail = serving_invariant()
    print(f"[parallel] serving invariant: {'PASS' if serving_ok else 'FAIL'} {serving_detail}", flush=True)

    # (1) + (3): fire N concurrent run() calls on ONE shared worker instance.
    worker = OpenCodeWorker(BASE)
    results = [None] * N
    threads = [threading.Thread(target=worker_run, args=(i, results, worker)) for i in range(N)]
    wall0 = time.time()
    for t in threads: t.start()
    for t in threads: t.join()
    wall = time.time() - wall0

    for r in results:
        print(f"[parallel] w{r['i']}: session={r['session']} built={r['built']} "
              f"honest={r['honest']} {r['seconds']}s final={r['final']!r}", flush=True)

    sessions = [r["session"] for r in results]
    distinct = len(set(sessions)) == N and all(sessions)
    all_built = all(r["built"] for r in results)
    all_honest = all(r["honest"] for r in results)
    slowest = max(r["seconds"] for r in results)
    overlap = round(sum(r["seconds"] for r in results) / wall, 2) if wall > 0 else 0.0

    print(f"[parallel] wall={round(wall,1)}s slowest-single={slowest}s "
          f"sum-of-tasks={round(sum(r['seconds'] for r in results),1)}s overlap={overlap}x", flush=True)
    print(f"[parallel] driver: distinct-sessions={distinct} all-built={all_built} "
          f"all-honest={all_honest}", flush=True)

    driver_ok = distinct and all_built and all_honest
    ok = driver_ok and serving_ok
    print("RESULT:", "PASS" if ok else "FAIL",
          "" if ok else f"(driver_ok={driver_ok}, serving_ok={serving_ok})", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
