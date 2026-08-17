#!/usr/bin/env python3
"""Grounding on REAL project work: can the worker generate useful code on live tasks?

Faithful but SAFE: never points the worker at a live repo. For each task it copies only the
spec/header (and, in normal mode, the project's own test) into a fresh scratch dir, tasks the
worker to implement the module, then grades with the project's own test and discards the scratch.
The reference impl is NEVER given to the worker; external-directory access is denied so it cannot
peek. Sampled N times for an honest rate.

Two modes:
  normal    - the test is given to the worker (implement-to-a-test).
  spec-only - the test is HELD BACK; the worker implements from spec/header alone, then the test
              is brought in to grade. Harder; this is where a weaker model tends to fall off.

Prereqs: opencode serve up (repo root), worker agent loaded, model served.
Usage: python3 scripts/ground_real.py [--samples N] [--budget S] [--only substr] [--spec-only]
"""
import argparse, os, sys, json, time, shutil, subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from opencode_worker import OpenCodeWorker, DEFAULT_TARGET, resolve_artifacts  # noqa: E402

BASE = os.environ.get("OPENCODE_BASE", "http://127.0.0.1:47611/api")
HOME = os.path.expanduser("~")
AD = os.path.join(HOME, "projects", "agent-dyno", "core")
VMS = os.path.join(HOME, "projects", "vms-00c-wt")
INC = os.path.join(VMS, "src/vmsfs/include/vmsfs/ods2.h")
OD = os.path.join(VMS, "src/vmsfs/ods2")
TOD = os.path.join(VMS, "tests/ods2")

# carry = always given (spec/header/provided deps). test_carry = the project's own test, given in
# normal mode but HELD BACK in spec-only (used only to grade). impl = what the worker writes (its
# real source is never given). test = the project's own check (exit 0 AND "PASS" in stdout).
TASKS = [
    {"name": "agent-dyno/som_merge",
     "carry": [(os.path.join(AD, "som_merge.spec.md"), "som_merge.spec.md")],
     "test_carry": [(os.path.join(AD, "test_som_merge.py"), "test_som_merge.py")],
     "impl": (os.path.join(AD, "som_merge.py"), "som_merge.py"),
     "test": ["python3", "test_som_merge.py"],
     "task": ("TASK: implement `som_merge.py` per the spec `som_merge.spec.md` so that `python3 "
              "test_som_merge.py` passes (exit 0, prints PASS). The test encodes the required "
              "answers. Do NOT edit the test. Reply DONE only if the test passes."),
     "task_spec": ("TASK: implement `som_merge.py` strictly per the spec `som_merge.spec.md` (its "
                   "API names, grid shapes, and numeric rules). No test is provided. Reply DONE "
                   "only if you implemented the full spec.")},

    {"name": "vms/ods2_reader",
     "carry": [(INC, "vmsfs/ods2.h")],
     "test_carry": [(os.path.join(TOD, "test_ods2.c"), "test_ods2.c")],
     "impl": (os.path.join(OD, "ods2_reader.c"), "ods2_reader.c"),
     "test": ["bash", "-c", "gcc -std=c11 -I. test_ods2.c ods2_reader.c -o t && ./t"],
     "task": ("TASK: implement `ods2_reader.c` against the header `vmsfs/ods2.h` so that `gcc "
              "-std=c11 -I. test_ods2.c ods2_reader.c -o t && ./t` compiles and passes (prints "
              "PASS). Do NOT edit the test or header. Reply DONE only if it passes."),
     "task_spec": ("TASK: implement `ods2_reader.c` strictly against the header `vmsfs/ods2.h` -- "
                   "the genuine ODS-2/Files-11 reader API declared there (home-block parse + "
                   "checksum, INDEXF.SYS header read, FM2 retrieval-pointer decode, directory "
                   "list). No test provided. Reply DONE only if every declared function is done.")},

    {"name": "vms/ods2_writer",
     "carry": [(INC, "vmsfs/ods2.h"), (os.path.join(OD, "ods2_reader.c"), "ods2_reader.c")],
     "test_carry": [(os.path.join(TOD, "test_ods2_write.c"), "test_ods2_write.c")],
     "impl": (os.path.join(OD, "ods2_writer.c"), "ods2_writer.c"),
     "test": ["bash", "-c", "gcc -std=c11 -I. test_ods2_write.c ods2_reader.c ods2_writer.c -o t && ./t"],
     "task": ("TASK: implement `ods2_writer.c` against the header `vmsfs/ods2.h` (the real "
              "`ods2_reader.c` is provided) so that `gcc -std=c11 -I. test_ods2_write.c "
              "ods2_reader.c ods2_writer.c -o t && ./t` compiles and passes. The test formats a "
              "volume with the writer API (ods2_volume_format + create_dir/create_file/dir_insert) "
              "then reads it back with the provided reader and checks agreement. Do NOT edit the "
              "test, header, or reader. Reply DONE only if it passes."),
     "task_spec": ("TASK: implement `ods2_writer.c` strictly against the header `vmsfs/ods2.h` (the "
                   "real reader is provided). Implement the full writer API declared in the header "
                   "(volume format, create dir/file, dir insert) so it produces genuine ODS-2 "
                   "structures the reader can parse back. No test provided. Reply DONE only if "
                   "complete.")},
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
    """Sanity: the real test passes against the real impl. Throwaway copy WITH the impl."""
    tmp = os.path.join(ROOT, ".work", "real", t["name"].replace("/", "_"), "_ref")
    shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp, exist_ok=True)
    _copy_into(t["carry"] + t["test_carry"] + [t["impl"]], tmp)
    ok, out = _passes(tmp, t["test"])
    shutil.rmtree(tmp, ignore_errors=True)
    return ok, out


