"""Versions: what is installed, what has been released, and updating either.

Two findings are pinned here because they are what the feature turned on:

- `claude plugin list --available --json` returns ONLY the official catalogue,
  so the marketplace side is read off each marketplace's own manifest instead;
- `git -C <clone> rev-parse HEAD` fails on those clones with *dubious
  ownership*, so a sha comes out of `.git` by hand.
"""

import io
import json
import os
import sys
import urllib.request
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox, DOWN, ENTER, ESC, run_flow

from claude_sessions import config as config_mod
from claude_sessions import jsonstore, plugins, proc
from claude_sessions import versions as v


class _R:
    def __init__(self, out='', rc=0):
        self.stdout, self.stderr, self.returncode = out, '', rc


def _exe(monkeypatch, path='C:/Users/x/.local/bin/claude.exe'):
    monkeypatch.setattr(config_mod, 'get_claude_exe', lambda: path)


def _npm(monkeypatch, versions=('2.1.239', '2.1.240', '2.1.241'),
         latest='2.1.241', stable='2.1.231', calls=None):
    doc = json.dumps({'dist-tags': {'latest': latest, 'stable': stable},
                      'versions': {x: {} for x in versions}}).encode()

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=0):
        if calls is not None:
            calls.append(getattr(req, 'full_url', req))
        return _Resp(doc)

    monkeypatch.setattr(urllib.request, 'urlopen', fake)


# ── the installed version ────────────────────────────────────

