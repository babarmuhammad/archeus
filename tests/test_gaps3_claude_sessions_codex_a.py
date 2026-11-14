"""T-1185 — gaps3 coverage for `claude_sessions/codex.py` lines 1-343 (tip 56d53504).

The ten final selected branches (fail-closed and denial first, then boundaries,
then error paths), each owned by one test below. Probes that existing
`tests/test_codex.py` already covered were replaced as marked; probes where the
source disagrees with the contract stay as strict xfail with the defect named.

1. `db_path`/`_rows` empty-or-None home must not fall back to a database found
   through the process working directory (codex.py:43-46,53-55). [probe 1, xfail]
2. `launch_argv` permission axis: an unknown mode must never reach `-a`, and
   never as `never`; the four Codex-native values pass through verbatim; the
   two Claude translations map exactly (codex.py:305-308, 332-335, 341). [probe 8]
3. `launch_argv` prompt must not be able to take the slot of a flag — an
   option-like prompt needs an option terminator (codex.py:319-320). [probe 9, xfail]
4. `_rows` a VALID sqlite whose shape is not recognised (no `threads`, a lost
   column) is no sessions, never an exception; a NULL/blank `cwd` row is
   skipped and both-NULL timestamps are mtime 0.0, not a crash
   (codex.py:49-66,105-113). [probe 2]
5. `launch_argv` a resume/fork id stays exactly ONE argv element, even with
   spaces, tabs, `::` or option-like text (codex.py:285-292). [probe 10]
6. `transcript_path` is bound to the home the folder is under: an id from
   another home does not resolve here, the id is a bound parameter not SQL,
   and a NULL `rollout_path` reads '' (codex.py:117-120, 149-155). [probe 3]
7. `scan`/`_count` a rollout that cannot be read gives 0, never a crash and
   never a guess; a torn tail and non-dict lines do not move the counter; the
   list is newest-first (codex.py:126-128,143-145,158-174). [probe 4, xfail:
   NULL `rollout_path` raises TypeError; a non-dict `payload` raises AttributeError]
8. `_spend` a `token_count` whose cumulative total is empty or all-zero banks
   nothing at all — no phantom per-model zero entry (codex.py:260-262).
   [replaces probe 5, the cumulative-delta replay already covered at
   tests/test_codex.py `test_a_cumulative_total_is_banked_as_a_delta`]
9. `_split` a `cached_input_tokens` ahead of `input_tokens` clamps `in` to 0
   instead of going negative, and NULL fields read 0 (codex.py:235-240).
   [probe 6]
10. `fold` a later record cannot rewrite what an earlier one recorded: the
    `turn_context` cwd fills only an empty `cwd`, timestamps track min/max and
    garbage timestamps add nothing, `error` events count once
    (codex.py:184-191, 209-210, 221-222). [replaces probe 7, the A-B-A model
    ordering already covered at tests/test_codex.py
    `test_a_session_that_switched_model_bills_each_one_its_own_stretch`]

Every fake home, database and rollout lives under `tmp_path`; the OS seams the
slice could otherwise reach outward through (`harnesses.exe`,
`paths.find_actual_path`) are faked before the first call, and rollout bytes
are written with explicit `\\n` newlines. No sibling `test_gaps3` file is
imported and no test depends on another test's leftovers.
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import codex, sessions
from claude_sessions import harnesses as _harnesses
from claude_sessions import paths as _paths_mod

COLS = codex._COLS


@pytest.fixture(autouse=True)
def _no_host_state(monkeypatch):
    """Nothing this slice calls reads a config root, a selected home, an
    account, or a credential — but the two discovery seams that could reach
    host state at all are faked before the first call anyway, so a future
    entrypoint cannot leak through them by accident."""
    monkeypatch.setattr(_harnesses, 'exe', lambda hid=None: None)
    monkeypatch.setattr(_paths_mod, 'find_actual_path', lambda enc, *a, **k: None)


def _row(sid='', rollout=None, cwd=None, preview=None, first=None, model=None,
         tokens=None, branch=None, archived=None, upd=None, crt=None):
    m = {'id': sid, 'rollout_path': rollout, 'cwd': cwd, 'preview': preview,
         'first_user_message': first, 'model': model, 'tokens_used': tokens,
         'git_branch': branch, 'archived': archived, 'updated_at_ms': upd,
         'created_at_ms': crt}
    return [m[c] for c in COLS]


def _db(home, rows, cols=None):
    """A `state_5.sqlite` under *home* holding exactly *rows*."""
    cols = cols or COLS
    os.makedirs(home, exist_ok=True)
    con = sqlite3.connect(os.path.join(home, 'state_5.sqlite'))
    con.execute('CREATE TABLE threads (%s)' % ', '.join(cols))
    for r in rows:
        con.execute('INSERT INTO threads VALUES (%s)' % ','.join('?' * len(cols)), r)
    con.commit()
    con.close()


def _write(path, *lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        for line in lines:
            f.write(line + '\n')
    return path


def _j(obj):
    return json.dumps(obj)


def _jsonl(path, *objs):
    return _write(path, *[_j(o) for o in objs])


# ── 1 · fail closed on a home that is not a home ───────────────────────────

def test_an_empty_home_never_falls_back_to_the_working_directory(tmp_path, monkeypatch):
    sibling = str(tmp_path / 'sibling-home')
    empty_home = str(tmp_path / 'empty-home')
    os.makedirs(empty_home)
    _db(sibling, [_row('x1', cwd='Q:/foreign', upd=10, crt=10)])
    # a given home with no database answers "no sessions" even when a
    # neighbouring directory one level away has exactly such a file
    assert codex.projects(empty_home) == []
    assert codex.has_project(empty_home, codex._enc('Q:/foreign')) is False

    decoy = str(tmp_path / 'cwd-decoy')
    os.makedirs(decoy)
    _db(decoy, [_row('x1', cwd='Q:/foreign', upd=10, crt=10)])
    monkeypatch.chdir(decoy)
    assert codex.db_path('') == ''
    assert codex.projects('') == []
    assert codex.projects(None) == []
    assert codex.has_project('', codex._enc('Q:/foreign')) is False


# ── 2 · the permission axis never guesses ──────────────────────────────────

def test_an_unknown_permission_never_reaches_the_approval_flag():
    """The whole point of the whitelist is that a value archeus does not
    understand CANNOT pick an approval policy — least of all `never`, which is
    the one answer that turns the approval gate off. A casefolded membership
    test, a `PERMS.get(want, 'never')` default, or a dropped `if perm:` guard
    each opens this gate silently."""
    for want in ('Never', 'NEVER', 'nEver', 'never ', 'yolo', '-a',
                 '--dangerously-bypass', 'bypassPermissions ', 'default ',
                 'plan', 'acceptEdits', 'auto'):
        argv = codex.launch_argv('codex.exe', 'new', {'perm': want}, '')
        assert '-a' not in argv, want
        assert 'never' not in argv, want
    for want in sorted(codex._CODEX_PERMS):
        argv = codex.launch_argv('codex.exe', 'new', {'perm': want}, '')
        assert argv[1:3] == ['-a', want], want
    got = codex.launch_argv('codex.exe', 'new', {'perm': 'default'}, '')
    assert got[1:3] == ['-a', 'on-request']
    got = codex.launch_argv('codex.exe', 'new', {'perm': 'bypassPermissions'}, '')
    assert got[1:3] == ['-a', 'never']
    # `-a` is always a flag AND its value, never a flag swallowing the rest
    argv = codex.launch_argv('codex.exe', 'new', {'perm': 'never'}, '')
    assert len(argv) == argv.index('-a') + 2


# ── 3 · the prompt is the prompt, never a flag ──────────────────────────────

@pytest.mark.xfail(strict=True, reason="source defect: launch_argv appends opts['prompt'] "
                                       "as a bare trailing argument with no '--' option "
                                       "terminator (claude_sessions/codex.py:319-320), so a "
                                       "prompt beginning with '-' reaches codex as a flag")
def test_an_option_like_prompt_cannot_take_the_slot_of_a_flag():
    argv = codex.launch_argv('codex.exe', 'new', {'prompt': 'do a thing'}, '')
    assert argv[-1] == 'do a thing' and argv.count('do a thing') == 1
    assert codex.launch_argv('codex.exe', 'new', {'prompt': 42}, '')[-1] == '42'
    argv = codex.launch_argv('codex.exe', 'new', {'prompt': '--sandbox'}, '')
    assert '--sandbox' in argv                       # the prompt survives...
    assert '--' in argv, 'an option-like prompt must sit behind an option terminator'
    assert argv.index('--') < len(argv) - 1           # ...but never as an option


# ── 4 · an index this version does not describe ────────────────────────────

def test_an_index_this_version_does_not_describe_is_no_sessions(tmp_path):
    """The file is another program's: a VALID sqlite whose shape has drifted —
    no `threads`, a column the named `_COLS` SELECT no longer finds — is the
    same "no sessions" as an absent file, never an exception reaching the UI.
    The existing coverage only ever fed it bytes that were not a database at
    all, so a schema-drifted file is a different, unreached error path."""
    h1 = str(tmp_path / 'no-table')
    os.makedirs(h1)
    con = sqlite3.connect(os.path.join(h1, 'state_5.sqlite'))
    con.execute('CREATE TABLE other_things (id TEXT)')
    con.commit()
    con.close()
    assert codex.projects(h1) == []
    assert codex.scan(os.path.join(h1, 'projects', 'X--nothing')) == []
    assert codex.has_project(h1, 'X--nothing') is False

    h2 = str(tmp_path / 'lost-column')
    os.makedirs(h2)
    con = sqlite3.connect(os.path.join(h2, 'state_5.sqlite'))
    con.execute('CREATE TABLE threads (id TEXT, cwd TEXT)')
    con.execute('INSERT INTO threads VALUES (?, ?)', ('s1', 'C:/work/alpha'))
    con.commit()
    con.close()
    assert codex._rows(h2) == []
    assert codex.projects(h2) == []

    h3 = str(tmp_path / 'null-fields')
    _db(h3, [_row('s1', cwd=None, upd=7, crt=7),
             _row('s2', cwd='   ', upd=7, crt=7),
             _row('s3', cwd='C:/work/alpha')])       # BOTH timestamps NULL
    got = codex.projects(h3)
    assert [p[1] for p in got] == ['C:/work/alpha']
    assert got[0][0] == 0.0                          # missing time is 0, not a crash


# ── 5 · one id in, one argument out ─────────────────────────────────────────

def test_a_resume_or_fork_id_stays_exactly_one_argument():
    """The verb and the id are two argv elements and the id is never split,
    glued, or re-parsed — an id containing spaces, a tab, `::` or option-like
    text must arrive verbatim as ONE argument, or the session opened is not
    the session clicked. The existing argv test only used ids of bare letters."""
    ex = 'codex.exe'
    assert codex.launch_argv(ex, 'continue', {}, '') == [ex, 'resume', '--last']
    assert codex.launch_argv(ex, 'resume:abc def\t--last', {}, '') == \
        [ex, 'resume', 'abc def\t--last']
    assert codex.launch_argv(ex, 'fork:a b::c', {}, '') == [ex, 'fork', 'a b::c']
    assert codex.launch_argv(ex, 'fork:--yolo', {}, '') == [ex, 'fork', '--yolo']
    assert codex.launch_argv(ex, 'resume-named::my name::tail', {}, '') == \
        [ex, 'resume', 'my name']
    for choice in ('resume:two words', 'fork:two words'):
        argv = codex.launch_argv(ex, choice, {}, '')
        assert len(argv) == 3 and argv[1] in ('resume', 'fork')
        assert argv[2] == 'two words'


# ── 6 · the transcript belongs to the home its folder is under ─────────────

def test_a_transcript_lookup_is_bound_to_the_home_the_folder_is_in(tmp_path):
    """`<home>/projects/<enc>` is the whole handle: the rollout named by THIS
    home's index is the only answer. An id that exists in a second home does
    not resolve through this folder, the id is a bound parameter rather than
    SQL text, and a `rollout_path` stored NULL reads as '' — not a crash and
    not someone else's rollout."""
    cwd = 'C:/work/alpha'
    a = str(tmp_path / 'home-a')
    b = str(tmp_path / 'home-b')
    pa = os.path.join(a, 'sessions', 'rollout-s1.jsonl')
    pb = os.path.join(b, 'sessions', 'rollout-s2.jsonl')
    _jsonl(pa, {'type': 'event_msg', 'payload': {'type': 'user_message'}})
    _jsonl(pb, {'type': 'event_msg', 'payload': {'type': 'user_message'}})
    _db(a, [_row('s1', rollout=pa, cwd=cwd, upd=9, crt=9),
            _row('s3', rollout=None, cwd=cwd, upd=8, crt=8)])
    _db(b, [_row('s2', rollout=pb, cwd=cwd, upd=9, crt=9)])
    fa = os.path.join(a, 'projects', codex._enc(cwd))
    fb = os.path.join(b, 'projects', codex._enc(cwd))

    assert codex.transcript_path(fa, 's1') == pa
    assert codex.transcript_path(fb, 's2') == pb
    assert codex.transcript_path(fb, 's1') == ''     # s1 lives in the OTHER home
    assert codex.transcript_path(fa, 's2') == ''
    assert codex.transcript_path(fa, 's3') == ''     # rollout_path stored NULL
    assert codex.transcript_path(fa, "s1' OR '1'='1") == ''   # bound, never glued
    assert codex.transcript_path(fa, '') == ''


