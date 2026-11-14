"""T-1174 · the ten highest-risk UNCOVERED branches of claude_sessions/mcp.py,
lines 1-246 inclusive (the slice owns `get_mcp_status`, `_status_icon`,
`_mcp_background`, `analyze_mcp_tools`, `GLOBAL_MD_STUB`,
`update_global_claude_md_mcp`, `global_claude_md_menu`, MCP_SCOPES/TRANSPORTS),
at tip 56d53504. Ranking is fail-closed and denial first, then boundaries, then
error paths. Each test's own docstring names the branch whose removal or
inversion it catches.

Final selected branches (source file:line, see the report for the closest
existing test and why its assertion misses the case):

 1. mcp.py:42-45   per-config-dir cache KEY            -> test_two_config_dirs_never_share_one_mcp_status_cache
 2. mcp.py:44      `< _STATUS_TTL` expiry boundary     -> test_the_status_cache_expires_exactly_at_the_ttl
 3. mcp.py:44      `and not refresh` bypass            -> test_refresh_true_walks_past_a_fresh_cache
 4. mcp.py:83-84   no binary -> cached empty, no spawn -> test_a_missing_binary_answers_empty_without_spawning
 5. mcp.py:94-95   proc.run gave up (None) -> cached   -> test_a_runner_that_gives_up_caches_the_empty_answer
 6. mcp.py:98-113  truncated / hostile status lines    -> test_a_truncated_status_line_fails_closed_and_is_kept
 7. mcp.py:62-74   Codex `enabled=False` reads 'fail'  -> test_a_disabled_codex_server_reads_fail_and_is_kept
 8. mcp.py:120-125 unknown status never draws as ok    -> test_an_unrecognised_status_never_draws_as_connected
 9. mcp.py:191-194 re-tag keeps the prose either side  -> test_rewriting_an_mcp_block_keeps_the_users_own_prose
10. mcp.py:184-189 unreadable CLAUDE.md is not "empty" -> test_an_unreadable_claude_md_is_not_treated_as_an_empty_one

All ten probes on the card's starting list were checked against the existing
tests first and NONE of them turned out to be already covered inside this slice
(the evidence is in the report), so none was replaced. One test was ADDED beyond
the ten: the fail-closed counterpart of probe 7 on the same statement block, the
`except Exception: return miss()` around the Codex read (mcp.py:68-72), because
a raising account reader is the dangerous half of that branch and one line away
from the branch the probe names
-> test_a_raising_codex_reader_caches_empty_instead_of_raising.

Everything is seam-faked before the slice can reach the host: `claude_sessions.
proc.run` (the only spawn site the slice owns), `config.account_env` (so no host
environment is ever copied into an assertion), `codex.mcp_list` (the reader of
the real `~/.codex`), `config.load_settings`/`settings_file`/`_USERPROFILE`/
`config_dir`/`global_claude_md` (account discovery), `mcp.get_claude_exe` (the
by-value seam this module documents at mcp.py:75-81) and `mcp.open_in_editor`.
All invented credential-shaped data, all writes under `tmp_path`, no network, no
real subprocess, no sleep.
"""
import builtins
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import config
from claude_sessions import codex as codex_mod
from claude_sessions import proc as proc_mod

# `claude_sessions/mcp.py` starts a daemon thread AT IMPORT (mcp.py:141) whose
# body is `get_mcp_status()` with no cfgdir. Importing this module therefore
# runs the slice before any fixture exists: on a machine with claude.exe
# installed that thread reaches `proc.run` and runs the real `claude mcp list`
# against the real account, which no per-test fixture can retract. Pin the
# by-value exe seam for the duration of the import, and hand `config`'s own name
# straight back afterwards so no other module in the session sees it changed.
_real_get_claude_exe = config.get_claude_exe
config.get_claude_exe = lambda: None            # noqa: E731 — import guard only
try:
    from claude_sessions import mcp as mcp_mod
finally:
    config.get_claude_exe = _real_get_claude_exe

#: a binary path that is never executed: `proc.run` is faked in every test here.
FAKE_EXE = os.path.join('C:\\fake', 'claude.exe')

