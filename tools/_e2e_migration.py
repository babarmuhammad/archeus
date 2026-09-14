"""End-to-end migration check against a COPY of this machine's real profile.

The unit tests build a synthetic old layout; this one uses the real thing,
because the shapes that break a migration are the ones nobody thought to
invent — `claudectl-account-creds` was a directory none of the tests knew about
and is only handled because the migration matches a prefix rather than a list.

Nothing here touches anything live. `USERPROFILE` is redirected at a copy —
the same lever `config.py` reads at import — and the project-path resolver is
stubbed out, because the copied transcripts still name the real directories
they were recorded in.

Credentials are deliberately NOT copied: a stand-in directory with the same
name exercises the rename without duplicating secrets into a temp folder.

Run:  py tools/_e2e_migration.py
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL = os.path.join(os.environ.get('USERPROFILE') or os.path.expanduser('~'),
                    '.claude')

#: copied by name, never by content
SECRET = 'claudectl-account-creds'

PROBE = r'''
import json, os, sys
sys.path.insert(0, %r)
from claude_sessions import migrate, config as _c, paths

# The copied transcripts name the REAL working directories they were recorded
# in, so leaving the resolver live would migrate this machine's actual project
# folders — a check that edits what it is checking. Stubbed out: the real-path
# branch is what tests/test_migration.py covers, and what this run is for is
# the config-dir shapes nobody thought to invent.
paths.find_actual_path = lambda *a, **k: None

print('settings_file  =', _c.settings_file)
print('pending        =', migrate.pending())
moved, failed = migrate.run()
print('moved          =', len(moved))
print('failed         =', failed[:3])
print('pending after  =', migrate.pending())
leftovers = sorted(n for n in os.listdir(os.path.dirname(_c.settings_file))
                   if n.startswith('claudectl'))
print('leftovers      =', leftovers)
s = _c.load_settings()
print('migrated_from  =', s.get('migrated_from'))
print('accounts kept  =', len(s.get('accounts') or []))
print('theme kept     =', s.get('theme'))
'''


def main():
    if not os.path.isdir(REAL):
        print('no real profile at %s — nothing to check' % REAL)
        return 0
    tmp = tempfile.mkdtemp(prefix='archeus-e2e-')
    home = os.path.join(tmp, '.claude')
    os.makedirs(home)
    copied = []
    try:
        for name in os.listdir(REAL):
            src = os.path.join(REAL, name)
            dst = os.path.join(home, name)
            if name == SECRET:
                os.makedirs(dst, exist_ok=True)
                with io.open(os.path.join(dst, 'placeholder'), 'w') as f:
                    f.write('not the real thing')
                copied.append(name)
            elif name.startswith('claudectl'):
                (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src, dst)
                copied.append(name)
        # two real project folders, transcripts and all
        pr_src, pr_dst = os.path.join(REAL, 'projects'), os.path.join(home, 'projects')
        os.makedirs(pr_dst, exist_ok=True)
        for enc in sorted(os.listdir(pr_src))[:2]:
            shutil.copytree(os.path.join(pr_src, enc), os.path.join(pr_dst, enc))
            copied.append('projects/' + enc)
        print('copied %d entries into %s\n' % (len(copied), home))

        env = dict(os.environ, USERPROFILE=tmp)
        env.pop('CLAUDE_CONFIG_DIR', None)   # the copy is the default account here
        r = subprocess.run([sys.executable, '-c', PROBE % ROOT],
                           capture_output=True, text=True, env=env, cwd=tmp)
        print(r.stdout or '', end='')
        if r.returncode:
            print(r.stderr[-2000:])
            return 1
        bad = [ln for ln in r.stdout.splitlines()
               if ln.startswith('leftovers') and ln.strip() != 'leftovers      = []']
        bad += [ln for ln in r.stdout.splitlines()
                if ln.startswith('failed') and ln.strip() != 'failed         = []']
        if bad:
            print('\nFAILED:\n  ' + '\n  '.join(bad))
            return 1
        print('\nOK — nothing left under the old name, settings intact')
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
