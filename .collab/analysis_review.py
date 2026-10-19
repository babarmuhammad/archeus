"""Codex review of an analysis card (a .collab note, no commits): py .collab/analysis_review.py T-071 .collab/T-071-storage-namespace-options.md

Writes reviews/T-NNN-analysis.md, then .r2, .r3 ... for each re-review."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import review as rv

cid, note = sys.argv[1], sys.argv[2]
card = {c: block for c, block, _ in rv.cards()}[cid]
prompt = f"""You are the architecture reviewer for archeus v1. Read-only: do not edit files, run tests, \
commit, fetch web pages, or call Windows isolation/profile/ACL APIs.

Read .collab/README.md (protocol and hard rules) and the root AGENTS.md first.

Review analysis card {cid}. It has no commits; its deliverable is the note {note}. The card:

{card}

Read the note in full and every document named under refs (including the earlier .collab notes and \
reviews it builds on). Judge the note against the card's accept and verify lines, in this order: \
scope kept (at most two families, no vendor/price/installed-state inventory, no R7 relaxation, no \
T-004 unblock, mechanism left unchosen); claims stronger than their tag (PINNED needs a quotation \
and a source; INFERRED must not be stated as fact; UNKNOWN must not be resolved by assumption); \
contradictions with the canonical PV-20 design, ADR-0053, T-052's accepted facts or T-004's \
blocking reason; whether the owner options are bounded, distinct and each name the evidence and \
file scopes that would have to precede it. You cannot fetch the cited pages: judge the quotations \
for internal consistency and say what you could not check. Skip style nits.

Reply in exactly this format, nothing before it:
VERDICT: APPROVE | CHANGES | ESCALATE
1. path:line - problem - required change
(one numbered line per finding; "none" if APPROVE with no findings)
Not checked: <what you could not verify, or "nothing">

ESCALATE means only the owner can decide."""
out = os.path.join(rv.REVIEWS, f'{cid}-analysis.md')
n = 1
while os.path.exists(out):
    n += 1
    out = os.path.join(rv.REVIEWS, f'{cid}-analysis.r{n}.md')
tmp = out + '.tmp'
r = subprocess.run([rv.codex(), 'exec', '-C', rv.REPO, '-s', 'read-only', '-o', tmp, '-'],
                   input=prompt, capture_output=True, text=True, encoding='utf-8', errors='replace')
body = open(tmp, encoding='utf-8').read().strip() if os.path.exists(tmp) else ''
if r.returncode or not body.startswith('VERDICT:'):
    if os.path.exists(tmp):
        os.remove(tmp)
    print(f'{cid}: review failed (exit {r.returncode})')
    print('\n'.join(r.stderr.strip().splitlines()[-6:]))
    sys.exit(1)
os.replace(tmp, out)
print(body)
print('->', os.path.relpath(out, rv.REPO))
