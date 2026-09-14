"""The harness registry: which agent CLI a config dir belongs to, and what that
CLI can do.

Only Claude Code is registered at this stage, on purpose — the mechanism ships
before the thing that needs it, so the harnesses that follow cannot be tempted
to special-case their way past it. Every gate here is written to hold for a
registry of three.
"""
import os

import pytest

from claude_sessions import config as c
from claude_sessions import harnesses, quota


# ── the capability table ─────────────────────────────────────

def test_no_descriptor_claims_a_capability_that_does_not_exist():
    """A key that is not in CAPS reads as "supported", because cap() answers
    (True, '') for anything unlisted. A typo would therefore turn a surface OFF
    silently — the one failure this whole mechanism exists to prevent."""
    for hid, d in harnesses.HARNESSES.items():
        unknown = set(d['caps']) - set(harnesses.CAPS)
        assert not unknown, '%s declares unknown capabilities: %s' % (hid, unknown)


def test_a_capability_that_is_off_says_why():
    """(ok, why), never a bare bool: the contract is "hidden with a stated
    reason", and a bare False leaves the UI nothing to print."""
    for hid, d in harnesses.HARNESSES.items():
        for key, val in d['caps'].items():
            assert isinstance(val, tuple) and len(val) == 2, '%s/%s' % (hid, key)
            ok, why = val
            if not ok:
                assert why.strip(), '%s/%s is off with no reason' % (hid, key)


def test_an_unlisted_capability_is_supported():
    """A descriptor lists what it CANNOT do. Claude Code lists nothing, so
    nothing about it may read as missing."""
    for key in harnesses.CAPS:
        assert harnesses.cap('claude', key) == (True, '')


def test_asking_about_a_capability_that_does_not_exist_is_an_error():
    """Not False. A misspelt key at a call site must not quietly disable a
    page."""
    with pytest.raises(KeyError):
        harnesses.cap('claude', 'wishful_thinking')


# ── placing a config dir ─────────────────────────────────────

def test_a_claude_account_is_placed_by_its_directory(monkeypatch, tmp_path):
    from harness import Sandbox
    sb = Sandbox(monkeypatch, tmp_path)
    assert harnesses.of(str(sb.cfg))['id'] == 'claude'


def test_an_unplaceable_directory_is_claude_code():
    """Every home that exists today is Claude Code's, and a harness id read out
    of settings written by a newer version must not blank the UI."""
    assert harnesses.of('C:/nowhere/at/all')['id'] == 'claude'
    assert harnesses.descriptor('not-a-harness')['id'] == 'claude'


def test_the_home_directory_is_resolved_at_call_time(monkeypatch, tmp_path):
    """A module-level absolute path is a cache with no invalidation — the bug
    this codebase has now paid for three times. It would bind to whatever the
    user profile was when the module happened to be imported."""
    monkeypatch.setattr(c, '_USERPROFILE', str(tmp_path))
    assert harnesses.home_dir('claude') == os.path.join(str(tmp_path), '.claude')


# ── the binary ───────────────────────────────────────────────

def test_the_binary_is_resolved_every_time(monkeypatch, tmp_path):
    """Codex installs under a hashed directory that changes on every update, so
    a stored absolute path goes stale in silence. Nothing here may cache."""
    from harness import Sandbox
    Sandbox(monkeypatch, tmp_path)
    fake = tmp_path / 'claude.exe'
    fake.write_text('', encoding='utf-8')
    s = c.load_settings()
    s['claude_exe'] = str(fake)
    c.save_settings(s)
    assert harnesses.exe('claude') == str(fake)
    fake.unlink()
    assert harnesses.exe('claude') != str(fake)     # falls through, never stale


def test_there_is_still_exactly_one_binary_resolver():
    """Thirty-five callers spell it `get_claude_exe` and all of them mean Claude
    Code, so the name is the compatibility surface and stays. What must not come
    back is a SECOND resolution: the wrapper may not look at PATH, the install
    path or the setting itself, or the two answers can disagree about which
    binary is running."""
    src = _unstubbed_get_claude_exe()
    assert 'shutil.which' not in src and "'.local'" not in src
    assert "exe('claude')" in src


def _unstubbed_get_claude_exe():
    """The suite stubs config.get_claude_exe everywhere, so read the definition
    out of the module source rather than off the (replaced) attribute."""
    import ast
    import io as _io
    import os as _os
    path = _os.path.join(_os.path.dirname(_os.path.abspath(c.__file__)),
                         'config.py')
    src = _io.open(path, encoding='utf-8').read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef) and node.name == 'get_claude_exe':
            return ast.get_source_segment(src, node)
    raise AssertionError('get_claude_exe is gone')


# ── the environment that picks one home ──────────────────────

def test_the_home_variable_follows_the_harness(monkeypatch, tmp_path):
    from harness import Sandbox
    sb = Sandbox(monkeypatch, tmp_path)
    env = c.account_env(str(sb.cfg))
    assert env['CLAUDE_CONFIG_DIR'] == str(sb.cfg)


def test_a_key_in_the_environment_is_still_dropped(monkeypatch, tmp_path):
    """It shadows the account login, so the CLI would authenticate as the key's
    owner whatever home it was pointed at. The descriptor says so now."""
    from harness import Sandbox
    sb = Sandbox(monkeypatch, tmp_path)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-whatever')
    assert 'ANTHROPIC_API_KEY' not in c.account_env(str(sb.cfg))


# ── which calls spend quota ──────────────────────────────────

def test_a_print_call_is_inference():
    assert quota.is_inference(['C:/x/claude.exe', '-p', 'hello'])
    assert quota.is_inference(['claude', '--print', 'hello'])


def test_a_management_subcommand_is_not():
    for argv in (['claude', 'mcp', 'list'],
                 ['claude', 'plugin', 'marketplace', 'list'],
                 ['claude', '--version']):
        assert not quota.is_inference(argv)


def test_something_that_is_not_a_harness_at_all_is_not_inference():
    assert not quota.is_inference(['git', '-p', 'log'])
    assert not quota.is_inference([])
    assert not quota.is_inference(['python', '-m', 'claude_sessions', 'statusline'])


def test_the_shape_of_an_inference_call_is_the_harness_s_to_declare():
    """The sniff was never the problem; hardcoding one harness's shape here
    was. Codex's headless mode is a SUBCOMMAND, so a flag-only test answers
    False for every one of its calls and the account-quota guard silently stops
    applying."""
    for d in harnesses.HARNESSES.values():
        assert 'inference_flags' in d and 'inference_verbs' in d
