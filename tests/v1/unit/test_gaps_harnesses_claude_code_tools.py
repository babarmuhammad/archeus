"""T-748: the highest-risk uncovered branches of `archeus/harnesses/claude_code/tools.py`.

The gaps the existing tests of the module leave alone: `test_tool_removal_units.py`
F01-F14 (and the adapter tests that read `T.allowed` through `ClaudeCodeAdapter.argv`)
cover the mapping over every set of classes, the snapshot, the `mcp__*` fallback,
the observed normalisation of `.` `@` `-` `_` and case, the L1 collision and the
conditional `Skill`. What is not reached there is re-opened here in the order the
risk falls: the denial and fail-closed paths first (an inventory item that is not
an excluded user/project `mcp_server` must never reach `--disallowedTools`; a
server name must never smuggle a glob or a comma into the joined flag; a malformed
inventory must raise before any argv exists, never spawn with a weaker deny), then
the boundary values (duplicate and empty names, an explicit `None` where a list was
expected), then the error paths (the `DEFAULT_FLAGS` fallbacks and the `KeyError`s
that refuse the spawn).

Pure functions over dicts: no OS call, no file, no clock, nothing that differs
between Linux and Windows. Style and fixtures follow the module's closest test,
`tests/v1/unit/test_tool_removal_units.py` (its `_flag`, `_inv` and `_mcp`).
"""

import pytest

from archeus.harnesses import sources
from archeus.harnesses.claude_code import tools as T


def _flag(argv, name):
    assert argv.count(name) <= 1, argv
    return argv[argv.index(name) + 1] if name in argv else None


def _inv(servers=(), items=(), skills=False):
    return {'flags': dict(sources.DEFAULT_FLAGS, mcp_servers=list(servers),
                          disable_slash_commands=not skills), 'items': list(items)}


def _mcp(source, name, status='excluded', **kw):
    d = {'source': source, 'type': 'mcp_server', 'name': name, 'status': status}
    d.update(kw)
    return d


# ── denial paths: only an excluded user/project mcp_server is ever named ─────

def test_g01_items_that_are_not_mcp_servers_are_never_denied():
    """tools.py:104 (`i.get('type') == 'mcp_server'`): dropping the filter lets
    an excluded skill or a mistyped item type join `--disallowedTools`, denying
    a name Claude Code reads as an MCP server; a missing `type` key must skip
    the item too, not crash before the other filters are read."""
    inv = _inv(servers=[{'owner': 'account', 'name': 'gh'}],
               items=[_mcp('user', 'web'),
                      {'source': 'user', 'type': 'skill', 'name': 'sk', 'status': 'excluded'},
                      {'source': 'user', 'type': 'mcp-server', 'name': 'typo',
                       'status': 'excluded'},
                      {'source': 'user', 'name': 'no_type', 'status': 'excluded'},
                      {'source': 'user', 'type': 'mcp_server', 'name': 'no_status'}])
    assert T.mcp_deny(inv) == ['mcp__web']
    # and an unknown status is not "excluded": the deny stays what it is
    assert T.mcp_deny(inv) == T.mcp_deny(_inv(servers=[{'name': 'gh'}],
                                               items=[_mcp('user', 'web')]))


def test_g02_only_user_and_project_scope_is_named():
    """tools.py:105 (`i.get('source') in ('user', 'project')`): a local-scope or
    ownerless (missing key) excluded server is not named — `--strict-mcp-config`
    keeps it out; widening the filter would name a server whose definition the
    inventory cannot attribute to a file, exactly the L2 case."""
    inv = _inv(servers=[{'owner': 'account', 'name': 'gh'}],
               items=[_mcp('user', 'ok'), _mcp('local', 'local_one'),
                      _mcp('Local', 'local_two'), {'type': 'mcp_server', 'name': 'no_source',
                                                   'status': 'excluded'},
                      _mcp('plugin:up@m', 'upmcp')])
    assert T.mcp_deny(inv) == ['mcp__ok']


