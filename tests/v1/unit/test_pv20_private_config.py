"""T-024 (ADR-0053 A2, T-017 C1 and its correction): an isolated execution's
CLAUDE_CONFIG_DIR, TEMP and TMP are Core-created directories under its own
`own/state`, kept for a resume of the same execution and never replaced by the
account home. Fake launch only: no process, no provider, no Windows boundary.

What these tests do NOT show: what the rest of the inherited environment names,
runtime staging, the broker or login, materialised opt-ins, or what the real CLI
does with these directories."""

import dataclasses
import os
import shutil
from types import SimpleNamespace

import pytest

from archeus.core.domain import ids
from archeus.harnesses import base
from archeus.harnesses.claude_code import adapter as cc


class FakeIsolation:
    """Rides on the spec like IsolationContext; records each launch and what was on
    disk at that moment."""

    def __init__(self):
        self.launches = []

    def launch(self, argv, *, cwd, env, paths):
        self.launches.append({'env': dict(env),
                              'config_dir': os.path.isdir(paths.config),
                              'tmp_dir': os.path.isdir(paths.tmp),
                              'config_files': sorted(os.listdir(paths.config))
                              if os.path.isdir(paths.config) else None})
        return SimpleNamespace(pid=424242), None


@pytest.fixture(autouse=True)
def _no_real_process(monkeypatch):
    def boom(*a, **k):
        raise AssertionError('a real process launch was reached')
    monkeypatch.setattr(base.proc, 'spawn_detached', boom)
    monkeypatch.setattr(base.proc, 'process_create_time', lambda pid: 1.0)


def _spec(tmp_path, isolation=None, **kw):
    home = tmp_path / 'account-home'
    home.mkdir(exist_ok=True)
    return base.ExecutionSpec(execution_id=ids.new_id('execution'), prompt='go',
                              workdir=str(tmp_path), isolation=isolation,
                              account=base.AccountRef('claude-code:test', str(home)), **kw)


def _inside(path, root):
    p, r = (os.path.normcase(os.path.realpath(x)) for x in (path, root))
    return p == r or p.startswith(r.rstrip(os.sep) + os.sep)


def _start_then_end(tmp_path):
    iso = FakeIsolation()
    spec = _spec(tmp_path, iso)
    cc.ClaudeCodeAdapter(exe='claude').start(spec)
    paths = base.ExecPaths(spec.execution_id)
    base.mark_ended(paths, 0)
    return iso, spec, paths


def _resume(spec):
    nxt = dataclasses.replace(spec, process_seq=2)
    return cc.ClaudeCodeAdapter(exe='claude').resume(nxt, {'session': 'sess-1'})


def test_a_first_isolated_process_gets_new_empty_private_dirs(tmp_path):
    iso, spec, paths = _start_then_end(tmp_path)
    (seen,) = iso.launches
    assert seen['config_dir'] and seen['tmp_dir'] and seen['config_files'] == []
    assert seen['env']['CLAUDE_CONFIG_DIR'] == paths.config
    assert seen['env']['TEMP'] == seen['env']['TMP'] == paths.tmp
    assert os.path.dirname(paths.config) == os.path.dirname(paths.tmp) == paths.state


def test_an_isolated_claude_config_dir_is_never_the_account_home_or_inside_it(tmp_path):
    iso, spec, paths = _start_then_end(tmp_path)
    assert not _inside(iso.launches[0]['env']['CLAUDE_CONFIG_DIR'], spec.account.home_ref)


def test_a_resume_reuses_the_private_dirs_and_keeps_their_content(tmp_path):
    iso, spec, paths = _start_then_end(tmp_path)
    with open(os.path.join(paths.config, 'session.jsonl'), 'w', encoding='utf-8') as f:
        f.write('{}')
    _resume(spec)
    first, second = iso.launches
    assert second['config_files'] == ['session.jsonl']
    assert second['env']['CLAUDE_CONFIG_DIR'] == first['env']['CLAUDE_CONFIG_DIR']


@pytest.mark.parametrize('damage', ['missing', 'a file'])
def test_a_resume_without_its_private_config_launches_nothing(tmp_path, damage):
    iso, spec, paths = _start_then_end(tmp_path)
    shutil.rmtree(paths.config)
    if damage == 'a file':
        with open(paths.config, 'w', encoding='utf-8') as f:
            f.write('not a directory')
    with pytest.raises(base.SpawnFailed):
        _resume(spec)
    assert len(iso.launches) == 1                      # the first process only
    assert os.path.isdir(paths.config) is False        # never re-created empty
    assert 'private config' in (base.read_json(paths.ended) or {}).get('error', '')


def test_a_tombstone_that_cannot_be_written_still_refuses_with_both_reasons(tmp_path,
                                                                           monkeypatch):
    iso, spec, paths = _start_then_end(tmp_path)
    shutil.rmtree(paths.config)

    def tombstone_fails(*a, **k):
        raise OSError('disk full')
    monkeypatch.setattr(base, 'mark_ended', tombstone_fails)
    with pytest.raises(base.SpawnFailed) as got:
        _resume(spec)
    assert 'private config' in str(got.value) and 'disk full' in str(got.value)
    assert 'private config' in str(got.value.__cause__)
    assert len(iso.launches) == 1


def test_an_isolated_launch_drops_the_provider_keys(tmp_path, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-test')
    monkeypatch.setenv('ANTHROPIC_AUTH_TOKEN', 'tok-test')
    iso, spec, paths = _start_then_end(tmp_path)
    env = iso.launches[0]['env']
    assert 'ANTHROPIC_API_KEY' not in env and 'ANTHROPIC_AUTH_TOKEN' not in env


def test_an_unisolated_launch_is_unchanged(tmp_path, monkeypatch):
    seen = {}

    def detached(argv, *, cwd, env, **kw):
        seen.update(argv=argv, env=dict(env))
        return SimpleNamespace(pid=424242), None

    monkeypatch.setattr(base.proc, 'spawn_detached', detached)
    monkeypatch.setenv('TEMP', str(tmp_path / 'core-temp'))
    monkeypatch.setenv('TMP', str(tmp_path / 'core-tmp'))
    spec = _spec(tmp_path)
    cc.ClaudeCodeAdapter(exe='claude').start(spec)
    paths = base.ExecPaths(spec.execution_id)
    assert seen['env']['CLAUDE_CONFIG_DIR'] == spec.account.home_ref
    assert seen['env']['TEMP'] == str(tmp_path / 'core-temp')
    assert seen['env']['TMP'] == str(tmp_path / 'core-tmp')
    assert not os.path.exists(paths.state)
