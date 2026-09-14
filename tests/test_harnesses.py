"""The harness registry: which agent CLI a config dir belongs to, and what that
CLI can do.

Every gate here is written to hold for a registry of three: the mechanism
shipped one release before the second harness so that Codex could not
special-case its way past it. What Codex does with it is in `test_codex.py` —
this file stays about the registry itself.
"""
import io
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


# ── what consumes a capability ───────────────────────────────

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _declared_caps():
    """Every capability key named by a surface: the GUI's NAV and TABS tables
    and the terminal menu's MAIN_CAPS."""
    import re
    from claude_sessions.main import MAIN_CAPS
    js = io.open(os.path.join(ROOT, 'claude_sessions', 'web', 'app.js'),
                 encoding='utf-8').read()
    out = set(MAIN_CAPS.values())
    for tbl in ('NAV', 'TABS'):
        a = js.index('const %s=[' % tbl)
        block = js[a:js.index('\n];', a)]
        for row in re.finditer(r"^  \['[a-z]+',.*?,'([a-z_]*)'\],$", block,
                               re.M | re.S):
            if row.group(1):
                out.add(row.group(1))
    return out


def test_every_capability_a_surface_names_actually_exists():
    """An unlisted key reads as supported, so a typo in a page table turns the
    page OFF nowhere and ON everywhere — it would never be noticed."""
    unknown = _declared_caps() - set(harnesses.CAPS)
    assert not unknown, 'no such capability: %s' % sorted(unknown)


def test_a_capability_some_harness_lacks_is_consumed_by_something():
    """A capability nothing reads is a promise nothing keeps: the descriptor
    says the harness cannot do it, and the screen offers it anyway. Only the
    OFF ones are required to have a consumer — the rest are answers waiting for
    a question, which is what a registry of one looks like."""
    declared = _declared_caps()
    orphans = set()
    for hid, d in harnesses.HARNESSES.items():
        for key, (ok, _why) in d['caps'].items():
            if not ok and key not in declared:
                orphans.add('%s/%s' % (hid, key))
    assert not orphans, 'nothing gates these: %s' % sorted(orphans)


def test_both_page_tables_declare_the_field_on_every_row():
    """A ragged table is worse than no table: the missing field reads as '' —
    available — so the one row that forgot is the one that silently works."""
    import re
    js = io.open(os.path.join(ROOT, 'claude_sessions', 'web', 'app.js'),
                 encoding='utf-8').read()
    for tbl, n in (('NAV', 7), ('TABS', 5)):
        a = js.index('const %s=[' % tbl)
        block = js[a:js.index('\n];', a)]
        rows = [r for r in re.finditer(r"^  \['[a-z]+',.*?\],$", block,
                                       re.M | re.S)]
        assert rows, tbl
        for r in rows:
            body = r.group(0).rstrip(',').rstrip(']')
            assert body.rstrip().endswith("'"), '%s: %s' % (tbl, r.group(0)[:40])


# ── the terminal menu dims rather than hides ─────────────────

def _with_fake_harness(monkeypatch, caps):
    """Register a harness whose home is the active account, so `of(None)`
    answers it. Nothing is off with one harness registered, and the behaviour
    under test is what the MENU does with a capability that is."""
    fake = dict(harnesses.HARNESSES['claude'], id='fake', label='Fake CLI',
                caps=caps)
    monkeypatch.setitem(harnesses.HARNESSES, 'fake', fake)
    monkeypatch.setattr(harnesses, 'of', lambda cfgdir=None: fake)
    return fake


def test_a_row_the_cli_cannot_do_is_dimmed_not_removed(monkeypatch, tmp_path):
    from harness import Sandbox
    from claude_sessions import main as m
    Sandbox(monkeypatch, tmp_path)
    _with_fake_harness(monkeypatch, {'mcp': (False, 'Fake CLI has no MCP.')})
    off = m._dim_unavailable('MCP servers', '__mcp__')
    on = m._dim_unavailable('Settings', '__settings__')
    assert off != 'MCP servers' and 'MCP servers' in off   # dimmed, still there
    assert on == 'Settings'


def test_selecting_it_says_why_instead_of_opening_an_empty_screen(
        monkeypatch, tmp_path):
    from harness import Sandbox
    from claude_sessions import main as m
    Sandbox(monkeypatch, tmp_path)
    _with_fake_harness(monkeypatch, {'mcp': (False, 'Fake CLI has no MCP.')})
    ok, why = m._cap_of_row('__mcp__')
    assert not ok and why == 'Fake CLI has no MCP.'
    assert m._cap_of_row('__settings__') == (True, '')


# ── placing a transcript, and folding it ─────────────────────

def test_a_transcript_is_placed_by_the_home_it_sits_under(monkeypatch, tmp_path):
    """A transcript is reached as a PATH far more often than as an account, and
    every one of them sits under a home. Placing the file is what keeps
    `_parse_session` and its five callers from growing a harness parameter."""
    from harness import Sandbox
    sb = Sandbox(monkeypatch, tmp_path)
    p = os.path.join(str(sb.projects), 'X--work-proj', 'abc.jsonl')
    assert harnesses.of_path(p)['id'] == 'claude'
    assert harnesses.of_path(str(tmp_path / 'elsewhere' / 'x.jsonl'))['id'] == 'claude'
    assert harnesses.of_path('')['id'] == 'claude'


def test_the_fold_is_resolved_late():
    """The table names the function rather than holding it: `sessions` imports
    the registry, so pointing at the function directly would be a cycle."""
    fold = harnesses.impl('fold', 'claude')
    assert callable(fold) and fold.__name__ == '_fold_claude'


def test_the_parser_no_longer_knows_what_a_record_looks_like():
    """`_parse_session` owns the cache, the key and the single pass. The field
    names in a record are the HARNESS's — `message.model`, `gitBranch`,
    `isApiErrorMessage`, the `<synthetic>` sentinel — and a Codex rollout
    answers to none of them."""
    import ast
    import inspect
    from claude_sessions import sessions
    src = inspect.getsource(sessions._parse_session)
    # record fields only: `usage_by_model` is the shape of the shared stats
    # dict, which IS the parser's to own
    for field in ('gitBranch', 'isApiErrorMessage',
                  'cache_creation_input_tokens', 'ai-title'):
        assert field not in src, '%s is back in the parser' % field
    # and the fold still reads them, or this test is measuring nothing
    fold_src = inspect.getsource(sessions._fold_claude)
    for field in ('gitBranch', 'isApiErrorMessage', 'ai-title'):
        assert field in fold_src
    assert isinstance(ast.parse(fold_src), ast.Module)


def test_folding_a_claude_record_still_fills_the_same_keys(tmp_path):
    """The extraction is a move, not a rewrite: one record in, the same stats
    dict out."""
    from claude_sessions import sessions
    s = dict(sessions._EMPTY_STATS)
    s['usage_by_model'], s['models'] = {}, []
    sessions._fold_claude({'type': 'assistant', 'gitBranch': 'main',
                           'cwd': 'C:/p', 'timestamp': '2026-01-01T00:00:00Z',
                           'message': {'role': 'assistant', 'model': 'claude-sonnet-5',
                                       'usage': {'input_tokens': 3,
                                                 'output_tokens': 4}}}, s)
    assert s['branch'] == 'main' and s['cwd'] == 'C:/p'
    assert s['models'] == ['claude-sonnet-5']
    assert s['usage_by_model']['claude-sonnet-5']['in'] == 3
    assert s['count'] == 1 and s['first_ts'] is not None