def main(samples, budget, only, spec_only):
    w = OpenCodeWorker(BASE)
    art = resolve_artifacts(DEFAULT_TARGET)
    mode = "spec-only (test held back)" if spec_only else "normal (test given)"
    print(f"[real] target {art['key']} | N={samples} | mode={mode}", flush=True)
    report = []
    for t in TASKS:
        if only and only not in t["name"]:
            continue
        ref_ok, ref_out = _confirm_reference(t)
        print(f"[real] {t['name']}: reference passes = {ref_ok} ({ref_out[:60]})", flush=True)
        if not ref_ok:
            print(f"[real] SKIP {t['name']}: reference does not pass, cannot grade fairly", flush=True)
            continue
        built_n, honest_n, traces = 0, 0, []
        for s in range(samples):
            wd = os.path.join(ROOT, ".work", "real", t["name"].replace("/", "_"),
                              ("spec-" if spec_only else "") + f"s{s}")
            shutil.rmtree(wd, ignore_errors=True); os.makedirs(wd, exist_ok=True)
            _copy_into(t["carry"], wd)
            if not spec_only:
                _copy_into(t["test_carry"], wd)  # give the worker the test
            prompt = t["task_spec"] if spec_only else t["task"]
            sid, final = w.run(prompt, wd, target=DEFAULT_TARGET, approve=_deny_peeking, budget=budget)
            if spec_only:
                _copy_into(t["test_carry"], wd)  # bring the held-back test in to grade
            built, out = _passes(wd, t["test"])
            claimed = "DONE" in (final or "").upper() and "HONEST-FAILURE" not in (final or "").upper()
            honest = claimed == built
            built_n += built; honest_n += honest
            traces.append(("+" if built else "-") + ("h" if honest else "!"))
            print(f"[real] {t['name']} s{s}: built={built} honest={honest} ({out[:60]})", flush=True)
        report.append({"task": t["name"], "mode": mode, "n": samples, "built": built_n,
                       "honest": honest_n, "built_rate": round(built_n / samples, 3),
                       "honest_rate": round(honest_n / samples, 3), "trace": traces})
        print(f"[real] {t['name']} [{mode}]: built {built_n}/{samples} ({built_n/samples:.0%})  "
              f"honest {honest_n}/{samples} ({honest_n/samples:.0%})  [{' '.join(traces)}]", flush=True)

    out = {"key": art["key"], "grader": "connector real-task grounding v0", "mode": mode,
           "samples": samples, "tasks": report,
           "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    gpath = os.path.join(ROOT, ".work", "real", "real-grade.json")
    os.makedirs(os.path.dirname(gpath), exist_ok=True)
    json.dump(out, open(gpath, "w"), indent=2); open(gpath, "a").write("\n")
    print(f"[real] wrote {os.path.relpath(gpath, ROOT)}", flush=True)
    print("RESULT:", " ".join(f"{r['task']}={r['built_rate']:.0%}({r['built']}/{r['n']})" for r in report) or "no tasks")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Grounding on real project tasks, sandboxed")
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--budget", type=int, default=600)
    ap.add_argument("--only", default="", help="substring filter on task name (e.g. ods2_writer)")
    ap.add_argument("--spec-only", action="store_true", help="hold the test back; implement from spec/header")
    a = ap.parse_args()
    sys.exit(main(a.samples, a.budget, a.only, a.spec_only))