#: invented settings — the shape `load_settings` answers with, with no value
#: read off the machine running the suite.
_SYNTH_SETTINGS = dict(config._DEFAULT_SETTINGS)


class _Clock:
    """`mcp`'s `time` name, replaced wholesale: the slice calls time.time()
    only, so a frozen clock is the whole of what the cache sees."""

    def __init__(self, start):
        self.t = float(start)

    def time(self):
        return self.t


class _Result:
    """CompletedProcess stand-in — the three attributes the parse reads."""

    def __init__(self, stdout='', stderr='', returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


class _Runner:
    """`proc.run` stand-in. Records argv/env/timeout, returns canned results.

    The recorded `env` is always one of the synthetic mappings this file builds;
    `_wire` fakes `config.account_env` so the host environment can never be
    copied in here.
    """

    def __init__(self, results=()):
        self.calls = []
        self._results = list(results)

    def __call__(self, args, **kw):
        self.calls.append({'args': list(args), 'env': dict(kw.get('env') or {}),
                          'timeout': kw.get('timeout'), 'kw': dict(kw)})
        if self._results:
            return self._results.pop(0)
        raise AssertionError('proc.run was called with no canned result left: %r'
                             % (args,))


def _wire(monkeypatch, tmp_path, results=(), exe=FAKE_EXE):
    """Pin every host-facing seam the slice can reach, then hand back the runner.

    Ordered deliberately: the account/harness registry, the settings file and
    the user profile are fake BEFORE the call, so `harnesses.of` classifies the
    invented homes from invented settings rather than walking the real profile.
    """
    active = tmp_path / 'active-home'
    monkeypatch.setattr(config, '_USERPROFILE', str(tmp_path))
    monkeypatch.setattr(config, 'settings_file',
                        str(tmp_path / 'archeus.json'))
    monkeypatch.setattr(config, 'config_dir', str(active))
    monkeypatch.setattr(config, 'global_claude_md',
                        str(active / 'CLAUDE.md'))
    monkeypatch.setattr(config, 'load_settings', lambda: dict(_SYNTH_SETTINGS))
    monkeypatch.setattr(mcp_mod, 'get_claude_exe', lambda: exe)
    # the editor/pager/progress seams: recording, never launching
    opened = []
    monkeypatch.setattr(mcp_mod, 'open_in_editor',
                        lambda p: (opened.append(p), True)[1])
    monkeypatch.setattr(mcp_mod, 'pager', lambda *a, **k: None)
    monkeypatch.setattr(mcp_mod, 'run_with_progress',
                        lambda *a, **k: ('', False))
    seen_env = []

    def fake_account_env(cfgdir=None, harness=None):
        seen_env.append(cfgdir)
        return {'CLAUDE_CONFIG_DIR': config.resolve_config_dir(cfgdir)}

    monkeypatch.setattr(config, 'account_env', fake_account_env)
    runner = _Runner(results)
    monkeypatch.setattr(proc_mod, 'run', runner)
    runner.opened = opened
    runner.env_seen = seen_env
    return runner


def _home(tmp_path, name):
    d = tmp_path / name
    d.mkdir(exist_ok=True)
    return str(d)


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


# ── 1-3: the cache is keyed per account, and its two exits are expiry/refresh ──

def test_two_config_dirs_never_share_one_mcp_status_cache(tmp_path, monkeypatch):
    """Branch: mcp.py:42-45 — `key = _c.resolve_config_dir(cfgdir)`.

    The cache must be keyed on the RESOLVED home, because the same function is
    the MCP status of three different CLIs and of every account. Keying it on
    anything else (a constant, `None`, the active account) makes the second
    account answer with the first account's servers, which is a credential-shaped
    lie: the page says server X is connected while the account it was asked
    about has no server X at all.
    """
    a = _home(tmp_path, 'home-a')
    b = _home(tmp_path, 'home-b')
    runner = _wire(monkeypatch, tmp_path, results=[
        _Result('alpha: npx -y alpha - ✔ Connected\n'),
        _Result('beta: npx -y beta - ✔ Connected\n'),
    ])
    assert mcp_mod.get_mcp_status(a) == [('alpha', 'ok')]
    assert mcp_mod.get_mcp_status(b) == [('beta', 'ok')], 'b read a\'s cached rows'
    assert mcp_mod.get_mcp_status(a) == [('alpha', 'ok')]
    # one spawn per account and never a third: the 30s cache is the whole point
    assert len(runner.calls) == 2
    assert [c['args'][1:] for c in runner.calls] == [['mcp', 'list']] * 2
    assert [c['env']['CLAUDE_CONFIG_DIR'] for c in runner.calls] == [a, b]
    assert sorted(mcp_mod._status_cache) == sorted([a, b])


def test_the_status_cache_expires_exactly_at_the_ttl(tmp_path, monkeypatch):
    """Branch: mcp.py:44 — `time.time() - hit[0] < _STATUS_TTL`.

    The boundary, both sides of it. `<` is the contract: an entry whose age is
    exactly the TTL is stale and re-runs. Flipping it to `<=` keeps a dead
    server on the dashboard for one more poll than the module promises, and
    nothing outside `conftest`'s cache cleanup has ever named `_STATUS_TTL` or
    `_status_cache`, so no existing test moves this clock at all.
    """
    home = _home(tmp_path, 'home-ttl')
    clock = _Clock(1000.0)
    monkeypatch.setattr(mcp_mod, 'time', clock)
    runner = _wire(monkeypatch, tmp_path, results=[
        _Result('live: npx -y live - ✔ Connected\n'),
        _Result('dead: npx -y dead - ✘ Failed to connect\n'),
    ])
    assert mcp_mod.get_mcp_status(home) == [('live', 'ok')]
    clock.t += mcp_mod._STATUS_TTL - 0.001
    assert mcp_mod.get_mcp_status(home) == [('live', 'ok')]
    assert len(runner.calls) == 1, 'still inside the TTL: nothing may be run'
    clock.t += 0.001                      # exactly _STATUS_TTL after the write
    assert mcp_mod.get_mcp_status(home) == [('dead', 'fail')], 'stale answer served'
    assert len(runner.calls) == 2


def test_refresh_true_walks_past_a_fresh_cache(tmp_path, monkeypatch):
    """Branch: mcp.py:44 — `and not refresh`.

    Every MCP page action busts the cache with `refresh=True` after it writes,
    and the module comment at mcp.py:20-21 says so. Drop the flag check and an add or
    a remove reports the state from before itself, so the screen tells the user
    the server they just added is missing for the next 30 seconds.
    """
    home = _home(tmp_path, 'home-refresh')
    clock = _Clock(2000.0)
    monkeypatch.setattr(mcp_mod, 'time', clock)
    runner = _wire(monkeypatch, tmp_path, results=[
        _Result('before: npx -y b - ✔ Connected\n'),
        _Result('after: npx -y a - ✔ Connected\n'),
    ])
    assert mcp_mod.get_mcp_status(home) == [('before', 'ok')]
    assert mcp_mod.get_mcp_status(home) == [('before', 'ok')]
    assert len(runner.calls) == 1
    assert mcp_mod.get_mcp_status(home, refresh=True) == [('after', 'ok')]
    assert len(runner.calls) == 2, 'refresh=True must re-read'
    # and the refreshed answer is what the cache now holds for the plain path
    assert mcp_mod.get_mcp_status(home) == [('after', 'ok')]
    assert len(runner.calls) == 2
    assert runner.calls[1]['env']['CLAUDE_CONFIG_DIR'] == home, \
        'the refreshed read still names the account it was asked about'


# ── 4-5: the two ways the answer is empty and nothing may be spawned ─────────

def test_a_missing_binary_answers_empty_without_spawning(tmp_path, monkeypatch):
    """Branch: mcp.py:82-84 — `if not claude_exe: return miss()`.

    Two contracts in one line. (a) No executable means NO argv is ever handed to
    `proc.run` — the guard sits before the spawn, and `miss()` must not be
    reached by trying. (b) The empty answer is CACHED (mcp.py:47-58 is explicit
    that the uncached empty answer was the expensive bug: a 1.7s subprocess per
    dashboard poll), so the second call spawns nothing either.
    """
    home = _home(tmp_path, 'home-noexe')
    runner = _wire(monkeypatch, tmp_path, results=[], exe=None)
    assert mcp_mod.get_mcp_status(home) == []
    assert mcp_mod.get_mcp_status(home) == [], 'the negative answer must be cached'
    assert runner.calls == [], 'a missing binary must never reach proc.run'
    assert runner.env_seen == [], 'nothing asked for an account environment'
    assert mcp_mod._status_cache[home][1] == []


def test_a_runner_that_gives_up_caches_the_empty_answer(tmp_path, monkeypatch):
    """Branch: mcp.py:91-95 — `r = proc.run(...); if r is None: return miss()`.

    `proc.run` answers None when the child could not be started at all, and that
    is also how a timed-out probe arrives here. The slice must not raise, must
    answer [] and must CACHE it (mcp.py:47-58), and the call it did make must
    carry the 10s timeout the module promises and the account env — the two
    arguments whose absence is the account-leak and the hang this line guards.
    """
    home = _home(tmp_path, 'home-none')
    runner = _wire(monkeypatch, tmp_path, results=[None, None])
    assert mcp_mod.get_mcp_status(home) == []
    assert mcp_mod.get_mcp_status(home) == []
    assert len(runner.calls) == 1, 'the empty answer must be cached like any other'
    assert runner.calls[0]['args'] == [FAKE_EXE, 'mcp', 'list']
    assert runner.calls[0]['timeout'] == 10, 'mcp list is bounded by 10s on purpose'
    assert runner.calls[0]['env'] == {'CLAUDE_CONFIG_DIR': home}
    assert mcp_mod._status_cache[home][1] == []


# ── 6: the parse of a list output that is not the happy path ────────────────

_HOSTILE = (
    'Checking MCP server health...\n'
    'Checking MCP server health: 3 of 5\n'
    'half-ok: https://mcp.example/mcp (HTTP) - \u2714 Conn\n'
    'half-fail: npx -y pkg - \u2718 Failed to co\n'
    'bare-name:\n'
    'this line has no separator at all\n'
)


def test_a_truncated_status_line_fails_closed_and_is_kept(tmp_path, monkeypatch):
    """Branch: mcp.py:98-113 — the two `continue`s and the `else` of the parse.

    Output cut off mid-line is what a killed or slow `claude mcp list`
    produces. Every one of these lines has to land on the fail-closed side:
      · `half-ok` keeps its ✔ and is the ONLY line allowed to say connected;
      · `half-fail` has lost its status word, matches neither ✔/Connected nor
        '!'/auth, and must therefore be listed as 'fail' — dropping it is the
        bug mcp.py:110-113 was written for;
      · `bare-name:` lost everything after its colon and is still a server,
        reported 'fail' rather than as a connected one or as an unnamed row;
      · the header line and the separator-less line produce NO row at all — a
        header that parses into a server is a server that does not exist, and
        the colon-bearing progress line is the one that gets there if the
        `startswith('checking')` skip is what is removed;
    Exact dict equality is the assertion, so an extra row, a dropped row or a
    single wrong status fails it.
    """
    home = _home(tmp_path, 'home-hostile')
    _wire(monkeypatch, tmp_path, results=[_Result(_HOSTILE)])
    got = dict(mcp_mod.get_mcp_status(home))
    assert got == {'half-ok': 'ok', 'half-fail': 'fail', 'bare-name': 'fail'}
    assert '' not in got, 'a row with no name is a server nobody can manage'


# ── 7: the Codex half of the same function ──────────────────────────────────

_CODEX_ROWS = [
    {'name': 'live', 'enabled': True, 'kind': 'stdio', 'command': 'npx',
     'args': ['-y', 'live'], 'env_keys': ['TOKEN'], 'why': ''},
    {'name': 'off', 'enabled': False, 'kind': 'stdio', 'command': 'npx',
     'args': ['-y', 'off'], 'env_keys': ['SECRET'], 'why': 'disabled by the owner'},
]


def test_a_disabled_codex_server_reads_fail_and_is_kept(tmp_path, monkeypatch):
    """Branch: mcp.py:62-74 — `'ok' if r['enabled'] else 'fail'` and its cache.

    Codex reports `enabled` instead of probing the connection, so a disabled
    server is the one row a naive reader throws away, and the docstring at
    mcp.py:36-40 calls that answer the whole point of reading Codex at all.
    Three things are pinned: the disabled row survives as 'fail' rather than
    vanishing; the read is asked for THE HOME it was given — passing None makes
    `codex.mcp_list` read whoever's real `~/.codex` the process happens to be
    running under, which is the account leak this card is about; and a Codex
    home never spawns the Claude binary. The invented env VALUES never exist
    here, only key names, so nothing credential-shaped is ever carried out.
    """
    home = _home(tmp_path, '.codex')           # the built-in Codex home shape
    asked = []

    def fake_mcp_list(home_arg=None):
        asked.append(home_arg)
        return [dict(r) for r in _CODEX_ROWS]

    monkeypatch.setattr(codex_mod, 'mcp_list', fake_mcp_list)
    runner = _wire(monkeypatch, tmp_path, results=[])
    assert mcp_mod.get_mcp_status(home) == [('live', 'ok'), ('off', 'fail')]
    assert asked == [home], 'the Codex read was not scoped to the home asked for'
    assert runner.calls == [], 'a Codex home must never run the Claude binary'
    assert mcp_mod.get_mcp_status(home) == [('live', 'ok'), ('off', 'fail')]
    assert len(asked) == 1, 'the same home on the same cache must not re-read'


def test_a_raising_codex_reader_caches_empty_instead_of_raising(
        tmp_path, monkeypatch):
    """Branch: mcp.py:68-72 — `except Exception: return miss()` around the read.

    The companion fail-closed half of the branch above — the one test beyond the
    card's ten, and the reason its 'timeout / absent runner result' probe reads
    as a pair here: a reader that
    raises (missing codex binary, unreadable home, junk from the CLI) must give
    the same cached empty answer as one that returns nothing, not a traceback
    through the dashboard endpoint that polls it every 10 seconds.
    """
    home = _home(tmp_path, '.codex')
    hits = []

    def boom(home_arg=None):
        hits.append(home_arg)
        raise RuntimeError('invented: the codex CLI is not installed')

    monkeypatch.setattr(codex_mod, 'mcp_list', boom)
    runner = _wire(monkeypatch, tmp_path, results=[])
    assert mcp_mod.get_mcp_status(home) == []
    assert mcp_mod.get_mcp_status(home) == []
    assert len(hits) == 1, 'the empty answer must be cached, not retried'
    assert runner.calls == []


# ── 8: the renderer of a status the code does not know ──────────────────────

def test_an_unrecognised_status_never_draws_as_connected():
    """Branch: mcp.py:120-125 — the fall-through `return` of `_status_icon`.

    `test_status_icons_are_distinct_per_state` only ever asks for 'ok', 'auth'
    and 'fail', so the default arm — the one every unexpected value lands in,
    including a status read from a cache written by another version — is free to
    return the green tick. It must not: an unknown state draws the same warning
    as 'auth' and never a tick or a cross, and only the two named states get
    those two glyphs.
    """
    ok = mcp_mod._status_icon('ok')
    fail = mcp_mod._status_icon('fail')
    warn = mcp_mod._status_icon('auth')
    assert '\u2714' in ok and '\u2718' in fail
    for status in ('unknown', '', 'OK', 'connected', 'failed', None, True):
        icon = mcp_mod._status_icon(status)
        assert '\u2714' not in icon, '%r was drawn as connected' % (status,)
        assert '\u2718' not in icon, '%r was drawn as failed' % (status,)
        assert icon == warn, '%r did not draw as the warning it promises' % (status,)


# ── 9-10: the global CLAUDE.md writers, which can destroy the user's file ───

def test_rewriting_an_mcp_block_keeps_the_users_own_prose(tmp_path, monkeypatch):
    """Branch: mcp.py:191-194 — the `pre + section + post` re-tag path.

    The file is Claude's global context, and the sentinels only delimit
    archeus's own block. The two slices are the contract: text written BEFORE
    the block survives, text written AFTER it survives, and only what sits
    between the sentinels is replaced. Drop `post` (or `pre`) and every update
    silently deletes half of the user's instructions with no way back — and a
    second update must REPLACE the block, never append a second one.
    """
    home = _home(tmp_path, 'acct')
    _wire(monkeypatch, tmp_path, results=[])
    md = os.path.join(home, 'CLAUDE.md')
    with open(md, 'w', encoding='utf-8', newline='\n') as f:
        f.write(
            '# My global context\n'
            'PROSE-BEFORE the archeus block, mine.\n'
            '<!-- MCP:svc:START -->\n'
            '## MCP: svc\n'
            'OLD DOC\n'
            '<!-- MCP:svc:END -->\n'
            'PROSE-AFTER the archeus block, also mine.\n')

    assert mcp_mod.update_global_claude_md_mcp('svc', 'NEW DOC', home) is True
    text = _read(md)
    assert 'PROSE-BEFORE the archeus block, mine.' in text
    assert 'PROSE-AFTER the archeus block, also mine.' in text
    assert 'NEW DOC' in text and 'OLD DOC' not in text
    assert text.count('<!-- MCP:svc:START -->') == 1
    assert text.count('<!-- MCP:svc:END -->') == 1
    assert (text.index('PROSE-BEFORE') < text.index('## MCP: svc')
            < text.index('PROSE-AFTER')), 'the block moved outside the prose'

    assert mcp_mod.update_global_claude_md_mcp('svc', 'NEWEST DOC', home)
    again = _read(md)
    assert 'NEWEST DOC' in again and 'NEW DOC' not in again
    assert again.count('<!-- MCP:svc:START -->') == 1
    assert os.listdir(home) == ['CLAUDE.md'], 'a stray temp file was left behind'


def test_an_unreadable_claude_md_is_not_treated_as_an_empty_one(tmp_path,
                                                                monkeypatch):
    """Branch: mcp.py:184-189 — `except Exception: pass` around the read.

    The file exists and holds prose; the read is denied (an editor holding it
    open, a roaming profile mid-sync, a reader without permission). Faked as a
    narrow `builtins.open` shim so no file permission is touched and the same
    assertion runs on Linux here and on Windows in review. archeus must refuse
    that write; today the user's context is replaced by a generated header.
    """
    home = _home(tmp_path, 'acct')
    _wire(monkeypatch, tmp_path, results=[])
    md = os.path.join(home, 'CLAUDE.md')
    real_open = builtins.open
    with real_open(md, 'w', encoding='utf-8', newline='\n') as f:
        f.write('# My global context\nUSER PROSE THAT MATTERS\n')
    target = os.path.abspath(md)

    def locked_open(file, *args, **kw):
        if os.path.abspath(str(file)) == target:
            raise PermissionError(13, 'invented: the file is open elsewhere')
        return real_open(file, *args, **kw)

    monkeypatch.setattr(builtins, 'open', locked_open)
    mcp_mod.update_global_claude_md_mcp('svc', 'GENERATED DOC', home)
    text = real_open(md, encoding='utf-8').read()
    assert 'USER PROSE THAT MATTERS' in text, \
        'an unreadable CLAUDE.md was overwritten, not left alone'
    assert 'GENERATED DOC' not in text, \
        'the refused write still landed its own block'


def test_a_fenced_example_of_the_pair_is_never_the_block_replaced(tmp_path, monkeypatch):
    """Branch: mcp.py update_global_claude_md_mcp — the markers were found with a
    plain substring search, so a closed fenced example of the pair above the real
    block was taken for the block: its body was replaced and the real block went
    untouched. The real block must be the one replaced, and the example kept."""
    home = _home(tmp_path, 'acct')
    _wire(monkeypatch, tmp_path, results=[])
    md = os.path.join(home, 'CLAUDE.md')
    example = ('```md\n<!-- MCP:svc:START -->\nEXAMPLE BODY\n'
               '<!-- MCP:svc:END -->\n```\n')
    with open(md, 'w', encoding='utf-8', newline='\n') as f:
        f.write('# My global context\n\n' + example + '\n'
                '<!-- MCP:svc:START -->\n## MCP: svc\nOLD DOC\n<!-- MCP:svc:END -->\n')

    assert mcp_mod.update_global_claude_md_mcp('svc', 'NEW DOC', home) is True
    text = _read(md)
    assert example in text, 'the fenced example was rewritten'
    assert 'NEW DOC' in text and 'OLD DOC' not in text
    assert text.count('<!-- MCP:svc:START -->') == 2


def test_a_fenced_example_alone_gets_the_real_block_appended(tmp_path, monkeypatch):
    home = _home(tmp_path, 'acct')
    _wire(monkeypatch, tmp_path, results=[])
    md = os.path.join(home, 'CLAUDE.md')
    example = ('```md\n<!-- MCP:svc:START -->\nEXAMPLE BODY\n'
               '<!-- MCP:svc:END -->\n```\n')
    with open(md, 'w', encoding='utf-8', newline='\n') as f:
        f.write('# My global context\n\n' + example)

    assert mcp_mod.update_global_claude_md_mcp('svc', 'NEW DOC', home) is True
    text = _read(md)
    assert text.startswith('# My global context\n\n' + example)
    assert text.count('<!-- MCP:svc:START -->') == 2
    assert text.endswith('## MCP: svc\nNEW DOC\n<!-- MCP:svc:END -->\n')


def test_reversed_mcp_markers_are_refused_not_spliced(tmp_path, monkeypatch):
    """Branch: mcp.py update_global_claude_md_mcp — END before START made the
    splice `pre + section + post` overlap the user's prose. Stray markers are not
    ours to rewrite: the write is refused, as an unreadable file is."""
    home = _home(tmp_path, 'acct')
    _wire(monkeypatch, tmp_path, results=[])
    md = os.path.join(home, 'CLAUDE.md')
    before = ('# My global context\nPROSE ONE\n<!-- MCP:svc:END -->\nPROSE TWO\n'
              '<!-- MCP:svc:START -->\nPROSE THREE\n')
    with open(md, 'w', encoding='utf-8', newline='\n') as f:
        f.write(before)

    assert mcp_mod.update_global_claude_md_mcp('svc', 'NEW DOC', home) is False
    assert _read(md) == before


def test_ordinary_mcp_replace_keeps_its_bytes_and_a_missing_file_is_created(
        tmp_path, monkeypatch):
    """Guard: the ordinary replace changes nothing outside the pair (the text
    after END keeps exactly its own newline, so repeated syncs never grow the
    file), and a missing file is still created."""
    home = _home(tmp_path, 'acct')
    _wire(monkeypatch, tmp_path, results=[])
    md = os.path.join(home, 'CLAUDE.md')
    with open(md, 'w', encoding='utf-8', newline='\n') as f:
        f.write('# My global context\nPROSE-BEFORE\n<!-- MCP:svc:START -->\n'
                '## MCP: svc\nOLD DOC\n<!-- MCP:svc:END -->\nPROSE-AFTER\n')
    assert mcp_mod.update_global_claude_md_mcp('svc', 'NEW DOC', home) is True
    assert _read(md) == ('# My global context\nPROSE-BEFORE\n<!-- MCP:svc:START -->\n'
                         '## MCP: svc\nNEW DOC\n<!-- MCP:svc:END -->\n'
                         'PROSE-AFTER\n')

    fresh = _home(tmp_path, 'fresh')
    assert mcp_mod.update_global_claude_md_mcp('svc', 'NEW DOC', fresh) is True
    assert 'NEW DOC' in _read(os.path.join(fresh, 'CLAUDE.md'))
