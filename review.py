"""Headless Codex review of a board card: py .collab/review.py T-012 | --pending"""
import glob
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BOARD = os.path.join(HERE, 'BOARD.md')
REVIEWS = os.path.join(HERE, 'reviews')

PROMPT = """You are the architecture reviewer for archeus v1. Read-only: do not edit files, \
run tests, commit, or call Windows isolation/profile/ACL APIs.

Read .collab/README.md (protocol and hard rules) and the root AGENTS.md first.

Review card {cid}. The card:

{card}

Inspect exactly these commits with `git show --stat <sha>` and `git show <sha>`: {commits}
Read every document named under refs and judge the change against them and against `accept`.

Look for, in this order: violations of the canonical design, ADRs or gate items; scope creep \
beyond the card; correctness bugs; missing or vacuous tests for the acceptance criteria; \
evidence claims stronger than what was run. Skip style nits.

Reply in exactly this format, nothing before it:
VERDICT: APPROVE | CHANGES | ESCALATE
1. path:line - problem - required change
(one numbered line per finding; "none" if APPROVE with no findings)
Not checked: <what you could not verify, or "nothing">

ESCALATE means only the owner can decide (canonical-doc conflict, missing authorization)."""


def cards():
    text = open(BOARD, encoding='utf-8').read()
    for block in re.split(r'^(?=### T-\d+)', text, flags=re.M):
        m = re.match(r'### (T-\d+)', block)
        if not m:
            continue
        fields = {}
        for line in block.splitlines()[1:]:
            for part in line.split(' · '):
                k, sep, v = part.partition(':')
                if sep and re.fullmatch(r'[a-z]+', k.strip()):
                    fields[k.strip()] = v.strip()
        yield m.group(1), block.strip(), fields


def shas(fields):
    return re.findall(r'\b[0-9a-f]{7,40}\b', fields.get('commits', ''))


def out_path(cid, sha):
    return os.path.join(REVIEWS, f'{cid}-{sha[:7]}.md')


def codex():
    found = shutil.which('codex')
    if found:
        return found
    pattern = os.path.join(os.environ['LOCALAPPDATA'], 'OpenAI', 'Codex', 'bin', '*', 'codex.exe')
    hits = sorted(glob.glob(pattern), key=os.path.getmtime)
    if not hits:
        sys.exit('codex executable not found')
    return hits[-1]


def review(cid, card, fields):
    commits = shas(fields)
    if not commits:
        print(f'{cid}: no commits listed, skipped')
        return False
    os.makedirs(REVIEWS, exist_ok=True)
    target = out_path(cid, commits[-1])
    tmp = target + '.tmp'
    prompt = PROMPT.format(cid=cid, card=card, commits=' '.join(commits))
    print(f'{cid}: reviewing {" ".join(commits)} ...', flush=True)
    r = subprocess.run([codex(), 'exec', '-C', REPO, '-s', 'read-only', '-o', tmp, '-'],
                       input=prompt, capture_output=True, text=True, encoding='utf-8', errors='replace')
    body = open(tmp, encoding='utf-8').read().strip() if os.path.exists(tmp) else ''
    if r.returncode or not body.startswith('VERDICT:'):
        if os.path.exists(tmp):
            os.remove(tmp)
        print(f'{cid}: review failed (exit {r.returncode}), card stays in review')
        print('\n'.join(r.stderr.strip().splitlines()[-6:]))
        return False
    os.replace(tmp, target)
    print(f'{cid}: {body.splitlines()[0]}  ->  {os.path.relpath(target, REPO)}')
    return True


def main(argv):
    if argv == ['--pending']:
        todo = [c for c in cards() if c[2].get('status') == 'review'
                and shas(c[2]) and not os.path.exists(out_path(c[0], shas(c[2])[-1]))]
        if not todo:
            print('nothing pending')
        return 0 if all([review(*c) for c in todo]) else 1
    if len(argv) == 1:
        match = [c for c in cards() if c[0] == argv[0]]
        if not match:
            sys.exit(f'{argv[0]} not on the board')
        return 0 if review(*match[0]) else 1
    sys.exit(__doc__)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.exit(main(sys.argv[1:]))
