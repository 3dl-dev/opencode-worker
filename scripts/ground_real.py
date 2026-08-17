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

# Real tasks. carry = [(real_src_abs, scratch_relpath)] copied into scratch (spec/header + the
# project's own test). impl = (real_src_abs, scratch_relpath): what the worker must WRITE; its real
# source is NEVER copied into scratch, only used to confirm the reference passes. test = the
# project's own check command run in scratch (exit 0 AND "PASS" in stdout = built).
AD = os.path.join(HOME, "projects", "agent-dyno", "core")
VMS = os.path.join(HOME, "projects", "vms-00c-wt")
TASKS = [
    {
        "name": "agent-dyno/som_merge",
        "carry": [(os.path.join(AD, "som_merge.spec.md"), "som_merge.spec.md"),
                  (os.path.join(AD, "test_som_merge.py"), "test_som_merge.py")],
        "impl": (os.path.join(AD, "som_merge.py"), "som_merge.py"),
        "test": ["python3", "test_som_merge.py"],
        "task": ("TASK: This directory has a spec `som_merge.spec.md` and its executable test "
                 "`test_som_merge.py` (stdlib only). Implement `som_merge.py` in this directory so "
                 "that `python3 test_som_merge.py` passes (exit 0, prints a line starting with "
                 "PASS). Follow the spec; the test encodes the required answers. Do NOT edit the "
                 "test. Reply DONE only if the test actually passes."),
    },
    {
        "name": "vms/ods2_reader",
        "carry": [(os.path.join(VMS, "src/vmsfs/include/vmsfs/ods2.h"), "vmsfs/ods2.h"),
                  (os.path.join(VMS, "tests/ods2/test_ods2.c"), "test_ods2.c")],
        "impl": (os.path.join(VMS, "src/vmsfs/ods2/ods2_reader.c"), "ods2_reader.c"),
        "test": ["bash", "-c", "gcc -std=c11 -I. test_ods2.c ods2_reader.c -o test_ods2 && ./test_ods2"],
        "task": ("TASK: This directory has the header `vmsfs/ods2.h` (genuine ODS-2 / Files-11 "
                 "structures + the reader API, with the layout fixed by _Static_assert) and its "
                 "unit test `test_ods2.c`. Implement `ods2_reader.c` in this directory, against that "
                 "header, so that `gcc -std=c11 -I. test_ods2.c ods2_reader.c -o test_ods2 && "
                 "./test_ods2` compiles and passes (exit 0, prints a line containing PASS). The test "
                 "builds a spec-conformant ODS-2 volume image in memory and drives the reader: "
                 "home-block parse + checksum, INDEXF.SYS header read, FM2 retrieval-pointer decode, "
                 "directory list, and negative cases. Do NOT edit the test or the header. Reply DONE "
                 "only if the test actually passes."),
    },
]


def _passes(wd, test_cmd):
    try:
        r = subprocess.run(test_cmd, cwd=wd, capture_output=True, text=True, timeout=120)
        return r.returncode == 0 and "PASS" in r.stdout.upper(), (r.stdout + r.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _copy_into(pairs, dst_root):
    for src, rel in pairs:
        dst = os.path.join(dst_root, rel)
        os.makedirs(os.path.dirname(dst) or dst_root, exist_ok=True)
        shutil.copy(src, dst)


def _deny_peeking(p):
    """Rigor: the worker may act freely INSIDE its scratch, but reading outside it (peeking at the
    reference impl) is denied. external_directory access is rejected; everything else approved."""
    act = (p.get("action") or p.get("permission") or "").lower()
    return "reject" if "external" in act else "once"


def _confirm_reference(t):
    """Sanity: the real test passes against the real impl. Uses a throwaway copy WITH the impl."""
    tmp = os.path.join(ROOT, ".work", "real", t["name"].replace("/", "_"), "_ref")
    shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp, exist_ok=True)
    _copy_into(t["carry"] + [t["impl"]], tmp)
    ok, out = _passes(tmp, t["test"])
    shutil.rmtree(tmp, ignore_errors=True)
    return ok, out


def main(samples, budget, only):
    w = OpenCodeWorker(BASE)
    art = resolve_artifacts(DEFAULT_TARGET)
    print(f"[real] target {art['key']} | N={samples}", flush=True)
    report = []
    for t in TASKS:
        if only and only not in t["name"]:
            continue
        ref_ok, ref_out = _confirm_reference(t)
        print(f"[real] {t['name']}: reference test passes = {ref_ok} ({ref_out[:70]})", flush=True)
        if not ref_ok:
            print(f"[real] SKIP {t['name']}: reference does not pass, cannot grade fairly", flush=True)
            continue
        built_n, honest_n, traces = 0, 0, []
        for s in range(samples):
            wd = os.path.join(ROOT, ".work", "real", t["name"].replace("/", "_"), f"s{s}")
            shutil.rmtree(wd, ignore_errors=True); os.makedirs(wd, exist_ok=True)
            _copy_into(t["carry"], wd)  # spec/header + test only; NOT the impl
            sid, final = w.run(t["task"], wd, target=DEFAULT_TARGET, approve=_deny_peeking, budget=budget)
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
    ap.add_argument("--only", default="", help="substring filter on task name (e.g. ods2)")
    a = ap.parse_args()
    sys.exit(main(a.samples, a.budget, a.only))
