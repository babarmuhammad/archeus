"""The old name must not survive anywhere it could be load-bearing.

A rename done by substitution is only finished when nothing is left, and the
dangerous leftovers are the quiet ones: a path literal, a header name, an env
var, a settings key. Grepping is the only check that sees all four at once.

The two kinds of legitimate mention are NOT listed here. They are imported from
`tools/_rename_brand.py`, which is the thing that has to honour them:

  SKIP   whole files that keep the old name — the changelog, the migration
         module, the tools and tests that exist to know both names
  HOLD   exact strings preserved wherever they appear — the documentation
         domain, which is not bought yet, and the README's "Formerly" line

Those lists used to be duplicated here, and the duplication cost exactly what
duplication costs: the script's copy was the shorter one, so a second run
rewrote `migrate.py` to `OLD = 'archeus'` — and rewrote this file's copy of the
allowlist in the same pass, so the suite went on passing over a migration that
had become a no-op. One definition, imported.
"""
import io
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from _rename_brand import HOLD, SKIP        # noqa: E402  (needs the path above)


def _tracked():
    out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True,
                         text=True, encoding='utf-8', check=True).stdout
    return [r for r in out.splitlines() if r and r not in SKIP]


def test_nothing_still_carries_the_old_name():
    held = re.compile('|'.join(re.escape(h) for h in HOLD), re.I)
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


def test_the_domain_is_the_only_thing_still_waiting_on_a_move():
    """`claudectl.space` is held because the new domain is not registered yet,
    and it is the last thing standing between here and the name being gone.

    This is a reminder with a filename attached: when the domain moves, drop it
    from HOLD and re-run the script. Everything else in HOLD is permanent."""
    pending = [h for h in HOLD if h.endswith('.space')]
    assert pending == ['claudectl.space'], \
        'the set of things waiting on an external move changed: %r' % (pending,)
