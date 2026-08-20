import pexpect, sys, time
PROMPT=("Fan out three separate subagent tasks to the local qwen worker via the opencode-worker run "
        "tool, one delegation each, do not build them yourself. Dir .work/demo. "
        "(1) slugify.py: slugify(s) + 2 asserts. (2) chunk.py: chunk(seq,size) + 2 asserts. "
        "(3) retry.py: retry(fn,n) + 2 asserts. Run each, then summarize each in one line.")
child = pexpect.spawn("claude --permission-mode bypassPermissions",
                      encoding="utf-8", dimensions=(46,88), timeout=300)
child.logfile_read = sys.stdout      # forwarded ONLY while pexpect is reading
time.sleep(9)
child.send(PROMPT); time.sleep(1.0); child.send("\r")
# expect(TIMEOUT) reads continuously for the duration -> output reaches the recording
try: child.expect(pexpect.TIMEOUT, timeout=250)
except Exception: pass
child.sendcontrol('c'); time.sleep(0.5); child.sendcontrol('c'); time.sleep(0.6)