def test_the_installed_version_is_parsed_out_of_the_banner(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _exe(monkeypatch)
    monkeypatch.setattr(proc, 'run', lambda *a, **k: _R('2.1.241 (Claude Code)\n'))
    assert v.installed_version() == '2.1.241'


def test_no_claude_no_version_and_no_crash(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    monkeypatch.setattr(config_mod, 'get_claude_exe', lambda: None)
    assert v.installed_version() == ''
    assert v.install_mode() == ''


def test_a_dead_claude_is_not_a_version(monkeypatch, tmp_path):
    """proc.run returns None on any failure — that must read as "unknown",
    never as a crash on the screen that is supposed to report it."""
    Sandbox(monkeypatch, tmp_path)
    _exe(monkeypatch)
    monkeypatch.setattr(proc, 'run', lambda *a, **k: None)
    assert v.installed_version() == ''


# ── the release list ─────────────────────────────────────────

def test_released_is_cached_for_an_hour_and_refreshes_on_demand(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    calls = []
    _npm(monkeypatch, calls=calls)

    first = v.released()
    assert first['latest'] == '2.1.241' and first['stable'] == '2.1.231'
    assert first['versions'][0] == '2.1.241'          # newest first
    assert len(calls) == 1

    v.released()                                     # served from disk
    assert len(calls) == 1
    v.released(refresh=True)                          # the user asked
    assert len(calls) == 2


def test_a_dead_network_keeps_the_cached_list_and_says_why(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _npm(monkeypatch)
    v.released()

    def boom(*a, **k):
        raise OSError('no route to host')
    monkeypatch.setattr(urllib.request, 'urlopen', boom)

    out = v.released(refresh=True)
    assert out['versions'][0] == '2.1.241'           # the stale answer survives
    assert 'no route' in out['error']


# ── status ───────────────────────────────────────────────────

def test_status_counts_how_many_releases_behind(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _exe(monkeypatch)
    _npm(monkeypatch)
    monkeypatch.setattr(proc, 'run', lambda *a, **k: _R('2.1.239 (Claude Code)'))
    st = v.status()
    assert st['installed'] == '2.1.239'
    assert st['behind'] == 2 and st['current'] is False
    assert st['target'] == '2.1.241'


def test_status_follows_the_configured_channel(monkeypatch, tmp_path):
    """`autoUpdatesChannel: stable` is what Claude Code's own updater follows,
    so "current" has to mean current on THAT channel — a stable install is not
    out of date because a newer latest exists."""
    sb = Sandbox(monkeypatch, tmp_path)
    from claude_sessions import hooks
    (sb.cfg / 'settings.json').write_text(
        json.dumps({'autoUpdatesChannel': 'stable'}), encoding='utf-8')
    monkeypatch.setattr(hooks, 'settings_path', str(sb.cfg / 'settings.json'))
    _exe(monkeypatch)
    _npm(monkeypatch, versions=('2.1.231', '2.1.241'))
    monkeypatch.setattr(proc, 'run', lambda *a, **k: _R('2.1.231 (Claude Code)'))
    st = v.status()
    assert st['channel'] == 'stable'
    assert st['target'] == '2.1.231' and st['current'] is True


# ── updating claude code ─────────────────────────────────────

def test_no_target_updates_and_a_target_installs(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _exe(monkeypatch)
    seen = []
    monkeypatch.setattr(plugins, '_claude_cli',
                        lambda args, timeout=120, **kw: (seen.append(args) or (True, 'ok')))
    v.update_claude('')
    v.update_claude('2.1.240')
    assert seen == [['update'], ['install', '2.1.240']]


def test_stable_and_latest_are_valid_targets(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _exe(monkeypatch)
    seen = []
    monkeypatch.setattr(plugins, '_claude_cli',
                        lambda args, timeout=120, **kw: (seen.append(args) or (True, 'ok')))
    assert v.update_claude('stable')[0]
    assert seen[-1] == ['install', 'stable']


def test_junk_is_never_passed_to_the_installer(monkeypatch, tmp_path):
    """The target reaches a subprocess, so it is validated here rather than
    trusted — `2.1.240; rm -rf` is not a version."""
    Sandbox(monkeypatch, tmp_path)
    _exe(monkeypatch)
    called = []
    monkeypatch.setattr(plugins, '_claude_cli',
                        lambda args, timeout=120: (called.append(args) or (True, '')))
    ok, msg = v.update_claude('2.1.240 && del *')
    assert ok is False and 'not a version' in msg
    assert called == []


def test_an_npm_install_is_reported_not_overwritten(monkeypatch, tmp_path):
    """`claude install` writes the NATIVE build. Running it over an npm install
    leaves two Claude Codes on the machine with the npm one still first on
    PATH, so archeus hands back the npm command instead."""
    Sandbox(monkeypatch, tmp_path)
    _exe(monkeypatch, 'C:/Users/x/AppData/Roaming/npm/claude.cmd')
    called = []
    monkeypatch.setattr(plugins, '_claude_cli',
                        lambda args, timeout=120: (called.append(args) or (True, '')))
    ok, msg = v.update_claude('')
    assert ok is False and 'npm install -g' in msg
    assert called == []


# ── plugins ──────────────────────────────────────────────────

def _mkt(sb, name, entries, sha='', installed=None):
    """One marketplace on disk: its manifest, optionally a .git HEAD, and the
    installed-plugins record that archeus reads."""
    root = sb.cfg / 'plugins'
    mroot = root / 'marketplaces' / name
    (mroot / '.claude-plugin').mkdir(parents=True, exist_ok=True)
    (mroot / '.claude-plugin' / 'marketplace.json').write_text(
        json.dumps({'name': name, 'plugins': entries}), encoding='utf-8')
    if sha:
        (mroot / '.git' / 'refs' / 'heads').mkdir(parents=True, exist_ok=True)
        (mroot / '.git' / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')
        (mroot / '.git' / 'refs' / 'heads' / 'main').write_text(sha + '\n', encoding='utf-8')
    known = {}
    kp = root / 'known_marketplaces.json'
    if kp.is_file():
        known = json.loads(kp.read_text(encoding='utf-8'))
    known[name] = {'source': {'source': 'github', 'repo': 'o/' + name},
                   'installLocation': str(mroot), 'lastUpdated': ''}
    kp.write_text(json.dumps(known), encoding='utf-8')
    if installed is not None:
        (root / 'installed_plugins.json').write_text(
            json.dumps({'version': 2, 'plugins': installed}), encoding='utf-8')
    return mroot


def test_a_marketplace_that_declares_a_version_is_compared_by_version(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    _mkt(sb, 'mkt', [{'name': 'demo', 'version': '2.0.0'}],
         installed={'demo@mkt': [{'scope': 'user', 'version': '1.0.0',
                                  'installPath': str(tmp_path)}]})
    row = v.plugin_rows()[0]
    assert row['available'] == '2.0.0'
    assert row['outdated'] is True


def test_v_prefixes_do_not_make_a_plugin_look_outdated(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    _mkt(sb, 'mkt', [{'name': 'demo', 'version': 'v1.0.0'}],
         installed={'demo@mkt': [{'scope': 'user', 'version': '1.0.0',
                                  'installPath': str(tmp_path)}]})
    assert v.plugin_rows()[0]['outdated'] is False


def test_a_plugin_that_is_its_own_marketplace_compares_against_the_clone_head(
        monkeypatch, tmp_path):
    """`source: './'` means the plugin IS the marketplace repo, so what an
    update would install is that clone's HEAD — read out of `.git` because git
    itself refuses these directories."""
    sb = Sandbox(monkeypatch, tmp_path)
    sha = 'abcdef0123456789abcdef0123456789abcdef01'
    _mkt(sb, 'mkt', [{'name': 'demo', 'source': './'}], sha=sha,
         installed={'demo@mkt': [{'scope': 'user', 'version': sha[:12],
                                  'gitCommitSha': sha, 'installPath': str(tmp_path)}]})
    row = v.plugin_rows()[0]
    assert row['available'] == sha[:12]
    assert row['outdated'] is False


def test_a_moved_clone_head_marks_the_plugin_outdated(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    old = '1111111111111111111111111111111111111111'
    new = '2222222222222222222222222222222222222222'
    _mkt(sb, 'mkt', [{'name': 'demo', 'source': './'}], sha=new,
         installed={'demo@mkt': [{'scope': 'user', 'version': old[:12],
                                  'gitCommitSha': old, 'installPath': str(tmp_path)}]})
    assert v.plugin_rows()[0]['outdated'] is True


def test_a_packed_ref_is_still_a_head(monkeypatch, tmp_path):
    """A freshly cloned repo keeps its refs in packed-refs, with no loose file
    for the branch at all."""
    sb = Sandbox(monkeypatch, tmp_path)
    sha = '3333333333333333333333333333333333333333'
    mroot = _mkt(sb, 'mkt', [{'name': 'demo', 'source': './'}],
                 installed={'demo@mkt': [{'scope': 'user', 'version': sha[:12],
                                          'gitCommitSha': sha,
                                          'installPath': str(tmp_path)}]})
    (mroot / '.git').mkdir(parents=True, exist_ok=True)
    (mroot / '.git' / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')
    (mroot / '.git' / 'packed-refs').write_text(
        '# pack-refs with: peeled\n%s refs/heads/main\n' % sha, encoding='utf-8')
    assert v.plugin_rows()[0]['available'] == sha[:12]


def test_a_silent_marketplace_is_not_reported_as_up_to_date(monkeypatch, tmp_path):
    """"Not checked" and "current" are different answers, and conflating them is
    how a stale plugin hides."""
    sb = Sandbox(monkeypatch, tmp_path)
    _mkt(sb, 'mkt', [{'name': 'other'}],
         installed={'demo@mkt': [{'scope': 'user', 'version': '1.0.0',
                                  'installPath': str(tmp_path)}]})
    row = v.plugin_rows()[0]
    assert row['available'] == '' and row['outdated'] is None


def test_the_official_catalogue_pins_by_sha(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    sha = '30287f5e3f122a646d1ac5ca3ab96e130c52a3ad'
    _mkt(sb, 'off', [{'name': 'demo', 'source': {
        'source': 'git-subdir', 'url': 'https://x/y.git', 'ref': 'v1.5.5', 'sha': sha}}],
        installed={'demo@off': [{'scope': 'user', 'version': sha[:12],
                                 'gitCommitSha': sha, 'installPath': str(tmp_path)}]})
    row = v.plugin_rows()[0]
    assert row['ref'] == 'v1.5.5'
    assert row['outdated'] is False


def test_updating_a_plugin_accepts_no_tty(monkeypatch, tmp_path):
    """-y is not optional: without a TTY the CLI refuses rather than prompting,
    and a job that waits on a prompt nobody can answer just times out."""
    Sandbox(monkeypatch, tmp_path)
    seen = []
    monkeypatch.setattr(plugins, '_claude_cli',
                        lambda args, timeout=120, **kw: (seen.append(args) or (True, 'ok')))
    v.update_plugin('demo@mkt')
    assert seen == [['plugin', 'update', 'demo@mkt', '-y']]
    assert v.update_plugin('')[0] is False


def test_refreshing_marketplaces_can_name_one_or_all(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    seen = []
    monkeypatch.setattr(plugins, '_claude_cli',
                        lambda args, timeout=120, **kw: (seen.append(args) or (True, '')))
    v.update_marketplaces()
    v.update_marketplaces('mkt')
    assert seen == [['plugin', 'marketplace', 'update'],
                    ['plugin', 'marketplace', 'update', 'mkt']]


def test_the_cache_is_written_inside_the_account_dir(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    _npm(monkeypatch)
    v.released()
    assert (sb.cfg / 'archeus-versions.json').is_file()
    assert time.time() - json.loads(
        (sb.cfg / 'archeus-versions.json').read_text(encoding='utf-8')
    )['fetched'] < 60


# ── archeus's own version ──────────────────────────────────

class _Dist:
    """Enough of importlib.metadata.Distribution for versions._dist()."""

    def __init__(self, version='1.6.0', direct_url=None, pkg_dir=None):
        self.version = version
        self._direct = direct_url
        self._pkg = pkg_dir or os.path.dirname(v.__file__)

    def locate_file(self, name):
        # '' is the distribution root (site-packages); a name is a path in it —
        # the same two answers importlib.metadata gives, and both are read.
        return self._pkg if name else os.path.dirname(self._pkg)

    def read_text(self, name):
        return self._direct if name == 'direct_url.json' else None


def _self(monkeypatch, dist=None, ver=None):
    """Pin what archeus looks like: a distribution (or none), and clear the
    installed-version memo so one test cannot leak into the next."""
    monkeypatch.setattr(v, '_SELF_VER', None)
    monkeypatch.setattr(v, '_dist', lambda: dist)
    if ver is not None:
        monkeypatch.setattr(v, '_source_version', lambda: ver)


def _pypi(monkeypatch, latest='1.7.0', calls=None):
    doc = json.dumps({'info': {'version': latest}}).encode()

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=0):
        if calls is not None:
            calls.append(getattr(req, 'full_url', req))
        return _Resp(doc)

    monkeypatch.setattr(urllib.request, 'urlopen', fake)


def test_a_checkout_reports_its_version_and_refuses_to_be_pip_upgraded(monkeypatch, tmp_path):
    """`python claude-sessions.py` is not an installed distribution. It still has
    a version (pyproject says so) — but installing a release over it would leave
    the checkout untouched and the user confused about which one is running."""
    Sandbox(monkeypatch, tmp_path)
    _self(monkeypatch, dist=None, ver='1.6.0')
    assert v.self_installed() == '1.6.0'
    assert v.self_install_mode() == 'checkout'
    ok, msg = v.update_self()
    assert ok is False and 'git pull' in msg


def test_an_installed_copy_shadowed_by_a_checkout_is_not_the_one_running(monkeypatch, tmp_path):
    """A checkout early on sys.path shadows a pip install: importlib still finds
    the site-packages dist-info. Believing it would report the wrong version and
    upgrade a package this process is not using."""
    Sandbox(monkeypatch, tmp_path)
    monkeypatch.setattr(v, '_SELF_VER', None)
    elsewhere = str(tmp_path / 'site-packages' / 'claude_sessions')
    from importlib import metadata as _md
    monkeypatch.setattr(_md, 'distribution',
                        lambda name: _Dist(version='1.5.0', pkg_dir=elsewhere))
    assert v._dist() is None                       # not the one we are running
    assert v.self_install_mode() == 'checkout'


def test_an_editable_install_is_a_checkout(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _self(monkeypatch, dist=_Dist(direct_url=json.dumps(
        {'url': 'file:///d/claude', 'dir_info': {'editable': True}})))
    assert v.self_install_mode() == 'checkout'


def test_a_pipx_venv_is_recognised_by_its_path(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    pipx = os.path.join('C:', os.sep, 'Users', 'x', 'pipx', 'venvs', 'archeus',
                        'Lib', 'site-packages', 'claude_sessions')
    _self(monkeypatch, dist=_Dist(pkg_dir=pipx))
    assert v.self_install_mode() == 'pipx'

    _self(monkeypatch, dist=_Dist(pkg_dir=os.path.join(
        'C:', os.sep, 'Python312', 'Lib', 'site-packages', 'claude_sessions')))
    assert v.self_install_mode() == 'pip'


def test_pipx_home_is_honoured_when_the_path_does_not_say_pipx(monkeypatch, tmp_path):
    """PIPX_HOME relocates the venvs, so the path no longer carries the word."""
    Sandbox(monkeypatch, tmp_path)
    home = tmp_path / 'tools'
    monkeypatch.setenv('PIPX_HOME', str(home))
    _self(monkeypatch, dist=_Dist(
        pkg_dir=str(home / 'venvs' / 'archeus' / 'lib' / 'claude_sessions')))
    assert v.self_install_mode() == 'pipx'


def test_pipx_and_pip_get_different_upgrade_commands(monkeypatch, tmp_path):
    """`pipx upgrade` and `pip install -U` are not interchangeable — the wrong
    one either does nothing or installs into the wrong environment."""
    Sandbox(monkeypatch, tmp_path)
    seen = []
    monkeypatch.setattr(v.proc, 'spawn_detached',
                        lambda argv, **k: (seen.append(argv) or (object(), '')))

    monkeypatch.setattr(v, 'self_install_mode', lambda: 'pipx')
    assert v.update_self()[0]
    assert seen[-1][5:] == ['pipx', 'upgrade', 'archeus']

    monkeypatch.setattr(v, 'self_install_mode', lambda: 'pip')
    assert v.update_self()[0]
    assert seen[-1][6:] == ['-m', 'pip', 'install', '-U', 'archeus']


def test_the_upgrade_is_deferred_to_a_worker_that_waits_for_this_process(monkeypatch, tmp_path):
    """pip rewrites the console script, which Windows keeps locked while it is
    the running process — so the install cannot happen HERE. It happens in the
    worker, which re-enters archeus through the __main__ dispatch that imports
    nothing pip is about to replace.

    Which pid it carries is the whole difference between the two modes: 0 means
    "install now, beside the running archeus", and our own pid means "wait for
    it to go first", which is what *install on quit* and *restart* need."""
    Sandbox(monkeypatch, tmp_path)
    seen = []
    monkeypatch.setattr(v.proc, 'spawn_detached',
                        lambda argv, **k: (seen.append(argv) or (object(), '')))
    monkeypatch.setattr(v, 'self_install_mode', lambda: 'pip')
    ok, _msg = v.update_self()
    assert ok
    argv = seen[0]
    assert argv[1:4] == ['-m', 'claude_sessions', '--self-update']
    assert argv[4] == '0', 'Update now waited for something'

    del seen[:]
    ok, _msg = v.update_self(defer=True)
    assert ok and seen[0][4] == str(os.getpid())


def test_the_upgrade_worker_gets_no_window_of_its_own(monkeypatch, tmp_path):
    """The bug this replaced: the worker's first act is to BLOCK on our pid, so
    a console for it took the foreground and then sat there showing `Waiting for
    archeus to exit...` until the user quit — which reads as the update having
    hung. Nothing about the upgrade may reach spawn_terminal any more."""
    Sandbox(monkeypatch, tmp_path)
    monkeypatch.setattr(v, 'self_install_mode', lambda: 'pip')
    console = []
    monkeypatch.setattr(v.proc, 'spawn_terminal',
                        lambda *a, **k: console.append(a) or (None, 'x'))
    seen = {}
    monkeypatch.setattr(v.proc, 'spawn_detached',
                        lambda argv, **k: (seen.update(k) or (object(), '')))
    assert v.update_self()[0]
    assert not console, 'the upgrade opened a terminal window'
    assert seen.get('log'), 'a windowless worker with no log leaves no trace of a failure'


def test_a_detached_spawn_never_asks_for_a_console():
    """The two flags are opposites and this module holds both, so the seam that
    exists to avoid a window must not be reachable from the one that opens it."""
    src = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'claude_sessions', 'proc.py'),
        encoding='utf-8').read()
    body = src[src.index('def spawn_detached('):src.index('def wait_and_run(')]
    assert 'new_console_flags' not in body
    assert 'detached_flags' in body           # Windows
    assert 'start_new_session' in body        # POSIX


def test_the_worker_is_told_what_to_announce_and_whether_to_come_back(monkeypatch, tmp_path):
    """Both instructions travel in the ENVIRONMENT, so the command line stays
    exactly what __main__'s --self-update dispatch already parses — the pid has
    to remain argv[4]."""
    Sandbox(monkeypatch, tmp_path)
    _self(monkeypatch, dist=_Dist(version='1.6.0'))
    _pypi(monkeypatch, latest='1.7.0')
    v.self_released()
    monkeypatch.setattr(v, 'self_install_mode', lambda: 'pip')
    seen = {}
    monkeypatch.setattr(v.proc, 'spawn_detached',
                        lambda argv, **k: (seen.update(k, argv=argv) or (object(), '')))

    v.update_self()
    assert seen['env']['ARCHEUS_UPDATE_TO'] == '1.7.0'
    assert 'ARCHEUS_RELAUNCH' not in seen['env'], 'staging must not relaunch on its own'

    v.update_self(restart=True)
    relaunch = json.loads(seen['env']['ARCHEUS_RELAUNCH'])
    # `-m claude_sessions`, never sys.argv[0]: the console script is the file pip
    # is replacing. And --gui, because the restart button only exists there.
    assert relaunch[1:3] == ['-m', 'claude_sessions'] and '--gui' in relaunch
    assert seen['argv'][4] == str(os.getpid())


def test_a_failed_spawn_is_not_reported_as_a_scheduled_update(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    monkeypatch.setattr(v, 'self_install_mode', lambda: 'pip')
    monkeypatch.setattr(v.proc, 'spawn_detached', lambda argv, **k: (None, 'no worker'))
    ok, msg = v.update_self()
    assert ok is False and 'no worker' in msg


def test_pypi_is_cached_for_a_day_and_refreshes_on_demand(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    calls = []
    _pypi(monkeypatch, calls=calls)
    assert v.self_released()['latest'] == '1.7.0'
    assert len(calls) == 1
    v.self_released()                       # served from disk
    assert len(calls) == 1
    v.self_released(refresh=True)
    assert len(calls) == 2
    assert (sb.cfg / 'archeus-self.json').is_file()


def test_the_two_version_caches_do_not_overwrite_each_other(monkeypatch, tmp_path):
    """released() writes its whole document, so archeus's answer lives in its
    own file — sharing one would mean each fetch erasing the other."""
    sb = Sandbox(monkeypatch, tmp_path)
    _npm(monkeypatch)
    v.released()
    _pypi(monkeypatch)
    v.self_released()
    assert json.loads((sb.cfg / 'archeus-versions.json').read_text(
        encoding='utf-8'))['latest'] == '2.1.241'
    assert json.loads((sb.cfg / 'archeus-self.json').read_text(
        encoding='utf-8'))['latest'] == '1.7.0'


def test_a_dead_pypi_keeps_the_cached_answer_and_says_why(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _pypi(monkeypatch)
    v.self_released()

    def boom(*a, **k):
        raise OSError('no route to host')
    monkeypatch.setattr(urllib.request, 'urlopen', boom)
    out = v.self_released(refresh=True)
    assert out['latest'] == '1.7.0'
    assert 'no route' in out['error']


def test_status_says_whether_archeus_is_behind(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _self(monkeypatch, dist=_Dist(version='1.6.0'))
    _pypi(monkeypatch, latest='1.7.0')
    st = v.self_status(refresh=True)
    assert st['installed'] == '1.6.0' and st['latest'] == '1.7.0'
    assert st['update'] is True and st['current'] is False

    monkeypatch.setattr(v, '_SELF_VER', None)
    monkeypatch.setattr(v, '_dist', lambda: _Dist(version='1.7.0'))
    st = v.self_status(refresh=True)
    assert st['update'] is False and st['current'] is True


def test_a_newer_installed_build_is_not_an_update(monkeypatch, tmp_path):
    """Running 1.8.0.dev against a published 1.7.0 must not offer a downgrade."""
    Sandbox(monkeypatch, tmp_path)
    _self(monkeypatch, dist=_Dist(version='1.8.0'))
    _pypi(monkeypatch, latest='1.7.0')
    assert v.self_status(refresh=True)['update'] is False


def test_the_banner_notice_never_touches_the_network(monkeypatch, tmp_path):
    """ui.menu re-polls banner_fn every 0.5s, so a fetch here is a stall twice a
    second — and the case that matters is a cache past its TTL, which is exactly
    when a well-meaning `self_released()` call WOULD go to the network. Warming
    the cache first would only prove the TTL works, not that this reads it."""
    Sandbox(monkeypatch, tmp_path)
    _self(monkeypatch, dist=_Dist(version='1.6.0'))
    jsonstore.save(v._self_cache_path(),
                   {'latest': '1.7.0', 'fetched': time.time() - v.SELF_TTL * 10})

    def boom(*a, **k):
        raise AssertionError('update_notice fetched')
    monkeypatch.setattr(urllib.request, 'urlopen', boom)
    assert '1.7.0' in v.update_notice()


def test_no_notice_when_there_is_nothing_to_say(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _self(monkeypatch, dist=_Dist(version='1.7.0'))
    _pypi(monkeypatch, latest='1.7.0')
    v.self_released()
    assert v.update_notice() == ''


def test_off_means_no_outbound_check_at_all(monkeypatch, tmp_path):
    """One switch covers every network check archeus makes on the user's
    behalf, so 'off' has to actually stop the thread starting."""
    Sandbox(monkeypatch, tmp_path)
    monkeypatch.setattr(v, '_bg_started', False)
    s = config_mod.load_settings()
    s['auto_update'] = 'off'
    config_mod.save_settings(s)
    started = []
    monkeypatch.setattr(v, 'self_released',
                        lambda *a, **k: started.append(1) or {})
    v.start_background_check()
    assert started == []


def test_only_auto_installs_on_quit(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _self(monkeypatch, dist=_Dist(version='1.6.0'))
    _pypi(monkeypatch, latest='1.7.0')
    v.self_released()
    calls = []
    monkeypatch.setattr(v, 'update_self',
                        lambda **k: (calls.append(k) or (True, 'ok')))

    for mode, expect in (('notify', 0), ('off', 0), ('auto', 1)):
        del calls[:]
        s = config_mod.load_settings()
        s['auto_update'] = mode
        config_mod.save_settings(s)
        v.update_on_quit()
        assert len(calls) == expect, mode
    # and it DEFERS — an install on quit that did not wait for the quit would be
    # pip against a live process, which is the one thing that must not happen
    assert calls and calls[-1].get('defer') is True, calls


def _fake_run(seen, rc, stdout='', stderr=''):
    """A stand-in for `proc.run`, which is how the worker executes the install
    now — captured rather than inherited, because a detached parent's file
    handle is NOT inherited by a child that redirects nothing, so pip came up
    with no stdout at all and (under pythonw) died of it, silently."""
    class R:
        returncode, stdout, stderr = rc, '', ''
    R.stdout, R.stderr = stdout, stderr
    return lambda argv, **k: (seen.append(argv), R)[1]


def test_the_deferred_worker_waits_for_the_pid_then_runs(monkeypatch):
    """proc.wait_and_run is what makes a program able to replace its own files.
    It lives in proc so the waiting process imports nothing pip is replacing."""
    alive = [True, True, False]
    monkeypatch.setattr(proc, 'pid_alive', lambda p: alive.pop(0) if alive else False)
    ran = []
    monkeypatch.setattr(proc, 'run', _fake_run(ran, 0))
    rc = proc.wait_and_run(1234, ['pipx', 'upgrade', 'archeus'],
                           poll=0, out=lambda *a: None)
    assert rc == 0 and ran == [['pipx', 'upgrade', 'archeus']]
    assert alive == []          # it really waited rather than running straight away


def test_the_worker_refuses_an_empty_command(monkeypatch):
    assert proc.wait_and_run(1, [], out=lambda *a: None) == 2


# ── the wait is unbounded, and giving up does not mean installing anyway ──
#
#     "the update now function is still broken"
#
# It was capped at five minutes. The banner says "it installs when you close
# archeus" and the user keeps working, so the cap fired first every time: pip
# ran against the live process, met the console script it had been deferred to
# avoid, and failed into a log file with no window and no reader.

def test_the_worker_waits_as_long_as_archeus_runs(monkeypatch):
    """A session lasts hours; the deferral has to outlast it. Asserted on the
    default itself because the alternative is a test that sleeps for the old
    five minutes to tell the two apart."""
    import inspect
    assert inspect.signature(proc.wait_and_run).parameters['timeout'].default is None


def test_giving_up_does_not_install_over_a_running_archeus(monkeypatch):
    """A caller that does pass a deadline gets 'could not', never 'did it
    anyway' — the unsafe install is the exact thing the wait exists to avoid."""
    monkeypatch.setattr(proc, 'pid_alive', lambda p: True)      # never exits
    ran = []
    monkeypatch.setattr(proc, 'run', _fake_run(ran, 0))
    said = []
    rc = proc.wait_and_run(4321, ['pip', 'install', '-U', 'archeus'],
                           timeout=0.05, poll=0.01, out=said.append)
    assert ran == [], 'it installed over a process that was still running'
    assert rc != 0
    assert any('NOT installing' in m for m in said), said


def test_the_worker_announces_the_upgrade_only_when_it_worked(monkeypatch):
    """The notification IS the report: the worker has no console to print to and
    the app that staged it is gone by the time it runs. Announcing a failed
    install would be worse than silence — nobody would go looking for the log."""
    monkeypatch.setattr(proc, 'pid_alive', lambda p: False)
    started = []
    monkeypatch.setattr(proc, 'spawn_detached',
                        lambda argv, **k: started.append(argv) or (object(), ''))

    monkeypatch.setattr(proc, 'run', _fake_run([], 0))
    proc.wait_and_run(0, ['pip', 'x'], poll=0, out=lambda *a: None,
                      after=[['toast'], ['archeus', '--gui']])
    assert started == [['toast'], ['archeus', '--gui']]

    del started[:]
    monkeypatch.setattr(proc, 'run', _fake_run([], 1))
    proc.wait_and_run(0, ['pip', 'x'], poll=0, out=lambda *a: None, after=[['toast']])
    assert started == [], 'a failed install still announced itself'


def test_the_worker_resolves_its_after_steps_before_the_install():
    """pip replaces every file in this package, so an import after the install
    is a coin toss between the old files and the new. __main__ builds both argv
    lists — the toast and the relaunch — above the wait, and hands them over as
    plain lists."""
    src = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'claude_sessions', '__main__.py'),
        encoding='utf-8').read()
    branch = src[src.index("== '--self-update'"):src.index('from .main import run')]
    assert 'from .notify import command' in branch
    assert branch.index('from .notify import command') < branch.index('wait_and_run(')
    assert 'ARCHEUS_RELAUNCH' in branch and 'ARCHEUS_UPDATE_TO' in branch


def test_main_dispatches_the_worker_before_importing_the_package(monkeypatch):
    """The whole point of putting --self-update in __main__ is that pip is about
    to replace every file in this package, so the worker must not be holding a
    lazy import of one. Guarding the source keeps that true."""
    src = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'claude_sessions', '__main__.py'),
        encoding='utf-8').read()
    assert src.index('--self-update') < src.index('from .main import run')


# ── the screen ───────────────────────────────────────────────

_SST = {'installed': '1.6.0', 'mode': 'pip', 'latest': '1.6.0',
        'update': False, 'current': True, 'error': '', 'fetched': 0}
_ST = {'installed': '2.1.239', 'mode': 'native', 'channel': 'latest',
       'latest': '2.1.241', 'stable': '2.1.231', 'behind': 2, 'current': False,
       'target': '2.1.241', 'versions': ['2.1.241', '2.1.240', '2.1.239'],
       'local': ['2.1.239', '2.1.232'], 'error': '', 'fetched': 0}
_ROWS = [{'key': 'demo@mkt', 'name': 'demo', 'marketplace': 'mkt',
          'version': '1.0.0', 'sha': '', 'scope': 'user', 'available': '1.1.0',
          'ref': '', 'outdated': True}]


def _screen(monkeypatch, tmp_path, keys, upd=None, plug=None, sst=None, self_upd=None):
    Sandbox(monkeypatch, tmp_path)
    monkeypatch.setattr(v, 'status', lambda refresh=False: dict(_ST))
    monkeypatch.setattr(v, 'self_status', lambda refresh=False: dict(sst or _SST))
    monkeypatch.setattr(v, 'plugin_rows', lambda: [dict(r) for r in _ROWS])
    monkeypatch.setattr(v, 'update_claude', upd or (lambda t='': (True, 'ok')))
    monkeypatch.setattr(v, 'update_plugin', plug or (lambda k: (True, 'ok')))
    monkeypatch.setattr(v, 'update_self', self_upd or (lambda: (True, 'ok')))
    return run_flow(monkeypatch, keys, v.updates_menu)


def test_the_screen_states_archeuss_own_version(monkeypatch, tmp_path):
    _r, cap, _ = _screen(monkeypatch, tmp_path, [*ESC])
    assert 'archeus' in cap.text and '1.6.0' in cap.text
    assert 'installed via pip' in cap.text
    # up to date: no update row competing with Claude Code's
    assert 'Update archeus' not in cap.text


def test_the_archeus_update_row_appears_only_when_one_exists(monkeypatch, tmp_path):
    behind = dict(_SST, latest='1.7.0', update=True, current=False)
    seen = []
    _r, cap, _ = _screen(monkeypatch, tmp_path, [*ENTER, *ESC], sst=behind,
                         self_upd=lambda: (seen.append(1) or (True, 'scheduled')))
    assert 'Update archeus to 1.7.0' in cap.text
    assert seen == [1]          # it is the first selectable row when present


def test_the_screen_states_both_versions_and_what_is_behind(monkeypatch, tmp_path):
    _r, cap, _ = _screen(monkeypatch, tmp_path, [*ESC])
    out = cap.text
    assert 'Claude Code' in out
    assert '2.1.239' in out and '2.1.241' in out
    assert '2 releases behind' in out
    assert 'demo' in out and '1.1.0 available' in out


def test_the_update_row_updates(monkeypatch, tmp_path):
    """First selectable row is the check, second is the update — the update row
    only exists when an update does, which is why the fixture is behind."""
    seen = []
    _screen(monkeypatch, tmp_path, [*DOWN, *ENTER, *ESC],
            upd=lambda t='': (seen.append(t) or (True, 'updated')))
    assert seen == ['']


def test_an_already_downloaded_version_is_offered_for_rollback(monkeypatch, tmp_path):
    """A native install keeps its old builds, so a rollback needs no download —
    the screen offers them by name."""
    _r, cap, _ = _screen(monkeypatch, tmp_path, [*ESC])
    assert 'Roll back to 2.1.232' in cap.text
    assert 'Roll back to 2.1.239' not in cap.text   # that is the installed one


def test_a_plugin_row_updates_that_plugin(monkeypatch, tmp_path):
    seen = []
    # check, update, install-specific, roll back 2.1.232, then the plugin row
    keys = [*DOWN, *DOWN, *DOWN, *DOWN, *ENTER, b'y', *ESC]
    _screen(monkeypatch, tmp_path, keys,
            plug=lambda k: (seen.append(k) or (True, 'updated')))
    assert seen == ['demo@mkt']


# ── why it had never worked, on any path ─────────────────────
#
#     "update now still doesn't work ... right now it doesn't work with
#      archeus closed too"
#
# Two causes, both measured on this machine before they were fixed. The worker
# ran pip with its stdout INHERITED from a detached parent, which Windows does
# not actually inherit, so pip came up with no stdout — under `pythonw`, which
# is what the desktop shell runs on, it exited 1 having printed nothing at all,
# and the update log held the worker's own two lines and no pip output.

def test_the_install_is_captured_not_inherited(monkeypatch):
    """The log is the only voice a windowless worker has, so pip's output has to
    be put there rather than pointed at a handle the child never receives."""
    said = []
    monkeypatch.setattr(proc, 'pid_alive', lambda p: False)
    monkeypatch.setattr(proc, 'run',
                        _fake_run([], 0, stdout='Successfully installed archeus-2.2.0'))
    assert proc.wait_and_run(0, ['pip', 'x'], poll=0, out=said.append) == 0
    assert any('Successfully installed' in m for m in said), said

    del said[:]
    monkeypatch.setattr(proc, 'run', _fake_run([], 1, stderr='ERROR: no matching dist'))
    assert proc.wait_and_run(0, ['pip', 'x'], poll=0, out=said.append) == 1
    assert any('no matching dist' in m for m in said), said


def test_nothing_in_the_upgrade_runs_on_pythonw(monkeypatch, tmp_path):
    """A pythonw child gets `sys.stdout = None` and pip dies of it. The relaunch
    is the deliberate exception: the desktop app runs on pythonw exactly so it
    has no console, and bringing it back on python.exe would give it one."""
    Sandbox(monkeypatch, tmp_path)
    pyw = tmp_path / 'pythonw.exe'
    pyw.write_text('', encoding='utf-8')
    (tmp_path / 'python.exe').write_text('', encoding='utf-8')
    monkeypatch.setattr(v.sys, 'executable', str(pyw))
    monkeypatch.setattr(proc.sys, 'executable', str(pyw))
    assert os.path.basename(proc.python_exe()) == 'python.exe'

    seen = {}
    monkeypatch.setattr(v.proc, 'spawn_detached',
                        lambda argv, **k: (seen.update(argv=argv, env=k.get('env') or {}),
                                           (object(), ''))[1])
    monkeypatch.setattr(v, 'self_install_mode', lambda: 'pip')
    v.update_self(restart=True)
    assert 'pythonw' not in os.path.basename(seen['argv'][0]).lower(), seen['argv']
    assert not any('pythonw' in str(a).lower() for a in seen['argv']), seen['argv']
    relaunch = json.loads(seen['env']['ARCHEUS_RELAUNCH'])
    assert 'pythonw' in relaunch[0].lower(), relaunch


def test_a_locked_console_script_is_moved_aside_and_put_back(tmp_path):
    """Measured, and the reason this exists: with the script locked, `pip install
    -U` fails AFTER uninstalling the old package, so the user is left with
    nothing installed. Renaming is allowed on a running image where overwriting
    is not, which is what makes an install with archeus still open possible."""
    exe = tmp_path / 'archeus.exe'
    exe.write_bytes(b'MZ')
    os.chmod(exe, 0o444)                     # unwritable == locked, portably
    said = []
    moved = proc.free_locked([str(exe)], out=said.append)
    assert moved and not exe.exists(), (moved, said)
    aside = moved[0][0]
    assert os.path.isfile(aside)

    # pip failed: the user must still have the command they started with
    proc.restore_locked(moved, out=said.append)
    assert exe.exists() and not os.path.exists(aside)

    # pip succeeded: the fresh script it wrote is kept, not overwritten
    moved = proc.free_locked([str(exe)], out=said.append)
    exe.write_bytes(b'MZ-new')
    proc.restore_locked(moved, out=said.append)
    assert exe.read_bytes() == b'MZ-new'


def test_an_unlocked_script_is_left_exactly_where_it_is(tmp_path):
    """Most installs are not locked at all — a desktop shortcut runs pythonw, not
    the console script — and moving a file that pip can simply overwrite would
    be damage for nothing."""
    exe = tmp_path / 'archeus.exe'
    exe.write_bytes(b'MZ')
    assert proc.free_locked([str(exe)]) == []
    assert exe.exists()


def test_the_worker_is_only_ever_handed_our_own_console_script(monkeypatch):
    """It MOVES what it is handed, so the list may never name an interpreter."""
    for path in v.console_scripts():
        assert os.path.basename(path).lower() == 'archeus.exe', path
        assert os.path.isfile(path)


# ── the loop: install, restart, "a new version is available" ──
#
#     "it let me install archeus new version then told me to restart archeus to
#      use it, when i restarted it's saying again that a new version is
#      available and it's still showing me the old version"
#
# One `pip install -e .` leaves `<repo>/archeus.egg-info` behind for ever, and
# the checkout is first on sys.path, so importlib.metadata reported the working
# tree as an INSTALLED distribution at whatever version that file was built at.
# Measured here: a 2.2.0 checkout calling itself a 2.1.0 pip install, offering an
# upgrade that pip answered with "Requirement already satisfied" about a
# site-packages copy the process was not running.

def test_a_checkout_with_stale_metadata_beside_it_is_still_a_checkout(
        monkeypatch, tmp_path):
    """The layout decides, not the record sitting next to it."""
    pkg = tmp_path / 'claude_sessions'
    pkg.mkdir()
    (tmp_path / 'pyproject.toml').write_text('version = "9.9.9"\n', encoding='utf-8')
    monkeypatch.setattr(v, '__file__', str(pkg / 'versions.py'))
    monkeypatch.setattr(v, '_SELF_VER', None)

    class _Stale:                       # what the egg-info would have said
        version = '2.1.0'

        def locate_file(self, _x):
            return str(pkg)

        def read_text(self, _x):
            return ''

    import importlib.metadata as _md
    monkeypatch.setattr(_md, 'distribution', lambda _n: _Stale())

    assert v._running_from_source()
    assert v._dist() is None, 'stale metadata was believed'
    assert v.self_install_mode() == 'checkout'
    assert v.self_installed() == '9.9.9', 'the version came from the record, not the code'
    ok, msg = v.update_self()
    assert not ok and 'git pull' in msg, msg


def test_a_real_install_is_still_a_real_install(monkeypatch, tmp_path):
    """The guard is about a repository beside the package — site-packages has no
    pyproject.toml and no .git, so nothing about an installed copy changes."""
    site = tmp_path / 'site-packages'
    pkg = site / 'claude_sessions'
    pkg.mkdir(parents=True)
    monkeypatch.setattr(v, '__file__', str(pkg / 'versions.py'))
    monkeypatch.setattr(v, '_SELF_VER', None)

    class _Real:
        version = '2.2.0'

        def locate_file(self, x):
            return str(site / x) if x else str(site)

        def read_text(self, _x):
            return ''

    import importlib.metadata as _md
    monkeypatch.setattr(_md, 'distribution', lambda _n: _Real())
    assert not v._running_from_source()
    assert v.self_install_mode() == 'pip'
    assert v.self_installed() == '2.2.0'