# ── 7 · an unreadable rollout is zero, never a crash and never a guess ─────

def test_a_rollout_that_cannot_be_read_counts_zero_rather_than_crashing(tmp_path):
    cwd = 'C:/work/alpha'
    home = str(tmp_path / 'home')
    good = os.path.join(home, 'sessions', 'rollout-good.jsonl')
    _jsonl(good,
           {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': 'hi'}},
           {'type': 'event_msg', 'payload': {'type': 'agent_message', 'message': 'ok'}},
           # the preamble that must NOT count: a response_item with a user role
           {'type': 'response_item', 'payload': {'type': 'user_message'}})
    with open(good, 'a', encoding='utf-8', newline='\n') as f:
        f.write('{"type": "event_msg", "payload": {"type": "user_mess\n')
        f.write('not json at all: event_msg\n')
        f.write('[1, 2]\n')
    strp = os.path.join(home, 'sessions', 'rollout-str.jsonl')
    _jsonl(strp, {'type': 'event_msg', 'payload': 'user_message'})
    folder = os.path.join(home, 'projects', codex._enc(cwd))
    missing = os.path.join(home, 'sessions', 'gone.jsonl')

    _db(home, [_row('g', rollout=good, cwd=cwd, preview='hi', upd=30, crt=30),
               _row('m', rollout=missing, cwd=cwd, preview='gone', upd=20, crt=20)])
    got = codex.scan(folder)
    assert [(r[1], r[3]) for r in got] == [('g', 2), ('m', 0)]
    assert [r[0] for r in got] == sorted([r[0] for r in got], reverse=True)

    # the same scan with the two shapes that exist on disk today: a NULL path
    # and a payload that is a bare string — 0 each, and no exception
    con = sqlite3.connect(os.path.join(home, 'state_5.sqlite'))
    con.execute('UPDATE threads SET rollout_path = NULL WHERE id = ?', ('m',))
    con.execute('INSERT INTO threads VALUES (%s)' % ','.join('?' * len(COLS)),
                _row('st', rollout=strp, cwd=cwd, preview='str', upd=25, crt=25))
    con.commit()
    con.close()
    got = codex.scan(folder)
    assert [(r[1], r[3]) for r in got] == [('g', 2), ('st', 0), ('m', 0)]


# ── 8 · a total with nothing in it banks nothing ────────────────────────────

def test_a_token_count_with_nothing_to_bank_banks_nothing():
    """A `token_count` whose cumulative total is absent or all zero is a
    heartbeat, not a spend. Banking it under `models[-1]` invents a model row
    of pure zeros in the usage table — and the delta logic cannot wash it out,
    because the entry itself is the lie. The guard at codex.py:261-262 is the
    only thing between the two outcomes."""
    s = dict(sessions._EMPTY_STATS, models=['gpt-5.5'], usage_by_model={})
    for p in ({'type': 'token_count'},
              {'type': 'token_count', 'info': None},
              {'type': 'token_count', 'info': {}},
              {'type': 'token_count', 'info': {'total_token_usage': None}},
              {'type': 'token_count', 'info': {'total_token_usage': {
                  'input_tokens': None, 'cached_input_tokens': None,
                  'output_tokens': None}}}):
        codex.fold({'type': 'event_msg', 'payload': p}, s)
    assert s['usage_by_model'] == {}
    assert s.keys() == sessions._EMPTY_STATS.keys()
    # and the moment there IS a total, the same code path banks it normally
    codex.fold({'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {
        'total_token_usage': {'input_tokens': 30, 'cached_input_tokens': 10,
                              'output_tokens': 5}}}}, s)
    assert s['usage_by_model'] == {'gpt-5.5': {'in': 20, 'out': 5,
                                               'cache_read': 10, 'cache_create': 0}}


