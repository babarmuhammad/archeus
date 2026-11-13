"""T-1276: claude_sessions/plugins.py:340-454 at 6bbd3b44 (plugin mutation argument validation and account-local subprocess).

Selected candidates, not measured coverage. Ranked, with the closest existing test:
1  395 ext:: transport refused before any CLI      tests/test_plugins_worktrees.py:142 covers names, not add_marketplace sources
2  397 dash-named existing directory refused      none; strict xfail below
3  404/418 dash and newline marketplace names     tests/test_plugins_worktrees.py:142 covers remove_marketplace, not update_marketplaces
4  432 plugin id is name or name@marketplace      tests/test_plugins_worktrees.py:142 covers bad names only
5  378 unsupported verb refused before lookup     tests/test_plugins_worktrees.py:126 checks the verb table, not refusal order
6  358 missing executable, no env and no process  none
7  360 selected cfgdir reaches env and child      none
8  361 None and nonzero results, 400-char bound   none
9  420 update argv and timeout 600                none
10 350 every mutation pins the requested home     tests/test_plugins_worktrees.py:111 checks one seam, not the env

Branch each test catches: 395 (add_marketplace remote_url_ok), 397 (add_marketplace isdir),
404/418 (_ID guards), 432 (install_plugin spec guard), 378 (_cli verb lookup), 358 (_run exe),
360 (_run account_env and timeout), 361 (_run None and returncode branches), 420 (update_marketplaces
name branch, update_plugin verb), 350 (_run env pinning).
"""

import os
import types

import pytest

from claude_sessions import config as _c
from claude_sessions import harnesses, plugins, proc

CLAUDE = {'id': 'claude', 'label': 'Claude Code', 'exe_names': ['claude']}
CODEX = {'id': 'codex', 'label': 'Codex', 'exe_names': ['codex-cli', 'codex']}


@pytest.fixture
def cli(monkeypatch):
    rec = types.SimpleNamespace(runs=[], env_for=[], exe_lookups=[], reply=None, missing=set())

    def of(cfgdir=None):
        return CODEX if cfgdir == 'codex-home' else CLAUDE

    def exe(hid=None):
        rec.exe_lookups.append(hid)
        return None if hid in rec.missing else '/bin/' + hid

    def account_env(cfgdir=None, harness=None):
        rec.env_for.append(cfgdir)
        return {'CLAUDE_CONFIG_DIR': cfgdir or ''}

    def run(args, **kw):
        rec.runs.append(types.SimpleNamespace(argv=list(args), kw=kw))
        if rec.reply is not None:
            return rec.reply(args)
        return types.SimpleNamespace(returncode=0, stdout='ok', stderr='')

    monkeypatch.setattr(harnesses, 'of', of)
    monkeypatch.setattr(harnesses, 'exe', exe)
    monkeypatch.setattr(_c, 'account_env', account_env)
    monkeypatch.setattr(proc, 'run', run)
    monkeypatch.setattr(proc, 'remote_url_ok', lambda url: url.startswith('https://'))
    return rec


def test_ext_transport_is_refused_before_any_cli(cli):
    ok, msg = plugins.add_marketplace('ext::sh -c touch-x')
    assert ok is False and msg
    assert cli.runs == []
    assert plugins.add_marketplace('acme/market') == (True, 'ok')
    assert cli.runs[0].argv == ['/bin/claude', 'plugin', 'marketplace', 'add', 'acme/market']


def test_local_marketplace_directory_is_accepted(cli, monkeypatch):
    real_isdir = os.path.isdir
    monkeypatch.setattr(os.path, 'isdir', lambda p: p == 'local-market' or real_isdir(p))
    assert plugins.add_marketplace('local-market') == (True, 'ok')
    assert cli.runs[0].argv[-1] == 'local-market'


@pytest.mark.xfail(strict=True, reason="claude_sessions/plugins.py:397-399: a directory whose "
                   "name starts with '-' passes the local-directory branch and reaches the "
                   "CLI option position")
def test_dash_named_existing_directory_is_refused(cli, monkeypatch):
    real_isdir = os.path.isdir
    monkeypatch.setattr(os.path, 'isdir', lambda p: p == '-dash-dir' or real_isdir(p))
    ok, _ = plugins.add_marketplace('-dash-dir')
    assert ok is False
    assert cli.runs == []


def test_dash_and_newline_marketplace_names_refused_before_cli(cli):
    for bad in ('-rf', '--force', 'a\nb', '../x'):
        assert plugins.remove_marketplace(bad)[0] is False
        assert plugins.update_marketplaces(bad)[0] is False
    assert cli.runs == []
    assert plugins.remove_marketplace('claude-plugins-official') == (True, 'ok')
    assert cli.runs[-1].argv[1:] == ['plugin', 'marketplace', 'remove', 'claude-plugins-official']


