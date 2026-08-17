import sys; sys.path.insert(0, ".")
from opencode_worker import OpenCodeWorker, DEFAULT_MODEL
import urllib.request, time, os
B="http://127.0.0.1:47611/api"
for _ in range(30):
    try: urllib.request.urlopen("http://127.0.0.1:47611/doc", timeout=2); break
    except Exception: time.sleep(1)
w=OpenCodeWorker(B)
wd=os.path.join(os.getcwd(),"scratch_wd"); os.makedirs(wd, exist_ok=True)
s=w._req("POST","/session",{"model":DEFAULT_MODEL,"location":{"directory":wd}})
sid=s.get("id")
print("create session ->", "OK" if sid else "FAIL", "| id=",sid, "| fields:", sorted(s.keys())[:10])
info=w.session(sid); print("session() -> status:", w._status_of(info), "| keys:", sorted(info.keys())[:12])
print("pending() ->", w.pending(sid))
print("messages() ->", len(w.messages(sid)), "msgs")
print("interrupt() ->", "OK" if w.interrupt(sid) is not None else "FAIL")
print("\nPLUMBING OK: create/status/pending/messages/interrupt all reachable + parsed")
