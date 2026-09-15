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
    ("hook and statusLine paths are never re-pointed",
     "    _rfixed, _rfailed = repair_commands(cfgdirs)",
     "    _rfixed, _rfailed = [], []"),
    ("a command the user wrote by hand is rewritten too",
     "        if os.path.isfile(raw):\n            continue",
     "        if False:\n            continue"),
    ("the interpreter is left pointing into the old environment",
     "    return f'\"{sys.executable}\" {tail}' if tail != out.strip() else out",
     "    return out"),
    # ── the second pass ──────────────────────────────────────
    ("the repair is one-shot again, so it only ever runs when nothing is broken",
     "def repair_commands(cfgdirs=None, moved=None, failed=None):",
     "def repair_commands(cfgdirs=None, moved=None, failed=None):\n"
     "    if not pending():\n        return [], []"),
    ("the statusline is repaired with the console interpreter",
     "                from . import statusline\n"
     "                sl['command'] = statusline._command()",
     "                sl['command'] = _repoint(cur, pkg_dir)"),
    ("a superseded block is renamed instead of dropped, so there are two",
     "        if (text.count(start) == text.count(end) > 0\n"
     "                and (_NEW_TAG + name + ':START -->') in text):",
     "        if False:"),
    ("every old block is dropped, including the one with no successor",
     "                and (_NEW_TAG + name + ':START -->') in text):",
     "                and True):"),
    ("a half-written pair is renamed, which poisons every later write",
     "        if new.count(start) == new.count(end) > 0:",
     "        if True:"),
    ("the KEEP fence is left invisible to the thing that protects it",
     "_SENTINEL_BLOCKS = _UNIQUE_BLOCKS + ('KEEP',)",
     "_SENTINEL_BLOCKS = _UNIQUE_BLOCKS"),
    # the anchor carries the line after it because `repair_commands` resolves
    # its default the same way and comes FIRST in the file — mutating that one
    # instead is a mutant no test can see, which is what the first run reported
    ("the sweep reads the settings file it has already moved away from",
     "        cfgdirs = [d for _name, d in _c.all_config_dirs()]\n"
     "    for cfgdir in cfgdirs:",
     "        cfgdirs = _old_config_dirs()\n"
     "    for cfgdir in cfgdirs:"),
    ("the sweep gate is the one that is already closed everywhere",
     "    if not sweep_pending():",
     "    if not pending():"),
    ("the sweep flag is written even after a failure",
     "    if failed:\n        return\n    s = _c.load_settings()\n"
     "    s[SWEEP_FLAG] = True",
     "    s = _c.load_settings()\n    s[SWEEP_FLAG] = True"),
    ("a machine that never had the old name is walked anyway",
     "    if _c.load_settings().get('migrated_from') != OLD:",
     "    if False:"),
    ("the old scheduler entry is left in place, still firing",
     "            proc.run(['schtasks', '/delete', '/tn', tn, '/f'], timeout=30)",
     "            pass"),
    ("the loop is unscheduled and never registered again",
     "        ok, msg = loops.schedule(r['id'], r.get('interval') or '', cfgdir)",
     "        ok, msg = True, 'skipped'"),
    ("the old cron line survives every rewrite",
     "        keep = [ln for ln in lines if OLD_TASK_PREFIX not in ln]",
     "        keep = list(lines)"),
    ("the stale env vars are enumerated rather than shape-matched",
     "    names = sorted(k for k in os.environ if k.startswith(OLD.upper() + '_'))",
     "    names = [k for k in ('%s_BAT' % OLD.upper(),) if k in os.environ]"),
    ("the old plugin install is never reported",
     "    if not stale:\n        return ''",
     "    return ''\n    if not stale:\n        return ''"),
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
