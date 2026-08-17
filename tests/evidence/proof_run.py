import sys, os, time; sys.path.insert(0,'.')
from opencode_worker import OpenCodeWorker, DEFAULT_TARGET
B="http://127.0.0.1:47611/api"
wd="/home/baron/.claude/jobs/93601af0/tmp/proof_wd"
for f in os.listdir(wd):
    try: os.remove(os.path.join(wd,f))
    except Exception: pass
task=("Create a file named notes.txt in your working directory containing exactly three "
      "lines, one word per line: apple, banana, cherry. Then read the file back to confirm, "
      "and reply DONE. Do nothing else.")
w=OpenCodeWorker(B)
t0=time.time()
sid, final = w.run(task, wd, target=DEFAULT_TARGET, poll=3.0, budget=270)
print(f"[proof] elapsed {time.time()-t0:.0f}s")
print("=== final assistant message ==="); print((final or "(none)")[:600])
p=os.path.join(wd,"notes.txt")
lines=[l.strip() for l in open(p).read().splitlines() if l.strip()] if os.path.exists(p) else []
ok = lines[:3]==["apple","banana","cherry"]
print("\n=== GROUND-TRUTH ACCEPTANCE CHECK (independent of model self-report) ===")
print("notes.txt exists:", os.path.exists(p), "| lines:", lines[:5], "| PASS:", ok)