# ── 9 · a cache bigger than the prompt is clamped, not negative ────────────

def test_a_cache_ahead_of_the_prompt_clamps_instead_of_going_negative():
    """A malformed or mid-update total can report more cached input than input.
    `in` is their difference and must clamp at 0 — a negative here is a
    discount the usage table hands out and no later delta erases it. Existing
    fixtures only ever used cached <= input, so the `max(0, ...)` at
    codex.py:238 was never load-bearing in a test."""
    assert codex._split({'input_tokens': 100, 'cached_input_tokens': 180,
                         'output_tokens': 20}) == {
        'in': 0, 'out': 20, 'cache_read': 180, 'cache_create': 0}
    assert codex._split(None) == {'in': 0, 'out': 0, 'cache_read': 0,
                                  'cache_create': 0}
    assert codex._split({'input_tokens': None, 'cached_input_tokens': None,
                         'output_tokens': None}) == {'in': 0, 'out': 0,
                                                     'cache_read': 0,
                                                     'cache_create': 0}
    s = dict(sessions._EMPTY_STATS, models=[], usage_by_model={})
    codex.fold({'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {
        'total_token_usage': {'input_tokens': 100, 'cached_input_tokens': 180,
                              'output_tokens': 20}}}}, s)
    assert s['usage_by_model']['codex'] == {'in': 0, 'out': 20, 'cache_read': 180,
                                            'cache_create': 0}
    assert min(u['in'] for u in s['usage_by_model'].values()) >= 0


