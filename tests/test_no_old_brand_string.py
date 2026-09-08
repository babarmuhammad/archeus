"""The old name must not survive anywhere it could be load-bearing.

A rename done by substitution is only finished when nothing is left, and the
dangerous leftovers are the quiet ones: a path literal, a header name, an env
var, a settings key. Grepping is the only check that sees all four at once.

Three kinds of mention are legitimate and are listed explicitly, so adding a
fourth is a decision someone has to make rather than something that drifts in:

  the two HELD strings   the domain and the GitHub repo path still resolve to
                         the old name because neither move has happened yet
  the migration          migrate.py and its tests exist to know the old name
  the history            CHANGELOG.md describes releases that really were
                         called claudectl, and prose that says "formerly"
"""
import io
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: substrings that legitimately still contain the old name anywhere they appear
HELD = ('claudectl.space', 'babarmuhammad/claudectl')

#: files allowed to name it outright
ALLOWED = {
    'CHANGELOG.md',                    # releases that really were named that
    'README.md',                       # the "formerly claudectl" line
    '.gitignore',                      # transitional: keeps old machine-local
                                       # state unstageable until it is migrated
    'claude_sessions/migrate.py',      # the one module that must know both
    'tests/test_migration.py',
    'tests/test_no_old_brand_string.py',
    'tools/_rename_brand.py',
    'tools/_mut_migration.py',
    'tools/_e2e_migration.py',
}


def _tracked():
    out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True,
                         text=True, encoding='utf-8', check=True).stdout
    return [r for r in out.splitlines() if r and r not in ALLOWED]


def test_nothing_still_carries_the_old_name():
    held = re.compile('|'.join(re.escape(h) for h in HELD), re.I)
    bad = []
    for rel in _tracked():
        path = os.path.join(ROOT, rel.replace('/', os.sep))
        try:
            with io.open(path, encoding='utf-8') as f:
                lines = f.read().splitlines()
        except (OSError, UnicodeDecodeError):
            continue          # binary, or not text — .ico and friends
        for n, line in enumerate(lines, 1):
            if 'claudectl' in held.sub('', line).lower():
                bad.append('%s:%d: %s' % (rel, n, line.strip()[:100]))
    assert not bad, 'the old name survives in:\n  ' + '\n  '.join(bad[:25])


def test_the_two_held_strings_are_still_only_the_domain_and_the_repo():
    """They are held back because the domain is not bought and the repo is not
    renamed. When either moves, the one substitution that finishes the job must
    not silently miss a THIRD thing that grew into the exemption meanwhile."""
    from claude_sessions import migrate  # noqa: F401  (import proves it loads)
    src = io.open(os.path.join(ROOT, 'tools', '_rename_brand.py'),
                  encoding='utf-8').read()
    for h in HELD:
        assert repr(h) in src or "'%s'" % h in src, \
            '%s is exempted here but not held by the rename script' % h
    assert src.count("': '\\x00HOLD") == len(HELD), \
        'the rename script holds a different number of strings than this test'
