"""Aimed Codex reviews (owner 2026-10-16: "only do aimed reviews with what you need and qwen needs").
One narrow question per call. Usage: py aimed_codex.py JOB [JOB ...]"""
import os
import subprocess
import sys

sys.path.insert(0, r'D:\Archeus\.collab')
import review as rv

HEAD = """You are the architecture reviewer for archeus v1. Read-only: do not edit files, run tests, \
commit, fetch web pages, or call Windows isolation/profile/ACL APIs. Do not open, list or print any real \
file under any account home, ~/.claude or a credential store.

This is an AIMED review: answer only the question below, read only what it names (plus what you must \
open to check a cited line), and do not re-review anything else. Skip style nits.

The card:

{card}

QUESTION:
{q}

Reply in exactly this format, nothing before it:
VERDICT: APPROVE | CHANGES | ESCALATE
1. path:line - problem - required change
(one numbered line per finding; "none" if APPROVE with no findings)
Not checked: <what you could not verify, or "nothing">

ESCALATE means only the owner can decide (canonical-doc conflict, missing authorization)."""

JOBS = {
    'T-100': ('T-100-analysis.md', """Judge only the note .collab/T-100-mechanism-decision.md against this card's accept line. \
Read: that note; .collab/T-071-storage-namespace-options.md with its Correction r2 and r3 sections; \
.collab/reviews/T-071-analysis.r3.md; the T-052 and T-004 cards on .collab/BOARD.md (and the T-052 note it names, if needed); \
.collab/README.md hard rules. Check: (1) exactly one option (or a combination T-071 allows) is chosen, and the note shows why it \
beats each other option on T-004's blocking reason (strict peer exclusion for execution-created descendants); (2) the evidence \
cards it names must precede any code, and none is missing that T-071 or T-052 requires for that option; (3) the code/fake/native \
file scopes match what T-071 names for that option; (4) every owner authorization it needs (ACL code, native runs, any ACL \
application, even on a Core-owned fixture) is named and NOT granted or assumed, and nothing unblocks T-004 or relaxes R7; \
(5) no claim is stronger than its T-071/T-052 source (PINNED vs INFERRED vs UNKNOWN). You cannot fetch cited pages: judge \
quotations for internal consistency only."""),
    'T-097': ('T-097-analysis.md', """Judge only the note .collab/T-097-login-probe-reads.md. Verify every file:line claim in it \
against the SOURCE CODE at commit 853f63f (use `git show 853f63f:<path>`, e.g. archeus/harnesses/calls.py, the usage._creds \
function it calls, archeus/api/routes.py). Answer: which file(s) under an account home the probe opens, which fields it reads, \
whether any value is copied, logged, cached, written or sent anywhere (and where), on which code paths it runs, and whether \
D7 ("Core stores no API key") still stands. Flag any claim the code does not support and any read/write/send path the note \
missed. Code only - never open a real account-home file."""),
    'T-101': ('T-101-ee6dabb.md', """Commits f357434 and ee6dabb only (`git show <sha>`). One question: the authority change. \
_finish (session end recording) now writes the session as the SYSTEM principal when the command's actor is a user, on the \
grounds that only Core records what it observed of a session. Is this consistent with the canonical authority/actor model \
(p20-design-gate.md item 83, D3, D4 and the actor rules they rest on - read them in docs/architecture/ at ee6dabb via \
`git show ee6dabb:docs/architecture/p20-design-gate.md`), and can a user principal now cause, through this path, any record \
or transition it could not cause before (e.g. ending or recording a session it does not own, or an event attributed to the \
system it did not observe)? Say whether the change needs a canonical amendment that is missing."""),
    'T-103': ('T-103-ec90967.md', """Architecture question only (queue item: T-093 slice I, the D7 conclusion and the threat model). \
Read docs/architecture/p20-design-gate.md at ec90967 (`git show ec90967:docs/architecture/p20-design-gate.md`): D7, section 12 \
items 110, 112, 120 and 125, and the plan section 27 correction those items name (find it at ec90967). D7 as amended: Core stores \
no API key of its own, but third-party MCP keys are written in plaintext to run/exec/<id>/res/mcp.json for the life of an \
execution (transient once T-099 lands, which this tree does not contain); the plaintext credentials on disk are the local token \
(run/local-token), the hook token in run/exec/*/req/*.req.json, and those MCP keys. Answer: (1) is the amended D7 consistent \
with the canonical PV-20 design, ADRs and target-architecture it rests on, or does it need an owner decision it does not record? \
(2) does the stated threat model hold - for each plaintext credential, who can read it (same user, other users, an isolated \
execution, a backup), for how long, and is every one of them named, protected as the docs claim, and bounded in lifetime? \
(3) is any credential Core holds missing from the inventory? Do not review tests or code style."""),
    'T-094': ('T-094-d80a9b4.md', """Correction commits 3060485 and d80a9b4 only (`git show <sha>`), answering the blocking finding of \
.collab/reviews/T-094-2f93182.claude.md (read its blocking item): POST /v1/policies/simulate answered 500 on a malformed boundary \
VALUE and POST /v1/policies/rules stored such a rule. Answer only: (1) does PolicyRule._check now refuse every boundary value \
rules.check_boundary cannot read (read check_boundary and the policy engine at 3060485), so neither route can 500 or store one, \
without refusing a boundary a legitimate client sends? (2) the commit makes a bad row stored BEFORE the change raise on every read of \
policy rules, unretireable through the API (item 127 says so and adds no migration because V1 is unshipped) - is that acceptable \
under D12 and the policy design, or must the read path tolerate or the change purge such a row? (3) is clearing the e-stop sentinel \
after each fuzzed request in tools/fuzz_p20.py sound, or does it hide a defect class D12 must find (e.g. a 500 that only appears \
while disarmed)? (4) is item 127 (docs/architecture/p20-design-gate.md) append-only and accurate? Do not re-review earlier commits."""),
    'T-103b': ('T-103-cbc0ee6.md', """Commit cbc0ee6 only (`git show cbc0ee6`): gate item 128 in docs/architecture/p20-design-gate.md, \
written to answer your four findings in .collab/reviews/T-103-ec90967.md (read it). Answer only: is each of the four findings \
answered accurately (check every factual claim item 128 makes against the code at cbc0ee6, e.g. core/runtime.py for the local \
token's reuse, infra/db/backup.py, the idempotency writer), is the diff append-only (no earlier line reworded), and does anything \
in item 128 still claim more than the code supports?"""),
    'T-103c': ('T-103-2b6e852.md', """Commit 2b6e852 only (`git show 2b6e852`), answering the single finding of \
.collab/reviews/T-103-cbc0ee6.md (read it). Answer only: does the appended bullet answer that finding accurately against the code \
at 2b6e852 (infra/db/writer.py _recall, infra/eventlog/retention.py prune and its callers), and is the diff append-only?"""),
    'T-097r': ('T-097-analysis.md', """Re-review after Qwen's correction. Judge ONLY whether each of the three findings in \
.collab/reviews/T-097-analysis.md is now answered accurately in .collab/T-097-login-probe-reads.md, checking each corrected \
file:line claim against the code at 853f63f (`git show 853f63f:<path>`). Do not re-review the rest of the note. Code only - never \
open a real account-home file."""),
    'T-108': ('T-108-ca123e5.md', """Two commits only on the round-5 candidate (detached D:/archeus-pv20-int5). (A) merge 688443f: \
`git show --cc 688443f -- docs/architecture/p20-design-gate.md docs/architecture/target-architecture.md` (also `git diff 688443f^1 \
688443f` and `git diff 688443f^2 688443f` on those two files). Is the union faithful to both sides - nothing from either parent \
dropped or reworded, append-only, the order (slices H/J items 115-128 then T-096.1-T-096.4; T-089 qualification then T-096's \
amendment) leaving no contradiction between items? (B) ca123e5 (`git show ca123e5`, archeus/harnesses/base.py): T-102 had \
re-wrapped a PermissionError and lost its cause; this refuses at the removal with SpawnWriteFailed. Does it keep T-102's charging \
rule (a workspace write failure is charged `workspace`, the task ends FAILED, no unbounded re-dispatch introduced) and D7's \
cleanup of mcp.json? Do not review anything else."""),
    'T-117': ('T-117-474815f.md', """Commit 474815f only: docs/architecture/p21-design-gate.md (`git show 474815f:docs/architecture/p21-design-gate.md`), \
a DRAFT P21 design gate. Judge ONLY its decisions section (D0-D10) and its contradictions list (X1-X6): (1) is any P21 obligation in \
the canonical docs missing from the decisions (grep "P21" across docs/ at 474815f)? (2) does any recommendation conflict with a \
canonical doc, ADR or approved gate decision, or weaken a security property (D0 in particular: starting P21 slices before P20's \
G/K)? (3) is each X1-X6 contradiction real, and which need an owner amendment before P21 can be approved? Do not review prose or \
the "what exists" section."""),
    'T-117b': ('T-117-b9ff906.md', """Commit b9ff906 only (`git show b9ff906`), correcting your ESCALATE in .collab/reviews/T-117-474815f.md (read it). Answer only: (1) is D0 now recorded faithfully as the owner's decision with the plan amendment APPENDED (no line of ARCHEUS_V1_REARCHITECTURE_PLAN.md removed or reworded) and the eligible-slice list matching the owner's option text, with every P20 security gate kept? (2) do the new D11-D14 cover the obligations you named (K5, K7, ADR-0030 causation, p16 trace lanes and replay), and is any recommendation, D13 especially (changes the event payload of every command), unsafe or in conflict with a canonical doc? (3) is the X1-X6 reclassification right? Nothing else."""),
    'T-114': ('T-114-c8f5bd5.md', """Qwen's merge c8f5bd5 (parents 4d37280 and origin/main 3b2ce96). Answer only: (1) is the resolution correct - `git diff 4d37280 c8f5bd5` must be exactly main's changes since the merge base (3b2ce96's side) with 4e91cb0's build_launch_command change reapplied in claude_sessions/launch.py (the branch moved that function there) and claude_sessions/main.py kept from the branch; nothing else changed or lost from either side (check `git diff 3b2ce96 c8f5bd5 -- claude_sessions/codex.py tests/test_codex.py pyproject.toml`)? (2) read .collab/QWEN-DONE-T-114.md: do the test results it reports cover the legacy suite and tests/v1/unit with 0 failures, and is anything claimed that the commit contradicts? (3) does dropping CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC from the launch env weaken any security property archeus relies on (grep what else sets or reads it)?"""),
    'T-097r3': ('T-097-analysis.md', """Re-review after Qwen's r2 correction. Judge ONLY whether the single finding of .collab/reviews/T-097-analysis.r2.md is now fixed in .collab/T-097-login-probe-reads.md (its "Correction r2" section and the in-place edits it names), checking each cited line with `git show 853f63f:<path>` (D:/archeus-p20-i no longer exists; 853f63f is in this repo). Also confirm the line-span corrections that section reports (_token_expired 61-68, _account_email 71-80, account_meta 83-87, _acct_state 169-171) and that no new claim contradicts D7. Nothing else."""),
    'T-122': ('T-122-9473e5e.md', """Commit 9473e5e only (`git show 9473e5e`; report .collab/T-122-ci-report.md). Answer only: (1) archeus/core/execution/canonical.py workspace_path now rejects NUL and over-long paths itself because newer Python realpath no longer raises: is every such path now unclassified (never a normal read/write) on Python 3.10-3.14, and is any other input class (UNC, \\?\ prefix, trailing dots/spaces, ADS ':' names, reserved device names) still classified as a normal path through the same realpath change? (2) archeus/core/execution/manager.py _inside also relies on realpath (left out of scope): is its gap a real policy bypass, and should the fix live in one shared guard both call? Cite lines. (3) archeus/node/staging.py _entry: does the symlink-as-alias change alter what is refused, or only the message? (4) do the test changes (hook chmod 0755, lstat counting at _entry, inode-reuse fix, T105 wait) weaken any assertion rather than fix it? Nothing else."""),
    'T-122r': ('T-122-9473e5e.md', """Re-review: correction commit ca2ca4b only (`git show ca2ca4b`), answering your two findings in .collab/reviews/T-122-9473e5e.md (read it). Answer only: (1) is openable() in archeus/core/execution/canonical.py the single guard run before every realpath in workspace_path and manager._inside, on the effective joined path, with the length counted in UTF-16 units on Windows and component length checked, so no path an OS cannot open is classified as a normal read/write or as inside the workspace? (2) does any other caller of realpath in those two modules still classify without it? (3) do the new tests bite with a tolerant realpath (no assertion weakened)? Nothing else."""),
    'T-110r': ('T-110-analysis.md', """Re-review after Qwen's correction. Judge ONLY whether each of the 8 findings in .collab/reviews/T-110-analysis.md is fixed in .collab/T-110-o7-breaker.md (its in-place edits and the "2b. Correction 2026-10-19" section; Qwen's summary is .collab/QWEN-DONE-T-110c.md), checking each new citation with `git show b73f875:<path>`, and whether the corrections introduced a new wrong citation or claim. Nothing else."""),
    'T-110': ('T-110-analysis.md', """Judge only Qwen's note .collab/T-110-o7-breaker.md against the T-110 card in .collab/QWEN-CARD-T-110.md: verify each file:line it cites against `git show b73f875:<path>`; is O7's record quoted exactly; are the breaker's location, threshold, window, reset and visibility correctly reported as decided or open; is the permanent-spawn-failure loop path right? List every open owner question it should have listed and did not."""),
    'batch': ('',"""Correction commits only, after your earlier CHANGES verdicts (each card's review: line names the file under \
.collab/reviews/; read it). Cards and commits: T-083 4eb7ca5 (earlier review T-083-015a351.md); T-089 02007f1 (earlier \
T-089-3bdc485.md); T-080 - its finding (a multi-task case with a legacy and a short-layout task worktree verifying and merging \
through one mission worktree) is answered by T-092's 2ff46ce (earlier T-080-10ea156.md); T-092 7701f2e, 1da0f7d, 2ff46ce, \
44cbb47 (no earlier Codex review). Judge ONLY: (a) for T-083, T-089, T-080: is each earlier finding addressed, or explicitly \
kept open as the card says; (b) for T-092 one question, digest compatibility: 7701f2e adds the merge-back fields \
(integration_state, merged_revision) to validate.py's _TASK_SKIP, so they leave the plan digest. Does every plan digest stored \
before this change still verify after it (a stored plan whose tasks already carry merged state, an in-flight mission across \
the upgrade), and is this consistent with validate.digest's documented contract and the P19 B4 precedent the card cites? \
Prefix each finding with its card id. Do not re-review earlier commits."""),
}