# ── 10 · a later record cannot rewrite what an earlier one said ────────────

def test_a_later_record_cannot_rewrite_the_cwd_or_the_timestamp_extremes():
    """`session_meta` owns the cwd; the per-turn `turn_context` fills it only
    while it is empty — dropping `and not s['cwd']` at codex.py:209 lets a
    mid-session directory change rewrite the whole session's project. And the
    timestamps are extremes, not last-seen: a torn or malformed line must
    shift neither, while an `error` event is counted exactly once."""
    s = dict(sessions._EMPTY_STATS, models=[], usage_by_model={})
    codex.fold({'timestamp': '2026-09-14T10:00:00.000Z', 'type': 'session_meta',
                'payload': {'cwd': '\\\\?\\C:\\first'}}, s)
    codex.fold({'timestamp': '2026-09-14T11:00:00.000Z', 'type': 'turn_context',
                'payload': {'cwd': 'C:\\second', 'model': 'gpt-5.5'}}, s)
    assert s['cwd'] == 'C:\\first'                   # the FIRST cwd owns the session
    assert s['models'] == ['gpt-5.5']
    first_ts, last_ts = s['first_ts'], s['last_ts']
    assert first_ts is not None and last_ts == first_ts + 3600.0
    # a later line that is garbage cannot move either extreme
    codex.fold({'timestamp': 'not-a-date', 'type': 'event_msg',
                'payload': {'type': 'error'}}, s)
    codex.fold({'timestamp': '2026-99-99T99:99:99Z', 'type': 'turn_context',
                'payload': {'cwd': 'C:\\third'}}, s)
    assert (s['first_ts'], s['last_ts']) == (first_ts, last_ts)
    assert s['cwd'] == 'C:\\first' and s['api_errors'] == 1
    # an EARLIER timestamp arriving late still lowers the minimum
    codex.fold({'timestamp': '2026-09-14T09:30:00.000Z', 'type': 'event_msg',
                'payload': {'type': 'user_message', 'message': 'early'}}, s)
    assert s['first_ts'] == first_ts - 1800.0 and s['last_ts'] == last_ts
    assert s['count'] == 1 and s['preview'] == 'early'
    # and turn_context alone still fills an EMPTY cwd (the other half of :209)
    s2 = dict(sessions._EMPTY_STATS, models=[], usage_by_model={})
    codex.fold({'type': 'turn_context',
                'payload': {'cwd': '\\\\?\\UNC\\srv\\share'}}, s2)
    assert s2['cwd'] == '\\\\srv\\share'
