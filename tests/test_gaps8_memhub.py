"""T-1335 — per-project memory toggles in claude_sessions/memhub.py, lines 227-294.

Selected branches (highest risk first):
  1. :233-236  disabling the prompt hook saves the flag off and never fans out to accounts
  2. :234-235  enabling the prompt hook installs memory_hook across accounts exactly once
  3. :258      set_memory_rules on without a project path does not call sync_rules
  4. :260-261  sync_rules receives the supplied mem; mem None loads memory first
  5. :246-248  enabling worklog installs its hook; disabling does not
  6. :265-268  _toggle_hook flips from st['hook_on'] and flashes ok equal to the new state
  7. :291-292  a missing worklog flag reads as False, so the first toggle enables it
  8. :232, :244, :276  flags land under project_defaults[enc] and other encodings are preserved
  9. :232-235  PREMISE, strict xfail: a failing install leaves the flag saved as on (no rollback)
 10. :232     PREMISE, strict xfail: the string 'false' passed as on is stored as True through bool()

Seams: config.load_settings/save_settings act on an in-memory dict, hooks.across_accounts is a
recorder, hooks.install_* are sentinels, memrules.sync_rules and memory.load_memory are fakes.
No settings file, no account home and no subprocess is touched.
"""

import copy
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import config, hooks, memhub, memory, memrules


@pytest.fixture
def env(monkeypatch):
    state = {'s': {}}
    calls = []
    sync_calls = []
    flashes = []

    def install_memory_hook(cfgdir=None):
        return 'memory'

    def install_worklog_hook(cfgdir=None):
        return 'worklog'

    def fan_out(fn, *args, **kw):
        calls.append(fn)
        return {}

    monkeypatch.setattr(config, 'load_settings', lambda: copy.deepcopy(state['s']))
    monkeypatch.setattr(config, 'save_settings',
                        lambda s: state.__setitem__('s', copy.deepcopy(s)))
    monkeypatch.setattr(hooks, 'install_memory_hook', install_memory_hook)
    monkeypatch.setattr(hooks, 'install_worklog_hook', install_worklog_hook)
    monkeypatch.setattr(hooks, 'across_accounts', fan_out)
    monkeypatch.setattr(memrules, 'sync_rules',
                        lambda *a: sync_calls.append(a))
    monkeypatch.setattr(memory, 'load_memory', lambda project, folder: 'LOADED')

    def flash(msg, ok=None, secs=None):
        flashes.append(SimpleNamespace(msg=msg, ok=ok))

    return SimpleNamespace(state=state, calls=calls, sync_calls=sync_calls, flashes=flashes,
                           flash=flash, install_memory=install_memory_hook,
                           install_worklog=install_worklog_hook)


def _proj(env, enc='enc'):
    return env.state['s'].get('project_defaults', {}).get(enc, {})


def test_disabling_the_prompt_hook_saves_off_and_never_fans_out(env):
    memhub.set_prompt_hook('enc', True)
    env.calls.clear()
    assert memhub.set_prompt_hook('enc', False) is False
    assert _proj(env)['memory_hook'] is False
    assert env.calls == []


def test_enabling_the_prompt_hook_installs_across_accounts_exactly_once(env):
    assert memhub.set_prompt_hook('enc', True) is True
    assert env.calls == [env.install_memory]


def test_memory_rules_on_without_project_path_does_not_sync(env):
    assert memhub.set_memory_rules(True, None, 'folder') is True
    assert env.state['s']['memory_rules'] is True
    assert env.sync_calls == []


def test_sync_rules_receives_the_supplied_mem(env):
    memhub.set_memory_rules(True, 'P', 'F', mem='MEM')
    assert env.sync_calls == [('P', 'F', 'MEM')]


def test_sync_rules_loads_memory_first_when_mem_is_none(env):
    memhub.set_memory_rules(True, 'P', 'F')
    assert env.sync_calls == [('P', 'F', 'LOADED')]


def test_worklog_enable_installs_its_hook_and_disable_does_not(env):
    memhub.set_worklog('enc', True)
    assert env.calls == [env.install_worklog]
    env.calls.clear()
    memhub.set_worklog('enc', False)
    assert env.calls == []
    assert _proj(env)['worklog'] is False


def test_toggle_hook_flips_from_state_and_flashes_the_new_state(env):
    st_off = {'enc': 'enc', 'hook_on': False}
    memhub._toggle_hook('P', st_off, env.flash)
    assert _proj(env)['memory_hook'] is True
    assert env.flashes[-1].ok is True and 'ENABLED' in env.flashes[-1].msg
    st_on = {'enc': 'enc', 'hook_on': True}
    memhub._toggle_hook('P', st_on, env.flash)
    assert _proj(env)['memory_hook'] is False
    assert env.flashes[-1].ok is False and 'disabled' in env.flashes[-1].msg


def test_a_missing_worklog_flag_reads_as_off_so_the_first_toggle_enables(env):
    memhub._toggle_worklog('P', {'enc': 'enc'}, env.flash)
    assert _proj(env)['worklog'] is True
    assert env.calls == [env.install_worklog]
    assert env.flashes[-1].ok is True


def test_flags_land_under_their_encoding_and_other_encodings_survive(env):
    env.state['s'] = {'project_defaults': {'other': {'memory_hook': True, 'worklog': True}}}
    memhub.set_prompt_hook('enc', True)
    memhub.set_worklog('enc', False)
    memhub.set_auto_memory('enc', True)
    assert env.state['s']['project_defaults']['other'] == {'memory_hook': True, 'worklog': True}
    assert _proj(env) == {'memory_hook': True, 'worklog': False, 'auto_memory': True}


def test_failed_install_does_not_leave_the_flag_on(env, monkeypatch):
    def failing(fn, *args, **kw):
        raise RuntimeError('install failed')
    monkeypatch.setattr(hooks, 'across_accounts', failing)
    try:
        memhub.set_prompt_hook('enc', True)
    except RuntimeError:
        pass
    assert _proj(env).get('memory_hook') is not True


def test_string_false_is_refused_and_nothing_is_saved(env):
    with pytest.raises(ValueError):
        memhub.set_prompt_hook('enc', 'false')
    assert env.state['s'] == {}
    assert env.calls == []


@pytest.mark.parametrize('value', ['false', 1, None])
def test_set_worklog_refuses_a_non_bool_and_saves_nothing(value, monkeypatch):
    saved, installed = [], []
    monkeypatch.setattr(config, 'load_settings', lambda: {})
    monkeypatch.setattr(config, 'save_settings', saved.append)
    monkeypatch.setattr(hooks, 'across_accounts', installed.append)
    with pytest.raises(ValueError):
        memhub.set_worklog('enc', value)
    assert saved == [] and installed == []


def test_set_worklog_leaves_the_flag_off_when_the_install_fails(monkeypatch):
    saved = []
    monkeypatch.setattr(config, 'load_settings', lambda: {})
    monkeypatch.setattr(config, 'save_settings', saved.append)

    def boom(fn):
        raise OSError('install failed')

    monkeypatch.setattr(hooks, 'across_accounts', boom)
    with pytest.raises(OSError):
        memhub.set_worklog('enc', True)
    assert saved == []