BATCH = [('T-083', '4eb7ca5'), ('T-089', '02007f1'), ('T-080', '2ff46ce'), ('T-092', '44cbb47')]


def run(job):
    board = {c: b for c, b, _ in rv.cards()}
    name, q = JOBS[job]
    card = '\n\n'.join(board[c] for c, _ in BATCH) if job == 'batch' else board[job[:5]]
    tmp = os.path.join(rv.REVIEWS, f'aimed-{job}.tmp')
    r = subprocess.run([rv.codex(), 'exec', '-C', rv.REPO, '-s', 'read-only', '-o', tmp, '-'],
                       input=HEAD.format(card=card, q=q), capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    body = open(tmp, encoding='utf-8').read().strip() if os.path.exists(tmp) else ''
    if os.path.exists(tmp):
        os.remove(tmp)
    if r.returncode or not body.startswith('VERDICT:'):
        print(f'{job}: FAILED (exit {r.returncode})')
        print('\n'.join(r.stderr.strip().splitlines()[-6:]), flush=True)
        return
    note = '\n\nAimed Codex review (owner 2026-10-16: aimed reviews only); the question asked is in .collab/BOARD.md.\n'
    outs = [rv.out_path(c, s) for c, s in BATCH] if job == 'batch' else [os.path.join(rv.REVIEWS, name)]
    for out in outs:
        n, base = 1, out
        while os.path.exists(out):
            n += 1
            out = base[:-3] + f'.r{n}.md'
        with open(out, 'w', encoding='utf-8', newline='\n') as f:
            f.write(body + note)
        print(f'{job}: {body.splitlines()[0]} -> {out}', flush=True)


for j in sys.argv[1:]:
    run(j)
