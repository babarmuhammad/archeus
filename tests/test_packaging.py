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


def _declared_packages():
    import re
    text = open(os.path.join(ROOT, 'pyproject.toml'), encoding='utf-8').read()
    body = text[text.index('[tool.setuptools]'):]
    body = body[body.index('packages = ['):]
    return re.findall(r'"([^"]+)"', body[:body.index(']') + 1])


def test_the_declared_packages_are_exactly_the_packages_on_disk():
    """`packages` does not recurse, so an `archeus` subpackage missing from the
    list imports fine from the source tree and is simply absent from the wheel
    — the skills_templates failure again, one level up. The other direction
    catches a listed package that was renamed or deleted."""
    on_disk = set()
    for top in ('claude_sessions', 'archeus'):
        for d, subdirs, files in os.walk(os.path.join(ROOT, top)):
            subdirs[:] = [s for s in subdirs if s != '__pycache__']
            if '__init__.py' in files:
                on_disk.add(os.path.relpath(d, ROOT).replace(os.sep, '.'))
    assert set(_declared_packages()) == on_disk


def test_the_v1_package_imports_in_a_clean_interpreter():
    """Nothing about `archeus` may depend on having been imported after the
    legacy UI, or on the cwd: a fresh interpreter run from elsewhere imports
    every declared V1 module, and none of them loads the legacy UI stack."""
    mods = ['archeus.core.domain.' + m for m in
            ('ids', 'states', 'values', 'actions', 'entities', 'events', 'guards')]
    mods += ['archeus.core.application.lifecycle']
    mods += ['archeus.core.ports', 'archeus.infra.paths', 'archeus.harnesses.base',
             'archeus.harnesses.fake', 'archeus.harnesses.registry',
             'archeus.infra.db', 'archeus.infra.db.backup', 'archeus.infra.eventlog.outbox',
             'archeus.infra.eventlog.consumers', 'archeus.infra.eventlog.retention',
             'archeus.infra.artifacts.store', 'archeus.core.application.commands',
             'archeus.core.application.queries', 'archeus.core.application.work',
             'archeus.core.engine']
    probe = ('import sys; sys.path.insert(0, %r)\n' % ROOT
             + ''.join('import %s\n' % m for m in mods)
             + "bad = [m for m in ('claude_sessions.ui', 'claude_sessions.gui_api', "
               "'claude_sessions.main', 'claude_sessions.gui') if m in sys.modules]\n"
               "print(bad)")
    r = subprocess.run([sys.executable, '-c', probe], capture_output=True, text=True,
                       encoding='utf-8', errors='ignore', timeout=60,
                       cwd=os.path.dirname(ROOT))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == '[]', r.stdout


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


def test_every_v1_migration_is_covered_by_package_data():
    """The schema is .sql files in a directory that is not a package, so they
    ship only if package-data names them — and a wheel without them opens a
    database with no tables. Every migration on disk must match the glob."""
    import re
    text = open(os.path.join(ROOT, 'pyproject.toml'), encoding='utf-8').read()
    body = text[text.index('[tool.setuptools.package-data]'):]
    line = re.search(r'^"archeus\.infra\.db" = \[(.*)\]$', body, re.M)
    assert line, 'archeus.infra.db declares no package-data'
    base = os.path.join(ROOT, 'archeus', 'infra', 'db')
    covered = set()
    for pat in re.findall(r'"([^"]+)"', line.group(1)):
        covered.update(glob(os.path.join(base, pat.replace('/', os.sep))))
    on_disk = set(glob(os.path.join(base, 'migrations', '*.sql')))
    assert on_disk, 'no migrations on disk'
    assert on_disk <= covered, 'migrations that would not ship: %s' % sorted(on_disk - covered)


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


def _version(path):
    import re
    text = open(path, encoding='utf-8').read()
    return re.search(r'(?m)^version = "([^"]+)"', text).group(1)


def _tuple(v):
    return tuple(int(p) for p in v.split('.')[:3])


def test_the_final_release_under_the_old_name_ships_no_code():
    """Both distributions used to ship `claude_sessions`, so installing one over
    the other overwrote those files and uninstalling either deleted them. The
    last release under the old name owns nothing, which is what makes it safe to
    hold alongside this one."""
    shim = os.path.join(ROOT, 'packaging', 'legacy-name', 'pyproject.toml')
    text = open(shim, encoding='utf-8').read()
    assert 'packages = []' in text
    assert '[tool.setuptools.package-data]' not in text
    assert 'claude_sessions.cli:run' in text, 'the old command stops working'


#: manifest -> how its version is spelled. Everything under packaging/ except
#: the final release under the old name, which has a life of its own.
_MANIFESTS = {
    os.path.join('packaging', 'npm', 'package.json'): r'"version":\s*"([^"]+)"',
    os.path.join('packaging', 'crates', 'Cargo.toml'): r'(?m)^version = "([^"]+)"',
    os.path.join('packaging', 'rubygems', 'archeus.gemspec'): r"s\.version\s*=\s*'([^']+)'",
    os.path.join('packaging', 'nuget', 'archeus.nuspec'): r'<version>([^<]+)</version>',
    os.path.join('packaging', 'docker', 'Dockerfile'): r'ARG ARCHEUS_VERSION=(\S+)',
}


