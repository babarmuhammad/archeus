"""T-1308: the highest-risk uncovered branches of archeus claude_sessions/harnesses.py
lines 788-815 inclusive (tip 51f4af3f, `of_argv`), and the two callers that read
its answer for the quota gate (`quota._cfgdir_of`, `quota.note_failure`,
`quota.preflight`), which the card treats as read-only context.

The ten selected branches, denial and fail-closed first, then boundaries, then
error paths:

 1. harnesses.py:809-810  every accepted suffix (bare, .com, .exe, .bat, .cmd,
                          .ps1) names the exact harness stem
 2. harnesses.py:805      mixed-case basename and suffix are recognised, and the
                          caller's argv is not rewritten
 3. harnesses.py:805      backslash, slash and mixed separators resolve the same
 4. harnesses.py:812-815  claude-helper / codexevil / piano do not match prefixes
 5. harnesses.py:810      .exe.old refuses; a quoted executable token is not
                          silently unquoted
 6. harnesses.py:806-807  empty list, None and a mapping without index zero
                          return None without an exception
 7. harnesses.py:805      an empty or None first token returns None, no default
 8. harnesses.py:805      a list or object rendered as text never names a harness
 9. quota.py:_cfgdir_of   a Codex or pi shim reads its own home variable, never
                          the ambient CLAUDE_CONFIG_DIR
10. quota.py:preflight    a prefix-only unknown launcher neither charges nor
                          rotates Claude; the exact Claude shim still takes the
                          inference gate

Every probe is a fake: no subprocess, no network, no user home, no credential
file, no real environment value. The quota gate is driven through its own
module-level seams (`reason`, `_ask`, `_report`, `note_limit`, the decision
caches), each replaced on the `quota` module before the call.
"""
import os

import pytest

from claude_sessions import harnesses as _h
from claude_sessions import quota as _q


_STEMS = {'claude': 'claude', 'codex': 'codex', 'pi': 'pi'}
_SUFFIXES = ('', '.com', '.exe', '.bat', '.cmd', '.ps1')


@pytest.mark.parametrize('hid', sorted(_STEMS))
@pytest.mark.parametrize('suffix', _SUFFIXES)
def test_every_accepted_suffix_names_the_exact_harness_stem(hid, suffix):
    """Branch: harnesses.py:809-810 and 814-815. Removing a suffix from the
    allow-list, or comparing against the wrong stem, drops the inference gate
    for that spelling of the binary."""
    d = _h.of_argv([_STEMS[hid] + suffix, '-p', 'hi'])
    assert d is not None and d['id'] == hid


def test_mixed_case_name_and_suffix_are_recognised_and_argv_is_not_rewritten():
    """Branch: harnesses.py:805 `.lower()` on the basename, and 809 on the
    suffix. The caller's list must come back unchanged: the gate reads it
    again after this call."""
    args = ['Claude.EXE', '-p', 'hi']
    d = _h.of_argv(args)
    assert d is not None and d['id'] == 'claude'
    assert args == ['Claude.EXE', '-p', 'hi']


@pytest.mark.parametrize('first, hid', [
    ('C:\\Users\\dev\\AppData\\claude.exe', 'claude'),
    ('C:/Users/dev/AppData/claude.exe', 'claude'),
    ('C:\\tools/npm\\codex.cmd', 'codex'),
    ('/usr/local/bin/pi', 'pi'),
    ('D:/a\\b/c\\pi.cmd', 'pi'),
])
def test_windows_and_posix_paths_with_mixed_separators_resolve_the_same(first, hid):
    """Branch: harnesses.py:805 `.replace('\\\\', '/')` and the last-segment
    split. Dropping the replace makes a Windows path one long basename on Linux
    and matches no harness."""
    d = _h.of_argv([first, 'exec'])
    assert d is not None and d['id'] == hid


@pytest.mark.parametrize('first', [
    'claude-helper', 'claude-helper.exe', 'codexevil', 'codexevil.cmd',
    'piano', 'piano.ps1', 'pi-tool.exe', 'claude.exe-helper',
])
def test_a_prefix_or_lookalike_name_never_matches_a_harness(first):
    """Branch: harnesses.py:812-815. The stem is compared for equality, never as
    a prefix, so a recognised suffix cannot turn `piano` into `pi`."""
    assert _h.of_argv([first, '-p', 'hi']) is None


@pytest.mark.parametrize('first', [
    'claude.exe.old', 'codex.exe.bak', 'pi.cmd.tmp', '"claude"', '"claude.exe"',
    "'claude.exe'", 'claude.sh', 'claude.exe ',
])
def test_an_unknown_or_doubled_suffix_refuses_and_quotes_are_not_removed(first):
    """Branch: harnesses.py:809-811. Only one known suffix is recognised, and a
    quoted token is a different string: stripping quotes here would name a
    binary the shell never resolved."""
    assert _h.of_argv([first, '-p']) is None


@pytest.mark.parametrize('args', [[], None, {}, {'x': 'claude'}])
def test_empty_none_and_mapping_without_index_zero_answer_none(args):
    """Branch: harnesses.py:806-807. The IndexError, TypeError and KeyError
    handler returns None and does not fall through to the suffix test."""
    assert _h.of_argv(args) is None


@pytest.mark.parametrize('args', [[''], [None], ['', '-p'], [' ']])
def test_an_empty_first_token_names_no_harness_and_is_not_claude_by_default(args):
    """Branch: harnesses.py:805 and 814. An empty token has stem '' and must not
    equal any harness stem; there is no default-to-Claude guess."""
    assert _h.of_argv(args) is None


