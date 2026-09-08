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
    monkeypatch.setattr(v.proc, 'spawn_terminal',
                        lambda argv, **k: (seen.append(argv) or (object(), '')))

    monkeypatch.setattr(v, 'self_install_mode', lambda: 'pipx')
    assert v.update_self()[0]
    assert seen[-1][5:] == ['pipx', 'upgrade', 'archeus']

    monkeypatch.setattr(v, 'self_install_mode', lambda: 'pip')
    assert v.update_self()[0]
    assert seen[-1][6:] == ['-m', 'pip', 'install', '-U', 'archeus']


def test_the_upgrade_is_deferred_to_a_window_that_waits_for_this_process(monkeypatch, tmp_path):
    """pip rewrites the console script, which Windows keeps locked while it is
    the running process — so the install cannot happen here. The spawned command
    carries our pid and re-enters archeus through the __main__ dispatch that
    imports nothing pip is about to replace."""
    Sandbox(monkeypatch, tmp_path)
    seen = []
    monkeypatch.setattr(v.proc, 'spawn_terminal',
                        lambda argv, **k: (seen.append(argv) or (object(), '')))
    monkeypatch.setattr(v, 'self_install_mode', lambda: 'pip')
    ok, _msg = v.update_self()
    assert ok
    argv = seen[0]
    assert argv[1:4] == ['-m', 'claude_sessions', '--self-update']
    assert argv[4] == str(os.getpid())


def test_a_failed_spawn_is_not_reported_as_a_scheduled_update(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    monkeypatch.setattr(v, 'self_install_mode', lambda: 'pip')
    monkeypatch.setattr(v.proc, 'spawn_terminal', lambda argv, **k: (None, 'no console'))
    ok, msg = v.update_self()
    assert ok is False and 'no console' in msg


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
    monkeypatch.setattr(v, 'update_self', lambda: (calls.append(1) or (True, 'ok')))

    for mode, expect in (('notify', 0), ('off', 0), ('auto', 1)):
        del calls[:]
        s = config_mod.load_settings()
        s['auto_update'] = mode
        config_mod.save_settings(s)
        v.update_on_quit()
        assert len(calls) == expect, mode


def test_the_deferred_worker_waits_for_the_pid_then_runs(monkeypatch):
    """proc.wait_and_run is what makes a program able to replace its own files.
    It lives in proc so the waiting process imports nothing pip is replacing."""
    import subprocess as _sp
    alive = [True, True, False]
    monkeypatch.setattr(proc, 'pid_alive', lambda p: alive.pop(0) if alive else False)
    ran = []
    monkeypatch.setattr(_sp, 'call', lambda argv: ran.append(argv) or 0)
    rc = proc.wait_and_run(1234, ['pipx', 'upgrade', 'archeus'],
                           poll=0, out=lambda *a: None)
    assert rc == 0 and ran == [['pipx', 'upgrade', 'archeus']]
    assert alive == []          # it really waited rather than running straight away


def test_the_worker_refuses_an_empty_command(monkeypatch):
    assert proc.wait_and_run(1, [], out=lambda *a: None) == 2


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
