"""Packaging invariants that only a real install can prove.

`pip install archeus` shipped an empty skills_templates/ for its whole life:
package-data globbed `skills_templates/*.md` while every file is one level
deeper at `skills_templates/<name>/SKILL.md`. CI's import smoke check could not
catch it, because it runs from the source tree where the files are simply there.

The wheel build itself is a CI job (it needs `build`); what runs here is the
cheap half — that the declared globs actually match the files on disk, and that
the console-script target does not drag in the heavy import chain.
"""

import ast
import os
import subprocess
import sys
from glob import glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, 'claude_sessions')


def _package_data_globs():
    """The package-data patterns, read out of pyproject without a TOML parser
    dependency (tomllib is 3.11+, this package supports 3.10)."""
    text = open(os.path.join(ROOT, 'pyproject.toml'), encoding='utf-8').read()
    start = text.index('[tool.setuptools.package-data]')
    body = text[start:]
    body = body[body.index('claude_sessions = ['):]
    body = body[:body.index(']') + 1]
    import re
    return re.findall(r'"([^"]+)"', body)


def test_every_declared_glob_matches_at_least_one_file():
    """A glob that matches nothing is invisible: the build succeeds, the wheel is
    just missing the data."""
    empty = [pat for pat in _package_data_globs()
             if not glob(os.path.join(PKG, pat.replace('/', os.sep)))]
    assert not empty, 'package-data patterns matching no files: %s' % empty


def test_the_bundled_skill_templates_are_covered_by_a_glob():
    from claude_sessions import skills
    on_disk = glob(os.path.join(skills.bundled_templates_dir(), '*', 'SKILL.md'))
    assert on_disk, 'no bundled templates on disk — fixture assumption broken'
    covered = set()
    for pat in _package_data_globs():
        covered.update(glob(os.path.join(PKG, pat.replace('/', os.sep))))
    missing = [p for p in on_disk if p not in covered]
    assert not missing, 'templates that would not ship: %s' % missing


def test_the_plugin_bundle_is_tracked_by_git():
    """The plugin is installed from the REPO by `/plugin marketplace add`, not
    from the wheel — so the failure mode is not a missing glob but a file that
    never got committed, which looks identical from inside a working tree."""
    want = [os.path.join('.claude-plugin', 'marketplace.json'),
            os.path.join('plugin', '.claude-plugin', 'plugin.json'),
            os.path.join('plugin', 'skills', 'commit-message', 'SKILL.md'),
            os.path.join('plugin', 'commands', 'recall.md')]
    r = subprocess.run(['git', 'check-ignore'] + want, cwd=ROOT,
                       capture_output=True, text=True, encoding='utf-8',
                       errors='ignore', timeout=60)
    assert r.returncode != 0, 'gitignored plugin files: %s' % r.stdout
    for rel in want:
        assert os.path.isfile(os.path.join(ROOT, rel)), rel


def test_the_console_script_target_exists_and_is_thin():
    """`archeus statusline` runs on every conversation turn. main's import
    chain pulls urllib/ssl/http.client via `usage`; cli.py must dispatch before
    that, exactly as __main__.py does."""
    text = open(os.path.join(ROOT, 'pyproject.toml'), encoding='utf-8').read()
    assert 'archeus = "claude_sessions.cli:run"' in text

    from claude_sessions import cli
    assert callable(cli.run)

    tree = ast.parse(open(os.path.join(PKG, 'cli.py'), encoding='utf-8').read())
    module_level = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert [a.name for n in module_level for a in n.names] == ['sys'], \
        'cli.py must not import anything heavy at module level'


def test_statusline_via_the_console_script_path_stays_light():
    """The regression this guards: pointing the script at main:run loaded 157
    modules including ssl, on every turn."""
    probe = (
        "import sys;"
        "sys.argv=['archeus','statusline'];"
        "import claude_sessions.cli as c;"
        "print('ssl' in sys.modules, 'urllib.request' in sys.modules)"
    )
    r = subprocess.run([sys.executable, '-c', probe], capture_output=True,
                       text=True, encoding='utf-8', errors='ignore', timeout=60,
                       cwd=ROOT)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == 'False False', r.stdout


