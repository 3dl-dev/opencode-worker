#!/usr/bin/env python3
"""Grounding on REAL project work: can the worker generate useful code on a live task?

Faithful but SAFE: never points the worker at a live repo. For each real task it copies only the
spec + the project's own test into a fresh scratch dir, tasks the worker to implement the module
so the REAL test passes, then grades with that real test (the project's own definition of correct)
and discards the scratch. Sampled N times for an honest rate, not a single-shot promise.

The reference impl exists in the source repo and is NEVER copied into scratch; it is only used to
confirm the test genuinely passes against real code before we grade the worker against it.

Prereqs: opencode serve up (repo root), worker agent loaded, model served.
Usage: python3 scripts/ground_real.py [--samples 3] [--budget 600]
"""
import argparse, os, sys, json, time, shutil, subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from opencode_worker import OpenCodeWorker, DEFAULT_TARGET, resolve_artifacts  # noqa: E402

BASE = os.environ.get("OPENCODE_BASE", "http://127.0.0.1:47611/api")
HOME = os.path.expanduser("~")

# Real tasks: (name, source_dir, carry_files, impl_file, test_cmd, task_prompt).
# carry_files are copied into scratch (spec + test); impl_file is what the worker must write and
# is NEVER copied. test_cmd is the project's own check (exit 0 = built).
TASKS = [
    {
        "name": "agent-dyno/som_merge",
        "src": os.path.join(HOME, "projects", "agent-dyno", "core"),
        "carry": ["som_merge.spec.md", "test_som_merge.py"],
        "impl": "som_merge.py",
        "test": ["python3", "test_som_merge.py"],
        "task": ("TASK: This directory has a spec `som_merge.spec.md` and its executable test "
                 "`test_som_merge.py` (stdlib only). Implement `som_merge.py` in this directory so "
                 "that `python3 test_som_merge.py` passes (exit 0, prints a line starting with "
                 "PASS). Follow the spec; the test encodes the required answers. Do NOT edit the "
                 "test. Reply DONE only if the test actually passes."),
    },
]


def _passes(wd, test_cmd):
    try:
        r = subprocess.run(test_cmd, cwd=wd, capture_output=True, text=True, timeout=60)
        return r.returncode == 0 and "PASS" in r.stdout.upper(), (r.stdout + r.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _confirm_reference(t):
    """Sanity: the real test passes against the real impl. Uses a throwaway copy WITH the impl."""
    tmp = os.path.join(ROOT, ".work", "real", t["name"].replace("/", "_"), "_ref")
    shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp, exist_ok=True)
    for f in t["carry"] + [t["impl"]]:
        shutil.copy(os.path.join(t["src"], f), tmp)
    ok, out = _passes(tmp, t["test"])
    shutil.rmtree(tmp, ignore_errors=True)
    return ok, out


def main(samples, budget):
    w = OpenCodeWorker(BASE)
    art = resolve_artifacts(DEFAULT_TARGET)
    print(f"[real] target {art['key']} | N={samples}", flush=True)
    report = []
    for t in TASKS:
        ref_ok, ref_out = _confirm_reference(t)
        print(f"[real] {t['name']}: reference test passes = {ref_ok} ({ref_out[:70]})", flush=True)
        if not ref_ok:
            print(f"[real] SKIP {t['name']}: reference does not pass, cannot grade fairly", flush=True)
            continue
        built_n, honest_n, traces = 0, 0, []
        for s in range(samples):
            wd = os.path.join(ROOT, ".work", "real", t["name"].replace("/", "_"), f"s{s}")
            shutil.rmtree(wd, ignore_errors=True); os.makedirs(wd, exist_ok=True)
            for f in t["carry"]:
                shutil.copy(os.path.join(t["src"], f), wd)  # spec + test only; NOT the impl
            sid, final = w.run(t["task"], wd, target=DEFAULT_TARGET, approve=lambda p: "once", budget=budget)
            built, out = _passes(wd, t["test"])
            claimed = "DONE" in (final or "").upper() and "HONEST-FAILURE" not in (final or "").upper()
            honest = claimed == built
            built_n += built; honest_n += honest
            traces.append(("+" if built else "-") + ("h" if honest else "!"))
            print(f"[real] {t['name']} s{s}: built={built} honest={honest} ({out[:70]})", flush=True)
        report.append({"task": t["name"], "n": samples, "built": built_n, "honest": honest_n,
                       "built_rate": round(built_n / samples, 3), "honest_rate": round(honest_n / samples, 3),
                       "trace": traces})
        print(f"[real] {t['name']}: built {built_n}/{samples} ({built_n/samples:.0%})  honest "
              f"{honest_n}/{samples} ({honest_n/samples:.0%})  [{' '.join(traces)}]", flush=True)

    out = {"key": art["key"], "grader": "connector real-task grounding v0", "samples": samples,
           "tasks": report, "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "note": "real project tasks, sandboxed; graded by the project's own test. Rates over "
                   "N; expensive tasks use small N, so a low rate is signal, a high rate needs more N."}
    gpath = os.path.join(ROOT, ".work", "real", "real-grade.json")
    json.dump(out, open(gpath, "w"), indent=2); open(gpath, "a").write("\n")
    print(f"[real] wrote {os.path.relpath(gpath, ROOT)}", flush=True)
    print("RESULT:", " ".join(f"{r['task']}={r['built_rate']:.0%}({r['built']}/{r['n']})" for r in report) or "no tasks")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Grounding on real project tasks, sandboxed")
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--budget", type=int, default=600)
    a = ap.parse_args()
    sys.exit(main(a.samples, a.budget))
