"""More than one login per CLI, not only per Claude account.

A home is what carries a login for all three of these CLIs — `CLAUDE_CONFIG_DIR`,
`CODEX_HOME`, `PI_CODING_AGENT_DIR` — and `config.account_env` has always
written whichever one the descriptor names. What was missing was anywhere to
say there is a second of them.

The tests below are aimed at the two mutations that would quietly undo it: a
seam that goes back to `home_dir(hid)` and so only ever sees the built-in home,
and `settings['homes']` growing a `'claude'` key, which is the thing that would
make a Codex home reachable from `all_config_dirs()` and therefore from every
Claude-shaped writer in the codebase.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox
from claude_sessions import config as _c
from claude_sessions import harnesses as _h


def _two_codex_homes(monkeypatch, tmp_path, extra='work'):
    """A second CODEX_HOME, registered the way the Accounts page registers one."""
    sb = Sandbox(monkeypatch, tmp_path)
    second = tmp_path / ('codex-' + extra)
    second.mkdir()
    s = _c.load_settings()
    s['homes'] = {'codex': [{'name': extra, 'dir': str(second)}]}
    _c.save_settings(s)
    # `exe()` walks exe_globs under the sandbox's _USERPROFILE, so give it one
    binroot = tmp_path / 'home' / '.local' / 'bin'
    binroot.mkdir(parents=True, exist_ok=True)
    (binroot / 'codex.exe').write_text('', encoding='utf-8')
    monkeypatch.setattr(_c, '_USERPROFILE', str(tmp_path / 'home'))
    return sb, str(second)


def test_a_second_home_is_listed_after_the_built_in_one(monkeypatch, tmp_path):
    _sb, second = _two_codex_homes(monkeypatch, tmp_path)
    rows = _h.homes('codex')
    assert [n for n, _d in rows] == ['Codex', 'work']
    assert rows[0][1] == _h.home_dir('codex'), 'the built-in home comes first'
    assert rows[1][1] == second


def test_the_built_in_home_is_named_after_the_cli(monkeypatch, tmp_path):
    """Not 'default'. It is what keeps a single-home machine looking unchanged:
    the sessions list and the project rows print this string as the account."""
    Sandbox(monkeypatch, tmp_path)
    assert _h.homes('codex')[0][0] == 'Codex'
    assert _h.homes('pi')[0][0] == 'pi'


def test_a_home_named_twice_is_one_home(monkeypatch, tmp_path):
    """Same dedup rule as the accounts list, because it is the same function."""
    Sandbox(monkeypatch, tmp_path)
    s = _c.load_settings()
    s['homes'] = {'codex': [{'name': 'again', 'dir': _h.home_dir('codex')},
                            {'name': 'again too', 'dir': _h.home_dir('codex').upper()}]}
    _c.save_settings(s)
    assert len(_h.homes('codex')) == 1


def test_claude_homes_still_come_from_the_accounts_list(monkeypatch, tmp_path):
    """`homes('claude')` must route through `config.all_config_dirs` rather than
    read `settings['homes']`: nine tests and the whole sandbox redirect accounts
    by patching that function, and a second reader would walk past them."""
    Sandbox(monkeypatch, tmp_path)
    monkeypatch.setattr(_c, 'all_config_dirs',
                        lambda: [('patched', str(tmp_path / 'patched'))])
    assert _h.homes('claude') == [('patched', str(tmp_path / 'patched'))]


def test_the_harness_homes_key_never_holds_claude(monkeypatch, tmp_path):
    """The whole argument for two keys. `all_config_dirs()` has ~35 callers and
    every one means a Claude login — if a Codex home could arrive through it,
    `provision.apply`, the OAuth poller and every hooks writer would take it."""
    _two_codex_homes(monkeypatch, tmp_path)
    assert 'claude' not in (_c.load_settings().get('homes') or {})
    dirs = [d for _n, d in _c.all_config_dirs()]
    assert not any('codex' in d.lower() for d in dirs), dirs


def test_every_seam_that_walks_homes_sees_the_second_one(monkeypatch, tmp_path):
    """`instances()` is the payoff: four consumers fan out with no edit."""
    _sb, second = _two_codex_homes(monkeypatch, tmp_path)
    rows = [(n, d) for n, d, hid in _h.instances() if hid == 'codex']
    assert [n for n, _d in rows] == ['Codex', 'work']
    assert second in [d for _n, d in rows]
    assert second in [d for hid, d in _h._homes() if hid == 'codex']
    # a skill you wrote is a property of YOU, so it installs into both
    assert os.path.join(second, 'skills') in [d for _n, d in _h.skill_roots()]


def test_a_disabled_harness_contributes_no_homes(monkeypatch, tmp_path):
    _two_codex_homes(monkeypatch, tmp_path)
    s = _c.load_settings()
    s['harnesses_disabled'] = ['codex']
    _c.save_settings(s)
    assert not [r for r in _h.instances() if r[2] == 'codex']


def test_a_transcript_under_a_second_home_is_still_that_cli(monkeypatch, tmp_path):
    """`of_path` compared only the BUILT-IN home, so a rollout under a second
    CODEX_HOME was placed as Claude Code's — which gets its transcript path and
    its token fold both wrong while looking like it worked."""
    _sb, second = _two_codex_homes(monkeypatch, tmp_path)
    roll = os.path.join(second, 'sessions', '2026', '09', '15', 'rollout-x.jsonl')
    assert _h.of_path(roll)['id'] == 'codex'
    assert _h.of_path(os.path.join(_h.home_dir('codex'), 'sessions', 'a.jsonl'))['id'] == 'codex'
    # and anything unplaceable is still Claude Code, which is the fallback the
    # function is allowed to assume
    assert _h.of_path(str(tmp_path / 'nowhere' / 'x.jsonl'))['id'] == 'claude'


def test_more_than_one_login_is_no_longer_a_declared_gap(monkeypatch, tmp_path):
    """The reason text said Codex keeps one login per CODEX_HOME. It still
    does — there can simply be more than one CODEX_HOME now."""
    Sandbox(monkeypatch, tmp_path)
    for hid in _h.ids():
        assert _h.cap(hid, 'accounts')[0] is True, hid
    assert 'accounts' in _h.CAPS, 'the key stays: the NAV row still gates on it'