def test_plugin_id_is_one_whole_name_or_name_at_marketplace(cli):
    refused = [('a b', ''), ('../x', ''), ('--json', ''), ('', ''), ('name', '-m'),
               ('name', 'mkt with space'), ('name@mkt', 'extra@more'), ('name@mkt@x', '')]
    for name, mkt in refused:
        ok, msg = plugins.install_plugin(name, mkt)
        assert ok is False and msg, (name, mkt)
    assert cli.runs == []
    assert plugins.install_plugin('code-review', 'claude-plugins-official') == (True, 'ok')
    assert plugins.install_plugin('code-review@claude-plugins-official') == (True, 'ok')
    assert [r.argv[1:] for r in cli.runs] == [
        ['plugin', 'install', 'code-review@claude-plugins-official']] * 2


def test_unsupported_verb_is_refused_before_lookup_and_never_falls_back(cli):
    assert plugins.update_plugin('code-review@m', cfgdir='codex-home') == (
        False, 'Codex has no update command')
    assert cli.exe_lookups == [] and cli.runs == []
    assert plugins.install_plugin('code-review', 'm', cfgdir='codex-home') == (True, 'ok')
    assert cli.runs[0].argv == ['/bin/codex', 'plugin', 'add', 'code-review@m']


def test_missing_executable_refuses_without_env_or_process(cli):
    cli.missing.add('codex')
    assert plugins._run(['plugin', 'list'], cfgdir='codex-home') == (
        False, 'codex-cli not found')
    assert cli.env_for == [] and cli.runs == []


def test_selected_home_reaches_env_and_child_and_timeout_is_kept(cli):
    assert plugins._run(['plugin', 'list'], timeout=45, cfgdir='acct-two') == (True, 'ok')
    assert cli.env_for == ['acct-two']
    assert cli.runs[0].kw['env'] == {'CLAUDE_CONFIG_DIR': 'acct-two'}
    assert cli.runs[0].kw['timeout'] == 45
    assert plugins._run(['x']) == (True, 'ok')
    assert cli.env_for[-1] is None and cli.runs[-1].kw['timeout'] == 120


def test_none_and_nonzero_results_are_refusals_and_output_is_bounded(cli):
    cli.reply = lambda args: None
    assert plugins._run(['x']) == (False, 'could not run claude')

    cli.reply = lambda args: types.SimpleNamespace(returncode=2, stdout='a' * 300, stderr='b' * 300)
    ok, out = plugins._run(['x'])
    assert ok is False
    assert out == ('a' * 300 + 'b' * 300)[:400] and len(out) == 400

    cli.reply = lambda args: types.SimpleNamespace(returncode=0, stdout='', stderr='')
    assert plugins._run(['x']) == (True, '')


def test_update_argv_is_exact_for_all_and_for_one(cli):
    assert plugins.update_marketplaces() == (True, 'ok')
    assert plugins.update_marketplaces('claude-plugins-official') == (True, 'ok')
    assert plugins.update_plugin('code-review@m') == (True, 'ok')
    update_all, update_named, update_one = cli.runs
    assert update_all.argv[1:] == ['plugin', 'marketplace', 'update']
    assert update_named.argv[1:] == ['plugin', 'marketplace', 'update', 'claude-plugins-official']
    assert update_one.argv[1:] == ['plugin', 'update', '-y', 'code-review@m']
    assert [r.kw['timeout'] for r in cli.runs] == [600, 600, 600]
    assert not any(v in r.argv for r in cli.runs for v in ('install', 'uninstall', 'remove'))


def test_every_mutation_pins_the_requested_home_and_never_uses_a_shell(cli, monkeypatch):
    monkeypatch.setattr(_c, 'config_dir', 'active-home')
    mutations = [
        lambda: plugins.add_marketplace('acme/m', cfgdir='acct-two'),
        lambda: plugins.remove_marketplace('m', cfgdir='acct-two'),
        lambda: plugins.update_marketplaces('m', cfgdir='acct-two'),
        lambda: plugins.install_plugin('p', 'm', cfgdir='acct-two'),
        lambda: plugins.remove_plugin('p@m', cfgdir='acct-two'),
        lambda: plugins.update_plugin('p@m', cfgdir='acct-two'),
    ]
    for mutate in mutations:
        assert mutate() == (True, 'ok')
    assert cli.env_for == ['acct-two'] * len(mutations)
    assert all(r.kw['env'] == {'CLAUDE_CONFIG_DIR': 'acct-two'} for r in cli.runs)
    assert all('shell' not in r.kw for r in cli.runs)
