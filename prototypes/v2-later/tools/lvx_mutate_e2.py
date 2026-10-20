"""LV2-X.2: watch every new gate clause fail on a planted defect, then pass again. Prototype tooling.
  py prototypes/v2-later/tools/lvx_mutate_e2.py
Each mutant edits e2.js or e2.css, runs only the screens it should break, and must make the gate fail;
the originals are restored after each one. Writes results/lvx/mutate_e2.txt.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LVX = os.path.join(os.path.dirname(HERE), 'lvx')
MUTANTS = [
    ('a stop described as refusing new work', 'e2.js', "Nothing runs until you resume.`;", "Nothing runs until you resume. New work is refused.`;", 'shots', 'stopped'),
    ('a PIN claimed on the desktop', 'e2.js', "'Resuming from this computer needs no PIN.'", "'Resuming needs your PIN.'", 'shots', 'control'),
    ('a card squeezed to a strip', 'e2.css', 'html[data-d="e2"] .x-zone { background:', 'html[data-d="e2"] .x-zone { max-width: 120px; background:', 'shots', 'home'),
    ('a decorative loop at rest', 'e2.css', 'html[data-d="e2"] .x-livedot { width: 7px;', 'html[data-d="e2"] .x-livedot { animation: x-pulse 1.2s infinite; width: 7px;', 'shots', 'home'),
    ('a row wider than the phone', 'e2.css', 'html[data-d="e2"][data-dev="phone"] .x-mi3 { flex-wrap: wrap; gap: 2px 10px; }', 'html[data-d="e2"][data-dev="phone"] .x-mi3 { flex-wrap: nowrap; white-space: nowrap; min-width: 480px; }', 'shots', 'missions_x2'),
    ('the light animates a layout property', 'e2.js', "fill.animate([{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }], { duration: 600,", "fill.animate([{ width: '0px' }, { width: '100px' }], { duration: 600,", 'motion', None),
    ('the light runs while stopped', 'e2.js', "if (!reduce && Q.get('did') === 'approve' && !stopped) {", "if (!reduce && Q.get('did') === 'approve') {", 'motion', None),
    ('the light ignores reduced motion', 'e2.js', "if (!reduce && Q.get('did') === 'approve' && !stopped) {", "if (Q.get('did') === 'approve' && !stopped) {", 'motion', None),
]


def run(tool, only):
    env = dict(os.environ, LVX_ONLY=only or '')
    args = [sys.executable, os.path.join(HERE, 'lvx_shots.py' if tool == 'shots' else 'lvx_motion.py')] + (['e2'] if tool == 'shots' else [])
    out = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', env=env).stdout
    return out.strip().splitlines()[-1], out


def main():
    lines = []
    for name, f, a, b, tool, only in MUTANTS:
        p = os.path.join(LVX, f)
        orig = open(p, encoding='utf-8').read()
        assert orig.count(a) == 1, (name, a)
        try:
            open(p, 'w', encoding='utf-8').write(orig.replace(a, b))
            last, out = run(tool, only)
        finally:
            open(p, 'w', encoding='utf-8').write(orig)
        killed = 'FAILURES: none' not in last
        why = [l for l in out.splitlines() if 'FAIL' in l or ('ok' not in l.split()[-1:] and 'facts' in l)]
        lines.append('%-40s %s  %s' % (name, 'killed' if killed else 'SURVIVED', (why[0].strip() if why else last)[:150]))
    for tool in ('shots', 'motion'):
        last, _ = run(tool, 'stopped,control,home,missions_x2' if tool == 'shots' else None)
        lines.append('restored (%s): %s' % (tool, last))
    open(os.path.join(os.path.dirname(HERE), 'results', 'lvx', 'mutate_e2.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
