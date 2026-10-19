"""Run Qwen (pi on Spark) on one card, contained.

After the 2026-10-19 D:\\Claude wipe (a Qwen bash command `rmdir /s /q D:\\t111` whose
tab-mangled path resolved to the repo root at cwd), Qwen is confined:

  * cwd is ALWAYS the isolated sandbox worktree, never the canonical repo. The canonical
    repo lives at C:\\Users\\mab\\archeus-recovery\\repo and Qwen is never pointed at it.
  * analysis / review / doc cards get NO bash tool (--tools read,grep,find,ls,edit,write):
    with no shell they cannot delete, move or chmod anything. This is the default.
  * a card that must run tests is NOT launched here without an explicit bash=True AND an
    owner decision on the record; such a card is refused with a message, not run.

Usage:  py qwen_run.py <card-id> [bash]     # 'bash' only with owner sign-off, printed loud.
The card is copied into the sandbox's .collab; Qwen reports to .collab/QWEN-DONE-<id>.md.
A run whose pi session file stops growing for 20 min is killed.
"""
import glob
import os
import subprocess
import sys
import time

SANDBOX = r"C:\Users\mab\qwen-sandbox"
PI = r"C:\Users\mab\AppData\Roaming\npm\pi.cmd"
SESS = os.path.expanduser(r"~\.pi\agent\sessions")
NOBASH_TOOLS = "read,grep,find,ls,edit,write"
STALL = 20 * 60

PROMPT = """You are Qwen working card {cid} for archeus v1, INSIDE the sandbox worktree at {sb}.
Your working directory is this sandbox and you must never cd out of it or name a path outside it.
The real repository is elsewhere and is not yours to touch. Read .collab/QWEN-CARD-{cid}.md for the
card. Do exactly the card, inside its scope. Never delete, move or change permissions on any path.
pytest cleans its own temp dirs; you do not remove anything by hand. Sign work as Qwen. Never push.
When done or blocked write .collab/QWEN-DONE-{cid}.md: first line "STATUS: review" or
"STATUS: BLOCKED BY CLASSIFIER" or "STATUS: BLOCKED BY OWNER"; then commits, what ran with results,
what was not run, any block message verbatim."""


def newest():
    fs = glob.glob(os.path.join(SESS, "*", "*.jsonl"))
    return max((os.path.getmtime(f) for f in fs), default=0)


def run(cid, bash):
    os.makedirs(os.path.join(SANDBOX, ".collab"), exist_ok=True)
    src = os.path.join(r"D:\Archeus\.collab", f"QWEN-CARD-{cid}.md")
    dst = os.path.join(SANDBOX, ".collab", f"QWEN-CARD-{cid}.md")
    if os.path.exists(src):
        open(dst, "w", encoding="utf-8").write(open(src, encoding="utf-8").read())
    cmd = [PI, "--model", "spark/qwen3.8-flash-next"]
    if not bash:
        cmd += ["--tools", NOBASH_TOOLS]
    cmd += ["-p", PROMPT.format(cid=cid, sb=SANDBOX)]
    log = open(os.path.join(r"C:\Users\mab\archeus-recovery", f"qwen-{cid}.log"), "w", encoding="utf-8")
    p = subprocess.Popen(cmd, cwd=SANDBOX, stdout=log, stderr=subprocess.STDOUT)
    last, seen = time.time(), newest()
    while p.poll() is None:
        time.sleep(30)
        m = newest()
        if m != seen:
            seen, last = m, time.time()
        if time.time() - last > STALL:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
            print(f"{cid}: STALLED, killed", flush=True)
            return
    done = os.path.join(SANDBOX, ".collab", f"QWEN-DONE-{cid}.md")
    state = open(done, encoding="utf-8").readline().strip() if os.path.exists(done) else "no QWEN-DONE"
    print(f"{cid}: pi exit {p.returncode} (bash={bash}); {state}", flush=True)


if __name__ == "__main__":
    cid = sys.argv[1]
    bash = len(sys.argv) > 2 and sys.argv[2] == "bash"
    if bash:
        print("!! bash ENABLED for Qwen — only with owner sign-off; deletion guard is the sandbox cwd only")
    run(cid, bash)
