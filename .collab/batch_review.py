"""One Codex call over several cards: py .collab/batch_review.py amend|evidence T-080:3382715,10ea156 T-083:015a351 ..."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import review as rv

FOCUS = {
    'amend': ('This batch is the canonical-amendment batch. For each card, check that the documentation '
              'change is appended only (nothing already recorded reworded or deleted), that it states what was '
              'built exactly, and that it does not contradict the canonical design or another amendment in the batch.'),
    'evidence': ('This batch is correction commits only, after your earlier CHANGES verdicts (named on each card\'s '
                 'review: line; read those files under .collab/reviews/). Judge only whether each earlier finding is '
                 'addressed or explicitly kept open as the card says, and whether the evidence the test now demands '
                 'is enough for the decision it gates. Do not re-review earlier commits.'),
}
mode = sys.argv[1]
specs = [(a.split(':')[0], a.split(':')[1].split(',')) for a in sys.argv[2:]]
board = {cid: block for cid, block, _ in rv.cards()}
cards = '\n\n'.join(board[cid] for cid, _ in specs)
commits = ' '.join(s for _, shas in specs for s in shas)
ids = ', '.join(cid for cid, _ in specs)
prompt = rv.PROMPT.format(cid=ids + ' (one batch: judge them together)', card=cards, commits=commits)
prompt += '\n\n' + FOCUS[mode] + ' Prefix each finding with its card id.'
tmp = os.path.join(rv.REVIEWS, 'batch.tmp')
r = subprocess.run([rv.codex(), 'exec', '-C', rv.REPO, '-s', 'read-only', '-o', tmp, '-'],
                   input=prompt, capture_output=True, text=True, encoding='utf-8', errors='replace')
body = open(tmp, encoding='utf-8').read().strip() if os.path.exists(tmp) else ''
if os.path.exists(tmp):
    os.remove(tmp)
if r.returncode or not body.startswith('VERDICT:'):
    print(f'batch review failed (exit {r.returncode})')
    print('\n'.join(r.stderr.strip().splitlines()[-6:]))
    sys.exit(1)
note = f'\n\nBatch review by Codex over {ids} in one call (commits {commits}); the same verdict is filed under each card.\n'
for cid, shas in specs:
    with open(rv.out_path(cid, shas[-1]), 'w', encoding='utf-8', newline='\n') as f:
        f.write(body + note)
print(body)