def test_every_packaging_manifest_declares_the_same_version():
    """A release is one number in six files.

    A user who sees `archeus 2.1.0` on npm beside `2.4.0` on PyPI has no way to
    know which is the tool and which is a name. Nothing builds these in CI, so
    nothing else would ever notice the drift.

    npm is the one allowed to be AHEAD, by a patch on the same minor, and only
    because it is the one manifest that ships code of its own: the launcher is
    real JavaScript, and a bug in it (2.4.0 ran npm's own shim under `npx` and
    exited 1 printing nothing) has to be republished under a new number, which
    npm will not let you reuse. Nothing else here is code — Docker installs the
    real thing, the rest are pointers — so nothing else has that excuse.
    """
    import re
    here = _version(os.path.join(ROOT, 'pyproject.toml'))
    npm = os.path.join('packaging', 'npm', 'package.json')
    wrong = []
    for rel, pat in _MANIFESTS.items():
        path = os.path.join(ROOT, rel)
        assert os.path.isfile(path), 'missing packaging manifest: %s' % rel
        m = re.search(pat, open(path, encoding='utf-8').read())
        assert m, 'no version found in %s' % rel
        got = m.group(1)
        if got == here:
            continue
        ahead = (rel == npm
                 and got.split('.')[:2] == here.split('.')[:2]
                 and int(got.split('.')[2]) > int(here.split('.')[2]))
        if not ahead:
            wrong.append('%s says %s' % (rel, got))
    assert not wrong, 'pyproject is %s but %s' % (here, '; '.join(wrong))


def test_the_npm_launcher_never_installs_without_saying_so():
    """`npx <thing>` may not put software on a machine silently. Every install
    route goes through one helper that prints the command first, so there is one
    place to check rather than three."""
    src = open(os.path.join(ROOT, 'packaging', 'npm', 'bin', 'archeus.js'),
               encoding='utf-8').read()
    body = src[src.index('function install('):]
    body = body[:body.index('\nfunction ')]
    assert 'spawnSync' not in body, \
        'the install path spawns directly instead of going through run(), which prints'
    assert body.count('run(') >= 2, 'no install command is announced'


def test_the_npm_launcher_never_runs_its_own_shim():
    """`npx archeus` puts npm's generated shim on PATH under the name the
    launcher then looks up, so a bare `where archeus` finds the launcher
    itself. Executing that is fatal on Windows (`spawnSync` will not run a
    `.cmd` without `shell:true`, and a null status exits 1 printing nothing —
    2.4.0 shipped exactly that, so the package's headline command did nothing)
    and infinite on POSIX, where the shim is a symlink back to the same file.

    The resolution has to reject a node shim and keep a real console script:
    `.exe` on Windows, and anything not resolving inside `node_modules`
    elsewhere.
    """
    src = open(os.path.join(ROOT, 'packaging', 'npm', 'bin', 'archeus.js'),
               encoding='utf-8').read()
    assert "exec('archeus'" not in src, \
        'the launcher execs the bare name, which under npx is its own shim'
    body = src[src.index('function commandOnPath('):]
    body = body[:body.index('\nfunction ')]
    assert "'.exe'" in body, 'nothing keeps the Windows lookup to a console script'
    assert 'node_modules' in body, 'nothing rejects an npm shim off PATH'


def test_the_shim_pins_a_version_of_this_package_that_is_not_out_yet():
    """The pin is the whole mechanism, not a formality.

    Upgrading the old distribution uninstalls its own previous version first,
    and that version's RECORD still lists the shared `claude_sessions` files —
    so it deletes this package's copy of them on the way out. Requiring a
    version the user does NOT have forces pip to reinstall archeus in the same
    transaction, which puts the files back. Pin a version they already have and
    the requirement is satisfied without reinstalling anything, leaving an
    install that cannot import itself.

    So the release order is: this package first, then the shim.
    """
    import re
    shim = os.path.join(ROOT, 'packaging', 'legacy-name', 'pyproject.toml')
    pin = re.search(r'"archeus>=([^"]+)"',
                    open(shim, encoding='utf-8').read()).group(1)
    here = _version(os.path.join(ROOT, 'pyproject.toml'))
    assert _tuple(pin) > _tuple(here), (
        'the shim pins archeus>=%s and this tree is already %s — publishing it '
        'would not reinstall the shared files it deletes' % (pin, here))


def test_the_python_classifiers_match_requires_python():
    """PyPI's "Programming Language" facet filters on the per-minor classifiers.
    `Programming Language :: Python :: 3` alone puts the package in no version
    bucket, so narrowing a search to 3.12 does not find it — and the list is
    hand-written, so it drifts from requires-python silently the first time a
    version is added to the CI matrix.

    Also asserts the reverse: a classifier claiming a version this package does
    not support is a package that fails to install for whoever believed it."""
    import re
    with open(os.path.join(ROOT, 'pyproject.toml'), encoding='utf-8') as f:
        text = f.read()
    floor = re.search(r'requires-python\s*=\s*">=3\.(\d+)"', text)
    assert floor, 'requires-python is no longer a simple >=3.x floor'
    claimed = {int(m) for m in re.findall(
        r'"Programming Language :: Python :: 3\.(\d+)"', text)}
    assert claimed, 'no per-minor Python classifier — PyPI cannot filter on version'
    assert min(claimed) == int(floor.group(1)), (
        'classifiers start at 3.%d but requires-python says >=3.%s'
        % (min(claimed), floor.group(1)))
    assert claimed == set(range(min(claimed), max(claimed) + 1)), \
        'the classifier list has a gap: %s' % sorted(claimed)


def test_no_classifier_claims_something_the_package_does_not_ship():
    """A classifier is a machine-readable claim, not a keyword. `Typing :: Typed`
    tells every type checker to look for a `py.typed` marker in the installed
    package; without one it is a claim that fails at the point someone relies
    on it."""
    with open(os.path.join(ROOT, 'pyproject.toml'), encoding='utf-8') as f:
        text = f.read()
    if '"Typing :: Typed"' in text:
        assert os.path.isfile(os.path.join(ROOT, 'claude_sessions', 'py.typed')), \
            'the Typed classifier is there but claude_sessions/py.typed is not'
