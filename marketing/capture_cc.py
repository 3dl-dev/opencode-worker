import pexpect, sys, time
# A goal plus the offload policy - no step-by-step tool direction. Claude decides how to
# decompose, when to hand a piece to the worker, and how to verify.
PROMPT=("I need three small utilities in ./.work/demo, each with a runnable test that asserts its "
        "behavior: a slugifier, a list chunker, and a retry wrapper. Per project policy, offload the "
        "builds to the local Qwen worker to keep them off my token budget, then verify each one "
        "yourself before you call it done.")
child = pexpect.spawn("claude --permission-mode bypassPermissions",
                      cwd="/home/baron/projects/opencode-worker",
                      encoding="utf-8", dimensions=(46,88), timeout=420)
child.logfile_read = sys.stdout      # forwarded ONLY while pexpect is reading
time.sleep(10)
child.send(PROMPT); time.sleep(1.0); child.send("\r")
try: child.expect(pexpect.TIMEOUT, timeout=380)
except Exception: pass
child.sendcontrol('c'); time.sleep(0.5); child.sendcontrol('c'); time.sleep(0.6)