def test_help_does_not_pay_for_the_tui():
    """`--help` is the first thing a fresh install types. It answers out of
    `cli.py`, which imports the standard library and nothing else — so the whole
    TUI stack (and anything that could be broken in it) is never loaded, and the
    answer cannot fail for a reason that has nothing to do with the question."""
    probe = (
        "import sys;"
        "sys.argv=['archeus','--help'];"
        "import claude_sessions.cli as c;"
        "c.print_help();"
        "print('MAIN' if 'claude_sessions.main' in sys.modules else 'clean',"
        " 'SSL' if 'ssl' in sys.modules else 'nossl', file=sys.stderr)"
    )
    r = subprocess.run([sys.executable, '-c', probe], capture_output=True,
                       text=True, encoding='utf-8', errors='ignore', timeout=60,
                       cwd=ROOT)
    assert r.returncode == 0, r.stderr
    assert 'USAGE' in r.stdout and 'COMMANDS' in r.stdout
    assert r.stderr.split() == ['clean', 'nossl'], r.stderr


def _docs():
    # docs/llms.txt is the crawler-facing index of the site and carried a stale
    # "Not on PyPI yet" for a whole release, because this list was README-only.
    for rel in ('README.md', os.path.join('plugin', 'README.md'),
                os.path.join('docs', 'llms.txt'), os.path.join('docs', 'install.md')):
        p = os.path.join(ROOT, rel)
        if os.path.isfile(p):
            yield rel, open(p, encoding='utf-8').read()


def test_no_document_denies_an_install_that_now_works():
    """This guard used to assert the opposite — that nothing advertised
    `pipx install archeus`, because the name 404'd and the first instruction a
    visitor followed was the one that failed.

    1.6.0 is published, so the hazard inverted: a leftover "not on PyPI yet"
    caveat now turns people away from the install that works. The lesson is that
    the old form encoded a temporary state as a permanent invariant; this form
    tracks the package's actual existence instead of restating it.
    """
    import re
    stale = []
    for rel, text in _docs():
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r'not (on PyPI|published)|both fail with a 404', line, re.I):
                stale.append('%s:%d %s' % (rel, i, line.strip()[:70]))
    assert not stale, 'claims archeus is unavailable on PyPI: %s' % stale


def test_the_working_install_is_the_one_shown_first():
    """Whatever else it says, the quickstart has to be runnable as written."""
    text = open(os.path.join(ROOT, 'README.md'), encoding='utf-8').read()
    quick = text[text.index('## Quickstart'):]
    quick = quick[:quick.index('\n## ')]
    assert 'git clone' in quick
    assert 'claude-sessions.py' in quick, 'the quickstart never runs anything'


def test_every_image_the_readme_shows_actually_exists():
    """A README is the first thing anyone sees, and a broken image is the
    loudest possible way to look unmaintained. The screenshots are generated
    (tools/shot_gui.py --docs, tools/shot_tui.py), so a renamed capture is an
    easy way to lose one."""
    import re
    text = open(os.path.join(ROOT, 'README.md'), encoding='utf-8').read()
    missing = [src for src in re.findall(r'src="([^"]+)"', text)
               if not src.startswith('http')
               and not os.path.isfile(os.path.join(ROOT, src.replace('/', os.sep)))]
    assert not missing, 'README references missing images: %s' % missing


def test_the_readme_shows_both_interfaces():
    """It ships a TUI and a GUI; someone opening the repo should see both
    without reading a word."""
    text = open(os.path.join(ROOT, 'README.md'), encoding='utf-8').read()
    assert 'docs/img/tui-' in text, 'no TUI screenshot'
    assert text.count('docs/img/gui-') >= 4, 'barely any GUI screenshots'