# ── fail-closed: a server name cannot smuggle a pattern into the joined flag ─

def test_g03_a_name_cannot_smuggle_a_glob_into_the_deny():
    """tools.py:94 through 103 (`mcp_name` sanitisation): `*` reaching a pattern
    is a deny with CLI glob semantics the inventory never opted into — an
    excluded server named `*` would otherwise deny *every* MCP tool, and one
    named `mcp__*` likewise. Only the nothing-opted-in fallback (tested by F04)
    may ever contain `*`."""
    names = ('*', 'a*', '*b', 'mcp__*', '__*')
    inv = _inv(servers=[{'owner': 'account', 'name': 'gh'}],
               items=[_mcp('user', n) for n in names])
    deny = T.mcp_deny(inv)
    assert deny == sorted(['mcp___', 'mcp_____', 'mcp___b', 'mcp__a_', 'mcp__mcp___'])
    assert not any('*' in p for p in deny)
    assert 'mcp__*' not in _flag(T.tool_argv(('read',), inv), '--disallowedTools').split(',')


def test_g04_a_name_cannot_smuggle_a_comma_or_a_space():
    """tools.py:94 through 115: the patterns are joined with `,` into one argv
    element, and `--tools`/`--disallowedTools` values are comma lists — a `,`
    surviving `mcp_name` would split one server into two patterns, one of them
    not prefixed `mcp__` (a deny against a built-in name no server has)."""
    inv = _inv(servers=[{'owner': 'account', 'name': 'gh'}],
               items=[_mcp('user', 'x,y'), _mcp('user', 'a b'), _mcp('user', 'ok')])
    deny = T.mcp_deny(inv)
    assert deny == ['mcp__a_b', 'mcp__ok', 'mcp__x_y']
    value = _flag(T.tool_argv(('read',), inv), '--disallowedTools')
    assert value == 'mcp__a_b,mcp__ok,mcp__x_y'
    assert [p for p in value.split(',') if not p.startswith('mcp__')] == []


def test_g05_mcp_name_boundaries_beyond_the_observed_characters():
    """tools.py:94: F06 observed `.`, `@`, `-`, `_` and case on 2.1.292; the
    rest of the character classes are unreached — the empty name (pattern
    `mcp__`, which can match no tool), tab/newline/backslash (a deny must stay
    one comma-list token), non-ASCII, and the kept set itself for digits."""
    assert T.mcp_name('') == ''
    assert T.mcp_name('a\nb') == 'a_b' and T.mcp_name('a\tb') == 'a_b'
    assert T.mcp_name('/..\\') == '____'
    assert T.mcp_name('caf\u00e9') == 'caf_'
    assert T.mcp_name('a0A-_') == 'a0A-_'
    # the empty name still produces exactly one, harmless, pattern — not a crash
    inv = _inv(servers=[{'owner': 'account', 'name': 'gh'}], items=[_mcp('user', '')])
    assert T.mcp_deny(inv) == ['mcp__']


# ── boundary values: duplicates, explicit None, empty lists ──────────────────

def test_g06_duplicate_names_collapse_and_the_deny_is_sorted():
    """tools.py:103 (`sorted({... for ...})`): five excluded items whose names
    normalise to four distinct servers must yield four patterns (two spellings
    of one server, `pv.dot`/`pv_dot`, are one deny) in byte order — F06 sorts
    distinct names only; without the set a duplicate pattern ships on the flag.
    Case is kept, so `web` and `Web` stay two servers and two denies."""
    inv = _inv(servers=[{'owner': 'account', 'name': 'gh'}],
               items=[_mcp('user', n) for n in ('pv.dot', 'pv_dot', 'PV_DOT', 'web', 'Web')]
                     + [_mcp('project', 'web')])
    deny = T.mcp_deny(inv)
    assert deny == ['mcp__PV_DOT', 'mcp__Web', 'mcp__pv_dot', 'mcp__web']
    assert list(deny) == sorted(set(deny))


