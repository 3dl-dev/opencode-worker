import sys, time, os; sys.path.insert(0,'.')
from opencode_worker import OpenCodeWorker, DEFAULT_TARGET
B="http://127.0.0.1:47611/api"
wd="/home/baron/.claude/jobs/93601af0/tmp/perm_wd"
for f in ["hello.txt"]:
    try: os.remove(os.path.join(wd,f))
    except Exception: pass
w=OpenCodeWorker(B)
task="Create a file hello.txt containing exactly the single word WORLD. Then reply DONE."
sid=w.start(task, wd, target=DEFAULT_TARGET)
print("started", sid, flush=True)
t0=time.time(); saw_ask=False; decisions=[]
while time.time()-t0 < 200:
    for p in w.pending(sid):
        rid=p.get("id") or p.get("requestID") or p.get("callID")
        label=p.get("permission") or p.get("tool") or p.get("title") or "?"
        saw_ask=True; decisions.append(label)
        w.reply(sid, rid, "once")
        print(f"[GATE surfaced: {label} -> approved once]", flush=True)
    st=w._status_of(w.session(sid))
    if st in ("idle","completed","done","error") and time.time()-t0>8: break
    time.sleep(2)
print(f"elapsed {time.time()-t0:.0f}s", flush=True)
p=os.path.join(wd,"hello.txt")
ok = os.path.exists(p) and open(p).read().strip().upper().startswith("WORLD")
print("\n=== PERMISSION CONTROL GROUND-TRUTH ===")
print("gate(s) surfaced to driver:", decisions or "NONE")
print("hello.txt exists+correct:", ok)
print("PASS (gate surfaced AND we controlled it AND action executed):", bool(saw_ask and ok))
