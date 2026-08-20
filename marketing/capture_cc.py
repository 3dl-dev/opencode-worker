import pexpect, sys, time
PROMPT=("Delegate this to the local qwen worker using the opencode-worker MCP run tool "
        "(dir /home/baron/projects/opencode-worker/.work/demo), then verify by reading the files "
        "and running the tests yourself. Task: build lru_cache.py with an LRUCache(capacity) class, "
        "O(1) get/put via a dict plus a doubly linked list with LRU eviction, and test_lru.py with "
        "asserts for eviction order, recency on get, and overwrite. Run python3 test_lru.py.")
child = pexpect.spawn("claude --permission-mode bypassPermissions",
                      encoding="utf-8", dimensions=(46,86), timeout=260)
child.logfile_read = sys.stdout
time.sleep(6)
child.send(PROMPT); time.sleep(0.6); child.send("\r")
try: child.expect([r"verified independently", r"all tests passed", r"tests passed"], timeout=230)
except Exception: pass
time.sleep(4)
child.sendcontrol('c'); time.sleep(0.5); child.sendcontrol('c'); time.sleep(0.6)