def test_g07_explicit_none_items_with_an_opt_in_denies_nothing_and_adds_no_flag():
    """tools.py:103 (`inv.get('items') or ()`) and tools.py:115 (`if deny else a`):
    an inventory that opted a server in and carries no items at all (key absent
    or explicitly `None`) yields no deny and therefore no `--disallowedTools`
    at all — the strict config, not an empty pattern list, is what keeps the
    rest out; `--tools` must still be there, always."""
    opted = dict(sources.DEFAULT_FLAGS, mcp_servers=[{'owner': 'account', 'name': 'gh'}])
    for items in (None, []):
        a = T.tool_argv(('exec', 'web'), {'flags': opted, 'items': items})
        assert _flag(a, '--disallowedTools') is None and '--disallowedTools' not in a
        assert _flag(a, '--tools') == 'Bash,PowerShell,WebFetch,WebSearch'
        assert '--allowedTools' not in a


# ── error paths: the DEFAULT_FLAGS fallbacks and the refusals to build argv ──

def test_g08_missing_or_empty_flags_fall_back_to_the_defaults():
    """tools.py:112 (`(inventory or {}).get('flags') or DEFAULT_FLAGS`) and the
    same fallback at tools.py:100: an inventory with `flags` absent, `None` or
    `{}` is read as the defaults — no `Skill` (slash commands stay off) and the
    blanket `mcp__*`, never a crash and never a silently wider tool list. The
    blanket deny wins even over excluded items the inventory still names."""
    items = [_mcp('user', 'web')]
    for flags in (None, {}):
        inv = {'flags': flags, 'items': items}
        a = T.tool_argv(('read',), inv)
        assert _flag(a, '--tools') == 'Read,Glob,Grep'
        assert T.SKILL not in _flag(a, '--tools').split(',')
        assert _flag(a, '--disallowedTools') == 'mcp__*'


def test_g09_partial_flags_dicts_refuse_the_argv():
    """tools.py:113 (`flags['disable_slash_commands']`) and tools.py:100
    (`[...]['mcp_servers']`): a flags dict the module cannot read raises instead
    of guessing — defaulting a missing key would spawn with a deny or a Skill
    state the inventory never said (fail-closed: no argv, therefore no spawn)."""
    with pytest.raises(KeyError):                    # tools.py:100
        T.mcp_deny({'flags': {'disable_slash_commands': True}, 'items': []})
    with pytest.raises(KeyError):                    # tools.py:113, before mcp_deny
        T.tool_argv(('read',), {'flags': {'mcp_servers': []}, 'items': []})


def test_g10_an_inventory_the_module_cannot_name_raises_before_any_argv():
    """tools.py:100 (`s['name']`) and tools.py:103 (`i['name']`): an opted-in
    server or an otherwise-deniable excluded item with no name is not skipped
    into silence — `mcp_name` would turn a guessed `''` into a deny matching
    nothing, i.e. an excluded server left callable. Raising here means the
    adapter never builds an argv for an inventory it cannot name."""
    with pytest.raises(KeyError):                    # tools.py:100, opted-in side
        T.mcp_deny(_inv(servers=[{}], items=[]))
    named = dict(sources.DEFAULT_FLAGS, mcp_servers=[{'owner': 'account', 'name': 'gh'}])
    with pytest.raises(KeyError):                    # tools.py:103, item side
        T.mcp_deny({'flags': named,
                    'items': [{'type': 'mcp_server', 'status': 'excluded', 'source': 'user'}]})
    with pytest.raises(KeyError):                    # the same refusal through the argv
        T.tool_argv(('read',), {'flags': named,
                                'items': [{'type': 'mcp_server', 'status': 'excluded',
                                           'source': 'user'}]})
