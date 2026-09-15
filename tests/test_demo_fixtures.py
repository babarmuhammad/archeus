"""The screenshot fixtures must be fiction.

`tools/shot_gui.py` renders the images that ship in the README, and its stub
data had been seeded from a real workspace — real project names, real account
names, real absolute paths. Every one of those went into a published PNG.

Anything the screenshot tools feed the app is therefore treated as publishable
by definition, and has to look like a demo: a made-up project list, made-up
account names, and paths under a demo root.

The home-directory check is deliberately computed rather than hardcoded — the
point is to catch data from WHATEVER machine runs the tools, and writing the
name of a real user into the repo to detect it would be self-defeating.
"""

import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_FILES = ('tools/smoke_gui.py', 'tools/shot_gui.py')

#: the only account names the demo workspace has
DEMO_ACCOUNTS = {'default', 'teamA', 'teamB'}


def _sources():
    for rel in FIXTURE_FILES:
        p = os.path.join(ROOT, rel.replace('/', os.sep))
        yield rel, io.open(p, encoding='utf-8').read()


def test_no_fixture_mentions_the_home_directory_of_this_machine():
    """Generic on purpose: it catches a leak from whoever regenerates the
    screenshots, not just from the machine this was written on.

    It looks for the home name AS A PATH SEGMENT, and skips comments — the same
    two rules its sibling below already applies, and for the same reason. A bare
    word match was matching English prose: on a CI runner `basename('~')` is
    `runner`, so the comment "reads as a slow runner" failed this test on every
    Linux and macOS job while passing on Windows, where the account is
    `runneradmin`.
    """
    home = os.path.basename(os.path.expanduser('~')).strip()
    if not home or len(home) < 3:
        return                       # nothing distinctive enough to search for
    seg = re.compile(r'[\\/]%s\b|\b%s[\\/]' % (re.escape(home), re.escape(home)))
    bad = []
    for rel, src in _sources():
        for i, line in enumerate(src.splitlines(), 1):
            if line.lstrip().startswith('#'):
                continue
            if seg.search(line):
                bad.append('%s:%d %r' % (rel, i, home))
    assert not bad, 'screenshot fixtures name a real home directory: %s' % bad


def test_no_fixture_carries_a_real_looking_absolute_path():
    """A drive letter or a /home/<user> path reads as somebody's actual
    machine, which is exactly what the images then show."""
    bad = []
    for rel, src in _sources():
        for i, line in enumerate(src.splitlines(), 1):
            if line.lstrip().startswith('#'):
                continue
            if re.search(r"['\"][A-Za-z]:\\\\", line) or re.search(r'/home/\w', line):
                bad.append('%s:%d %s' % (rel, i, line.strip()[:60]))
    assert not bad, 'fixture paths look like a real machine: %s' % bad


def test_the_demo_workspace_uses_demo_paths():
    from importlib import util
    spec = util.spec_from_file_location(
        'sg_fx', os.path.join(ROOT, 'tools', 'smoke_gui.py'))
    sg = util.module_from_spec(spec)
    spec.loader.exec_module(sg)
    for p in sg.STATE['projects']:
        assert p['path'].startswith('/demo/'), p
    for r in sg.STATE['recent']:
        assert r['path'].startswith('/demo/'), r


def test_the_demo_workspace_uses_demo_account_names():
    from importlib import util
    spec = util.spec_from_file_location(
        'sg_fx2', os.path.join(ROOT, 'tools', 'smoke_gui.py'))
    sg = util.module_from_spec(spec)
    spec.loader.exec_module(sg)
    names = {a['name'] for a in sg.STATE['accounts']}
    assert names <= DEMO_ACCOUNTS, names
    for p in sg.STATE['projects']:
        assert set(p['accounts']) <= DEMO_ACCOUNTS, p


def test_the_published_screenshots_are_the_generated_ones():
    """docs/img is what the README shows; it must hold only files the two
    screenshot tools produce, so nothing hand-dropped ships by accident.

    `.webp` is allowed alongside `.png` because `tools/optimize_images.py`
    derives one from the other — the manual links the WebP (a quarter of the
    bytes, served raw by MkDocs) while the README keeps the PNG, which is what
    PyPI renders. Allowing the extension does NOT weaken the gate: a WebP with
    no PNG beside it is not a derivative of anything, so it is rejected by the
    second assertion rather than waved through by the first."""
    d = os.path.join(ROOT, 'docs', 'img')
    if not os.path.isdir(d):
        return
    allowed = re.compile(r'^(gui|tui)-[a-z0-9-]+\.(png|webp)$')
    names = os.listdir(d)
    bad = [n for n in names if not allowed.match(n)]
    assert not bad, 'unexpected files in docs/img: %s' % bad
    orphans = [n for n in names
               if n.endswith('.webp') and n[:-5] + '.png' not in names]
    assert not orphans, 'webp with no generated png beside it: %s' % orphans