@pytest.mark.parametrize('first', [
    ['claude'], ['claude.exe'], {'exe': 'claude'}, ('codex', 'exec'),
    "['claude']", 42,
])
def test_a_container_or_number_rendered_as_text_never_names_a_harness(first):
    """Branch: harnesses.py:805. `str()` of a list, mapping, tuple or number is
    bracketed, dotted or numeric text: none of it may equal a harness stem. The
    supported shape is a sequence whose first element is the bare string."""
    assert _h.of_argv([first, '-p']) is None


def test_codex_shim_reads_its_own_home_variable_not_the_ambient_claude_one():
    """Branch: quota.py:_cfgdir_of via harnesses.py:805. The env carries a Claude
    home that must not be used for a Codex or pi call."""
    codex_env = _h.descriptor('codex')['home_env']
    pi_env = _h.descriptor('pi')['home_env']
    env = {
        'CLAUDE_CONFIG_DIR': os.path.join('synthetic', 'claude-home'),
        codex_env: os.path.join('synthetic', 'codex-home'),
        pi_env: os.path.join('synthetic', 'pi-home'),
    }
    assert _q._cfgdir_of(['codex.cmd', 'exec', 'x'], env) == env[codex_env]
    assert _q._cfgdir_of(['pi', '-p', 'x'], env) == env[pi_env]
    assert _q._cfgdir_of(['codex.cmd', 'exec'], {'CLAUDE_CONFIG_DIR': env['CLAUDE_CONFIG_DIR']}) is None


@pytest.fixture
def quota_gate(monkeypatch):
    """Fresh decision caches, and every side effect of the gate recorded."""
    monkeypatch.setattr(_q, '_decided', {})
    monkeypatch.setattr(_q, '_observed', {})
    monkeypatch.setattr(_q, '_window_observed', {})
    calls = {'reason': [], 'ask': [], 'report': [], 'note': []}

    def reason(cfgdir=None):
        calls['reason'].append(cfgdir)
        return 'synthetic limit'

    def ask(why, alts, mode):
        calls['ask'].append((why, mode))
        return None

    monkeypatch.setattr(_q, 'reason', reason)
    monkeypatch.setattr(_q, 'headroom', lambda exclude=None: [])
    monkeypatch.setattr(_q, '_ask', ask)
    monkeypatch.setattr(_q, '_report', lambda why: calls['report'].append(why))
    monkeypatch.setattr(_q._c, 'load_settings', lambda: {'headless_quota': 'prompt'})
    monkeypatch.setattr(_q, 'note_limit',
                        lambda cfgdir=None, window=True, ttl=None: calls['note'].append(cfgdir))
    monkeypatch.setattr(_q, '_note_rotation', lambda *a: calls.setdefault('rot', []).append(a))
    return calls


def test_a_prefix_only_launcher_is_never_gated_as_claude(quota_gate):
    """Branch: harnesses.py:812 through quota.py preflight (`is_inference`
    False). An unknown launcher must not reach the Claude account reader, the
    quota prompt or a rotation."""
    env = {'CLAUDE_CONFIG_DIR': os.path.join('synthetic', 'claude-home')}
    out_env, why = _q.preflight(['claude-helper', '-p', 'hi'], env)
    assert (out_env, why) == (env, '')
    assert quota_gate['reason'] == []
    assert quota_gate['ask'] == [] and quota_gate['report'] == []
    assert 'rot' not in quota_gate and quota_gate['note'] == []


@pytest.mark.xfail(strict=True, reason=(
    "quota.py:386-396 note_failure: of_argv() None (unknown launcher) falls "
    "through to note_limit(), so a prefix-only launcher's limit text charges "
    "the default Claude account; preflight at quota.py:457-460 treats the same "
    "argv as not a Claude call"))
def test_a_prefix_only_limit_text_charges_no_claude_account(quota_gate, monkeypatch):
    """Branch: harnesses.py:812 (no match) read by quota.py:398-400 through
    note_failure. A limit text from `claude-helper` must not latch the account
    that the env names."""
    monkeypatch.setattr(_q, 'is_limit_error', lambda text: True)
    env = {'CLAUDE_CONFIG_DIR': os.path.join('synthetic', 'claude-home')}
    _q.note_failure(['claude-helper', '-p', 'hi'], env, 'x')
    assert quota_gate['note'] == []


def test_the_exact_claude_shim_still_takes_the_inference_gate(quota_gate):
    """Control for harnesses.py:815 through quota.preflight: `claude.cmd -p` is
    the same call as `claude -p`, so the gate asks, and a blocked answer keeps
    the env untouched and reports the reason."""
    cfg = os.path.join('synthetic', 'claude-home')
    env = {'CLAUDE_CONFIG_DIR': cfg}
    out_env, why = _q.preflight(['claude.cmd', '-p', 'hi'], env)
    assert why == 'synthetic limit'
    assert out_env is env
    assert quota_gate['reason'][0] == cfg
    assert quota_gate['report'] == ['synthetic limit']


def test_the_exact_claude_shim_failure_is_charged_to_its_own_account(quota_gate, monkeypatch):
    """Control for quota.note_failure: a limit text from the exact Claude shim is
    recorded against the home the env names, once."""
    monkeypatch.setattr(_q, 'is_limit_error', lambda text: True)
    cfg = os.path.join('synthetic', 'claude-home')
    _q.note_failure(['claude.exe', '-p', 'hi'], {'CLAUDE_CONFIG_DIR': cfg}, 'x')
    assert quota_gate['note'] == [cfg]
