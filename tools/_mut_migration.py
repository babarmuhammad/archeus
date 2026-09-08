"""Mutation check for tests/test_migration.py.

Breaks one step of migrate.py at a time and asserts the suite goes red. A gate
nobody has watched fail is not a gate; this is the watching.

Run:  py tools/_mut_migration.py
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, 'claude_sessions', 'migrate.py')

#: label -> (find, replace). Each removes exactly one behaviour.
MUTANTS = [
    ('the project workdir is never moved',
     "    _move(os.path.join(base, OLD_WORKDIR), os.path.join(base, NEW_WORKDIR),\n"
     "          moved, failed)",
     "    pass"),
    ('.claude/.claudectl-*.json is left behind',
     "    _rename_prefixed(dot_claude, OLD_WORKDIR, NEW_WORKDIR, moved, failed)",
     "    pass"),
    ('the generated memory rules are left behind',
     "    _rename_prefixed(os.path.join(dot_claude, 'rules'), OLD + '-', NEW + '-',\n"
     "                     moved, failed)",
     "    pass"),
    ('the config dirs are never migrated',
     "        _migrate_config_dir(cfgdir, moved, failed)",
     "        pass"),
    ('only the default account is considered',
     "    for a in accounts:",
     "    for a in []:"),
    ('the real project path is never resolved',
     "            if real and os.path.isdir(real):",
     "            if False:"),
    ('an existing destination is overwritten',
     "    if os.path.isdir(src) and os.path.isdir(dst):\n"
     "        _merge(src, dst, moved, failed)",
     "    os.replace(src, dst)"),
    ('a destination a hook already created is skipped instead of merged',
     "    if os.path.isdir(src) and os.path.isdir(dst):\n"
     "        _merge(src, dst, moved, failed)",
     "    pass"),
    ('the merge does not recurse into subdirectories',
     "        _move(os.path.join(src, name), os.path.join(dst, name), moved, failed)",
     "        pass"),
    ('the done flag is written even after a failure',
     "    if not failed:\n        _mark_done(moved)",
     "    _mark_done(moved)"),
    ('a clean install walks every project anyway',
     "    if not _has_old_artifacts(cfgdirs):",
     "    if False:"),
    # the real incident: a blind rename pass rewrote this module's own OLD.
    # Every move becomes a no-op, nothing is found, the done flag is written,
    # and every existing user's state stays under the old name forever.
    ("the module no longer knows the name it is migrating FROM",
     "OLD = 'claudectl'",
     "OLD = 'archeus'"),
]


def main():
    src = io.open(TARGET, encoding='utf-8', newline='').read()
    bad = []
    try:
        for label, find, repl in MUTANTS:
            if find not in src:
                bad.append('%s: anchor not found (migrate.py moved?)' % label)
                continue
            with io.open(TARGET, 'w', encoding='utf-8', newline='') as f:
                f.write(src.replace(find, repl, 1))
            r = subprocess.run([sys.executable, '-m', 'pytest', '-q',
                                'tests/test_migration.py'],
                               cwd=ROOT, capture_output=True, text=True)
            status = 'caught' if r.returncode != 0 else 'MISSED'
            if r.returncode == 0:
                bad.append(label)
            print('%-8s %s' % (status, label))
    finally:
        with io.open(TARGET, 'w', encoding='utf-8', newline='') as f:
            f.write(src)
    if bad:
        print('\nnot covered by any test:')
        for b in bad:
            print('  ' + b)
        return 1
    print('\nall %d mutants caught' % len(MUTANTS))
    return 0


if __name__ == '__main__':
    sys.exit(main())
