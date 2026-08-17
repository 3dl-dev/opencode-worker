import sys, time, os; sys.path.insert(0,'.')
from opencode_worker import OpenCodeWorker, DEFAULT_TARGET
B="http://127.0.0.1:47611/api"
wd="/home/baron/.claude/jobs/93601af0/tmp/steer_wd"; os.makedirs(wd, exist_ok=True)
for f in os.listdir(wd):
    try: os.remove(os.path.join(wd,f))
    except Exception: pass
w=OpenCodeWorker(B)
task=("Write a file report.txt containing 5 detailed sentences about APPLES (the fruit). "
      "Take your time and be thorough. Then reply DONE.")
sid=w.start(task, wd, target=DEFAULT_TARGET)
print("started", sid, flush=True)
t0=time.time(); steered=False
while time.time()-t0 < 240:
    for p in w.pending(sid):
        rid=p.get("id") or p.get("requestID") or p.get("callID")
        w.reply(sid, rid, "once"); print(f"[perm approved {p.get('permission') or p.get('tool')}]", flush=True)
    st=w._status_of(w.session(sid))
    if not steered and time.time()-t0 >= 12:
        w.steer(sid, "STOP. Change the topic completely: rewrite report.txt so it is about ORANGES, "
                     "not apples. Every sentence must be about oranges. Then reply DONE.")
        steered=True; print(f"[STEERED at {time.time()-t0:.0f}s, session was '{st}']", flush=True)
    if steered and st in ("idle","completed","done","error") and time.time()-t0>20:
        break
    time.sleep(3)
print(f"elapsed {time.time()-t0:.0f}s", flush=True)
p=os.path.join(wd,"report.txt")
txt=open(p).read().lower() if os.path.exists(p) else ""
print("\n=== report.txt ===\n"+ (txt[:600] if txt else "(missing)"))
print("\n=== STEER GROUND-TRUTH ===")
print("mentions oranges:", "orange" in txt, "| mentions apples:", "apple" in txt,
      "| STEER LANDED:", ("orange" in txt))
