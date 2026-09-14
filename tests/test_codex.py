"""Codex as a second harness: its sessions, its projects, and the four seams
that now ask a harness instead of assuming Claude Code.

Everything here is built against the shape a real Codex install has on this
machine — a versioned `state_*.sqlite` whose `threads` table is the index, and
rollout JSONL named by that index rather than by the session id. The fixture is
a fake, but the schema is not invented: it is the column list `codex._COLS`
reads, and a rollout record is `{timestamp, type, payload}`.
"""
import json
import os
import sqlite3
import sys
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import harness
from harness import Sandbox
from claude_sessions import codex, config, harnesses, sessions, store

ROLLOUT_COLS = ('id', 'rollout_path', 'cwd', 'preview', 'first_user_message',
                'model', 'tokens_used', 'git_branch', 'archived',
                'updated_at_ms', 'created_at_ms')


def _rollout(path, cwd, turns=2, model='gpt-5.5', spend=0):
    """A rollout whose developer preamble is NOT a turn — the distinction the
    count exists for."""
    recs = [
        {'timestamp': '2026-09-14T22:14:01.000Z', 'type': 'session_meta',
         'payload': {'cwd': cwd}},
        {'timestamp': '2026-09-14T22:14:01.100Z', 'type': 'turn_context',
         'payload': {'model': model, 'cwd': cwd}},
        # the two that must NOT count: a rollout carries the developer
        # instructions and an <environment_context> block as response_items
        {'timestamp': '2026-09-14T22:14:01.200Z', 'type': 'response_item',
         'payload': {'type': 'message', 'role': 'developer'}},
        {'timestamp': '2026-09-14T22:14:01.300Z', 'type': 'response_item',
         'payload': {'type': 'message', 'role': 'user'}},
    ]
    for i in range(turns):
        # the noise a real turn carries on the SAME record type, measured from
        # a rollout on disk: a turn is bracketed by task_started/task_complete,
        # so `type == 'event_msg'` alone counts three events per exchange
        recs.append({'timestamp': '2026-09-14T22:15:%02d.000Z' % i,
                     'type': 'event_msg',
                     'payload': {'type': 'task_started', 'turn_id': 't%d' % i}})
        recs.append({'timestamp': '2026-09-14T22:15:%02d.500Z' % i,
                     'type': 'event_msg',
                     'payload': {'type': 'user_message',
                                 'message': 'do the thing %d' % i}})
        recs.append({'timestamp': '2026-09-14T22:16:%02d.000Z' % i,
                     'type': 'event_msg',
                     'payload': {'type': 'agent_message', 'message': 'done'}})
        recs.append({'timestamp': '2026-09-14T22:16:%02d.500Z' % i,
                     'type': 'event_msg',
                     'payload': {'type': 'task_complete', 'turn_id': 't%d' % i}})
        if spend:
            recs.append(_usage_rec(spend * (i + 1), 0, spend * (i + 1) // 10,
                                   '2026-09-14T22:16:%02d.600Z' % i))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for r in recs:
            f.write(json.dumps(r) + '\n')
    return path


def codex_home(root, threads, exe=True, spend=0):
    """A Codex home under *root* holding one state db and its rollouts.

    *threads* is [(sid, cwd, turns, archived)]. The binary is written too,
    because `harnesses.instances()` only offers a harness it can actually run —
    a home with no CLI is a leftover, not an installation.
    """
    home = os.path.join(str(root), '.codex')
    os.makedirs(home, exist_ok=True)
    con = sqlite3.connect(os.path.join(home, 'state_5.sqlite'))
    con.execute('CREATE TABLE threads (%s)' % ', '.join(ROLLOUT_COLS))
    for i, (sid, cwd, turns, archived) in enumerate(threads):
        path = _rollout(os.path.join(home, 'sessions', '2026', '09', '14',
                                     'rollout-%s.jsonl' % sid), cwd, turns,
                        spend=spend)
        con.execute('INSERT INTO threads VALUES (%s)' % ','.join('?' * len(ROLLOUT_COLS)),
                    (sid, path, cwd, 'ask %d' % i, 'ask %d' % i, 'gpt-5.5', 0,
                     'main', int(archived), 1789416868062 + i, 1789416841547 + i))
    con.commit()
    con.close()
    if exe:
        b = os.path.join(str(root), 'AppData', 'Local', 'OpenAI', 'Codex',
                         'bin', 'deadbeef00000000')
        os.makedirs(b, exist_ok=True)
        for name in ('codex.exe', 'codex'):
            open(os.path.join(b, name), 'w').close()
    return home


# ── the index is the session list ────────────────────────────

def test_a_project_is_known_because_the_index_says_so(monkeypatch, tmp_path):
    """Claude Code's record that a project exists is a DIRECTORY; Codex has no
    such directory. Walking the disk for one finds nothing at all."""
    sb = Sandbox(monkeypatch, tmp_path)
    home = codex_home(sb.root, [('s1', 'C:\\work\\alpha', 2, 0)])
    assert not os.path.isdir(os.path.join(home, 'projects'))
    projs = codex.projects(home)
    assert [p[1] for p in projs] == ['C:\\work\\alpha']


def test_the_extended_length_prefix_is_not_a_second_project(monkeypatch, tmp_path):
    """Codex records `\\\\?\\C:\\x` for some paths and `C:\\x` for others. The
    same project must encode to one folder, or it appears twice in the list."""
    sb = Sandbox(monkeypatch, tmp_path)
    home = codex_home(sb.root, [('s1', 'C:\\work\\alpha', 1, 0),
                                ('s2', '\\\\?\\C:\\work\\alpha', 1, 0)])
    assert len(codex.projects(home)) == 1


def test_a_rollout_counts_turns_and_not_the_preamble(monkeypatch, tmp_path):
    """`response_item` messages carry the developer instructions and the
    environment block with roles `developer` and `user`. Counting those reports
    three turns for a session in which the user said one thing."""
    sb = Sandbox(monkeypatch, tmp_path)
    home = codex_home(sb.root, [('s1', 'C:\\work\\alpha', 2, 0)])
    folder = store.project_folder(home, codex._enc('C:\\work\\alpha'))
    got = codex.scan(folder)
    assert len(got) == 1 and got[0][3] == 4        # 2 user + 2 agent, nothing else


def test_an_archived_thread_is_not_in_the_open_list(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    home = codex_home(sb.root, [('s1', 'C:\\work\\alpha', 1, 0),
                                ('s2', 'C:\\work\\alpha', 1, 1)])
    folder = store.project_folder(home, codex._enc('C:\\work\\alpha'))
    assert [r[1] for r in codex.scan(folder)] == ['s1']
    assert [r[1] for r in codex.scan(folder, archived=True)] == ['s2']


def test_a_locked_or_missing_database_is_no_sessions_not_an_error(
        monkeypatch, tmp_path):
    """Codex owns these files and holds them open while it runs. A session list
    is not worth blocking a UI thread for, and it is not an error worth
    showing either."""
    sb = Sandbox(monkeypatch, tmp_path)
    assert codex.projects(os.path.join(str(sb.root), 'nothing-here')) == []
    home = os.path.join(str(sb.root), '.codex')
    os.makedirs(home)
    open(os.path.join(home, 'state_5.sqlite'), 'w').write('not a database')
    assert codex.projects(home) == []


def test_the_newest_state_database_wins(monkeypatch, tmp_path):
    """The file name is versioned, so `state_6` will ship. Naming one freezes
    archeus at the version it was written against."""
    sb = Sandbox(monkeypatch, tmp_path)
    home = codex_home(sb.root, [('s1', 'C:\\work\\alpha', 1, 0)])
    open(os.path.join(home, 'state_6.sqlite'), 'w').close()
    assert codex.db_path(home).endswith('state_6.sqlite')


# ── the seams that stopped assuming Claude Code ──────────────

def test_a_transcript_is_named_by_the_index_not_by_the_session_id(
        monkeypatch, tmp_path):
    """`<folder>/<sid>.jsonl` is Claude Code's rule and only its rule. A Codex
    rollout lives under a date tree with a name the id cannot produce."""
    sb = Sandbox(monkeypatch, tmp_path)
    home = codex_home(sb.root, [('s1', 'C:\\work\\alpha', 1, 0)])
    folder = store.project_folder(home, codex._enc('C:\\work\\alpha'))
    p = store.transcript_path(folder, 's1')
    assert os.path.isfile(p)
    assert p != os.path.join(folder, 's1.jsonl')


def test_the_scan_and_the_fold_follow_the_home_the_file_is_under(
        monkeypatch, tmp_path):
    """One folder handle, two harnesses. `scan_sessions` and `_parse_session`
    keep their signatures; what they dispatch to is the home's business."""
    sb = Sandbox(monkeypatch, tmp_path)
    home = codex_home(sb.root, [('s1', 'C:\\work\\alpha', 2, 0)])
    folder = store.project_folder(home, codex._enc('C:\\work\\alpha'))
    rows = sessions.scan_sessions(folder)
    assert [r[1] for r in rows] == ['s1']
    st = sessions._parse_session(store.transcript_path(folder, 's1'))
    assert st['models'] == ['gpt-5.5'] and st['count'] == 4
    assert st['preview'].startswith('do the thing')
    assert st['cwd'] == 'C:\\work\\alpha'


def test_a_project_worked_in_under_both_clis_is_one_row(monkeypatch, tmp_path):
    """The encoded name is harness-independent, which is the whole reason a
    harness can ride on the home: the same project in Claude Code and in Codex
    is one row with two sources, not two projects."""
    sb = Sandbox(monkeypatch, tmp_path)
    from claude_sessions import gui
    actual = str(sb.root / 'work' / 'alpha')
    os.makedirs(actual, exist_ok=True)
    enc = codex._enc(actual)
    (sb.projects / enc).mkdir()
    codex_home(sb.root, [('s1', actual, 1, 0)])
    from claude_sessions import paths as paths_mod
    monkeypatch.setattr(paths_mod, 'find_actual_path',
                        lambda e, *a, **k: actual if e == enc else None)
    rows = gui.list_projects()
    assert len(rows) == 1
    assert sorted(rows[0]['accounts']) == ['Codex', 'default']


def test_a_home_that_does_not_have_the_project_is_not_offered(
        monkeypatch, tmp_path):
    """archeus's sidecar folder under a Codex home is created lazily, so its
    absence says nothing. Asking the index is the only answer there is."""
    sb = Sandbox(monkeypatch, tmp_path)
    codex_home(sb.root, [('s1', 'C:\\work\\alpha', 1, 0)])
    assert 'Codex' in dict(sessions.account_folders_for(codex._enc('C:\\work\\alpha')))
    assert 'Codex' not in dict(sessions.account_folders_for('X--nothing-here'))


def test_nothing_offers_a_harness_it_cannot_run(monkeypatch, tmp_path):
    """A home left behind by an uninstall is not an installation."""
    sb = Sandbox(monkeypatch, tmp_path)
    codex_home(sb.root, [('s1', 'C:\\work\\alpha', 1, 0)], exe=False)
    assert [h for _n, _d, h in harnesses.instances()] == ['claude']
    assert sessions.account_folders_for(codex._enc('C:\\work\\alpha')) == []


# ── the binary, which moves on every update ──────────────────

def test_the_newest_install_directory_wins(monkeypatch, tmp_path):
    """Codex installs under a directory named by a hash of the build and leaves
    the previous one in place. Resolving to the older one runs the version the
    user just replaced."""
    sb = Sandbox(monkeypatch, tmp_path)
    codex_home(sb.root, [])
    base = os.path.join(str(sb.root), 'AppData', 'Local', 'OpenAI', 'Codex', 'bin')
    newer = os.path.join(base, 'ffffffff00000000')
    os.makedirs(newer)
    for name in ('codex.exe', 'codex'):
        open(os.path.join(newer, name), 'w').close()
    os.utime(os.path.join(newer, 'codex.exe'), (2 ** 31, 2 ** 31))
    assert harnesses.exe('codex') == os.path.join(newer, 'codex.exe')


def test_the_search_stays_inside_the_profile_it_is_given(monkeypatch, tmp_path):
    """Written as a path RELATIVE to the user profile for exactly this reason:
    an absolute `expanduser` would find the real installation from inside a
    test, which is how the suite ended up listing the user's own projects."""
    Sandbox(monkeypatch, tmp_path)
    for d in harnesses.HARNESSES.values():
        for pat in d.get('exe_globs', ()):
            assert not os.path.isabs(pat) and '~' not in pat, pat
    assert harnesses.exe('codex') is None


# ── one walk ─────────────────────────────────────────────────

def test_every_project_list_comes_from_the_one_walk():
    """The same twenty lines stood in three modules, each producing
    `(mtime, path, enc, home)`. Three places a harness has to be remembered is
    three chances for the sidebar to show a project the terminal menu does not.
    """
    import inspect
    from claude_sessions import gui, gui_api, main
    for fn in (gui.list_projects, gui_api._entries, main.run):
        src = inspect.getsource(fn)
        assert 'projects_root' not in src, fn.__qualname__
        assert 'all_projects()' in src, fn.__qualname__


# ── the scratch directory is not a workspace ──────────────────

def test_a_probe_run_in_the_scratch_directory_is_not_a_project(monkeypatch, tmp_path):
    r"""The reported symptom, exactly: a one-shot `codex exec` in
    `%TEMP%\codexprobe` wrote the same session state a real project does, and
    the sidebar grew a tab for a directory that is gone by the next boot.

    It is filtered in `store.all_projects` and nowhere else — the rule is about
    what a project IS, not about which CLI recorded it, so a `claude -p` in the
    same directory has to vanish from the same edit.
    """
    sb = Sandbox(monkeypatch, tmp_path)
    from claude_sessions import gui

    real = str(sb.root / 'work' / 'alpha')
    probe = str(sb.tmp / 'codexprobe')
    for d in (real, probe):
        os.makedirs(d, exist_ok=True)

    # one of each harness, both in the scratch directory, plus a real project
    codex_home(sb.root, [('s1', probe, 1, 0), ('s2', real, 1, 0)])
    encs = {}
    for d in (real, probe):
        enc = codex._enc(d)
        encs[enc] = d
        (sb.projects / enc).mkdir()
        harness.make_jsonl(str(sb.projects / enc / ('%s.jsonl' % os.path.basename(d))))
    from claude_sessions import paths as paths_mod
    monkeypatch.setattr(paths_mod, 'find_actual_path', lambda e, *a, **k: encs.get(e))

    assert store.under_temp(probe) and not store.under_temp(real)
    assert {p for _m, p, _e, _h in store.all_projects()} == {real}
    assert [r['path'] for r in gui.list_projects()] == [real]


def test_the_scratch_filter_refuses_an_answer_that_would_hide_everything():
    """A filter that cannot be wrong about a probe directory can still be
    catastrophically wrong about a real one. `tempfile.gettempdir()` falls back
    to the working directory, and `config._TEMP` falls back to the user profile
    when neither TEMP nor TMP is set — filtering by either on such a machine
    hides every project the user has, with no error anywhere."""
    import tempfile
    for bad in (os.path.abspath(os.sep), config._USERPROFILE):
        with unittest.mock.patch.object(tempfile, 'tempdir', bad):
            assert store.temp_root() == ''
            assert not store.under_temp(os.path.join(bad, 'anything'))


# ── token spend ──────────────────────────────────────────────

def _usage_rec(total_in, cached, out, ts='2026-09-14T22:16:00.000Z'):
    """A `token_count` event, in the shape the binary's own type declarations
    give: `TokenCountEvent {info, rate_limits}`, `TokenUsageInfo
    {total_token_usage, last_token_usage, model_context_window}`, `TokenUsage
    {input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens,
    total_tokens}`."""
    u = {'input_tokens': total_in, 'cached_input_tokens': cached,
         'output_tokens': out, 'reasoning_output_tokens': out // 2,
         'total_tokens': total_in + out}
    # deliberately NOT the same object as the total. The two are different
    # numbers in a real rollout, and reading the wrong one is a mistake no
    # fixture that shares one dict between them can ever show.
    last = {'input_tokens': 7, 'cached_input_tokens': 3, 'output_tokens': 5,
            'reasoning_output_tokens': 2, 'total_tokens': 12}
    return {'timestamp': ts, 'type': 'event_msg',
            'payload': {'type': 'token_count',
                        'info': {'total_token_usage': u, 'last_token_usage': last,
                                 'model_context_window': 258400},
                        'rate_limits': None}}


def _parse(tmp_path, recs, name='rollout-x.jsonl'):
    p = os.path.join(str(tmp_path), name)
    with open(p, 'w', encoding='utf-8') as f:
        for r in recs:
            f.write(json.dumps(r) + '\n')
    s = dict(sessions._EMPTY_STATS)
    s['usage_by_model'], s['models'] = {}, []
    for r in recs:
        codex.fold(r, s)
    return s


def test_a_cumulative_total_is_banked_as_a_delta(tmp_path):
    """`total_token_usage` is the SESSION's running total, not the turn's. One
    event per turn summed the way Claude Code's per-message usage is summed
    multiplies a session's spend by its turn count — three turns of a session
    that spent 300 would have reported 1800."""
    s = _parse(tmp_path, [
        {'timestamp': '2026-09-14T22:14:01.100Z', 'type': 'turn_context',
         'payload': {'model': 'gpt-5.5'}},
        _usage_rec(100, 40, 20),      # cumulative after turn 1
        _usage_rec(250, 100, 55),     # after turn 2
        _usage_rec(400, 160, 90),     # after turn 3
    ])
    assert s['usage_by_model'] == {'gpt-5.5': {
        'in': 240,            # 400 input - 160 cached: the non-cached half
        'out': 90,
        'cache_read': 160,
        'cache_create': 0,    # this provider does not bill a cache write
    }}


def test_reasoning_tokens_are_not_added_a_second_time(tmp_path):
    """`reasoning_output_tokens` is a SUBSET of `output_tokens`, not a sibling
    of it — the binary exports `non_cached_input_tokens` as its own metric for
    input and no such thing for output. Adding it counts the thinking twice."""
    s = _parse(tmp_path, [_usage_rec(100, 0, 60)])
    assert s['usage_by_model']['codex']['out'] == 60


def test_a_session_that_switched_model_bills_each_one_its_own_stretch(tmp_path):
    """The model is named per TURN. Attribution follows `models[-1]`, so a
    session that went A, B, A has to bill the third stretch back to A rather
    than leaving A at whatever it stood at when B took over."""
    tc = lambda m: {'timestamp': '2026-09-14T22:14:01.100Z',
                    'type': 'turn_context', 'payload': {'model': m}}
    s = _parse(tmp_path, [tc('a'), _usage_rec(100, 0, 10),
                          tc('b'), _usage_rec(300, 0, 30),
                          tc('a'), _usage_rec(600, 0, 60)])
    assert s['models'] == ['b', 'a']
    assert s['usage_by_model']['a']['in'] == 100 + 300
    assert s['usage_by_model']['b']['in'] == 200
    assert sum(u['in'] for u in s['usage_by_model'].values()) == 600


def test_the_fold_adds_no_field_the_cache_would_reject(tmp_path):
    """A delta needs to know what it has already banked, and the obvious place
    to keep that is a scratch key on `s`. It cannot be: `_disk_cache_hit`
    compares a cached entry's keys against `_EMPTY_STATS` and would throw away
    every entry carrying an extra one — silently, forever."""
    s = _parse(tmp_path, [_usage_rec(100, 40, 20)])
    assert s.keys() == sessions._EMPTY_STATS.keys()


def test_a_rollout_that_restarts_its_count_never_banks_a_negative(tmp_path):
    s = _parse(tmp_path, [_usage_rec(500, 0, 50), _usage_rec(100, 0, 10)])
    assert s['usage_by_model']['codex'] == {
        'in': 500, 'out': 50, 'cache_read': 0, 'cache_create': 0}


# ── search, usage and the dashboard ──────────────────────────

def test_the_corpus_walk_finds_a_session_whose_transcript_is_elsewhere(monkeypatch, tmp_path):
    """`stats.iter_all_sessions` is what search, usage and the dashboard all
    read through, and it listed `*.jsonl` in the project folder. A Codex thread
    keeps an index there and its transcript somewhere else entirely, so all
    three saw a project with no sessions at all — no error, just a zero.
    """
    sb = Sandbox(monkeypatch, tmp_path)
    from claude_sessions import stats as stats_mod

    actual = str(sb.root / 'work' / 'alpha')
    os.makedirs(actual, exist_ok=True)
    home = codex_home(sb.root, [('s1', actual, 2, 0)], spend=1000)
    enc = codex._enc(actual)
    folder = os.path.join(home, 'projects', enc)
    os.makedirs(folder, exist_ok=True)

    rows = list(stats_mod.iter_all_sessions([(0, actual, enc, home)], silent=True))
    assert [r[3] for r in rows] == ['s1']
    assert rows[0][4]['count'] == 4                      # two exchanges
    assert rows[0][4]['usage_by_model']['gpt-5.5']['in'] == 2000   # cumulative


def test_codex_spend_reaches_the_usage_table(monkeypatch, tmp_path):
    """The whole point of the two edits above: a Codex project is a row in the
    usage table with real numbers, not a row reading zero."""
    sb = Sandbox(monkeypatch, tmp_path)
    from claude_sessions import stats as stats_mod

    actual = str(sb.root / 'work' / 'alpha')
    os.makedirs(actual, exist_ok=True)
    home = codex_home(sb.root, [('s1', actual, 2, 0)], spend=1000)
    enc = codex._enc(actual)
    os.makedirs(os.path.join(home, 'projects', enc), exist_ok=True)

    rows = stats_mod.assemble_project_usage([(0, actual, enc, home)])
    assert len(rows) == 1
    assert rows[0]['sessions'] == 1
    assert rows[0]['usage']['in'] == 2000
    assert rows[0]['usage']['out'] == 200
    assert 'gpt-5.5' in rows[0]['usage_by_model']


# ── launching Codex ──────────────────────────────────────────

def test_the_argv_is_codexs_own_vocabulary(monkeypatch, tmp_path):
    """Not a translation of Claude Code's. Every verb here is checked against
    `codex --help` on the installed binary: `resume [SESSION_ID]`, `--last` for
    the most recent, `fork` the same shape, and a bare `codex` for a new one."""
    argv = codex.launch_argv('codex.exe', 'new', {}, 'D:/p')
    assert argv == ['codex.exe', '-C', 'D:/p']
    assert codex.launch_argv('codex.exe', 'continue', {}, '')[1:] == ['resume', '--last']
    assert codex.launch_argv('codex.exe', 'resume:abc', {}, '')[1:] == ['resume', 'abc']
    assert codex.launch_argv('codex.exe', 'fork:abc', {}, '')[1:] == ['fork', 'abc']
    assert codex.launch_argv('codex.exe', 'resume-named::abc::x', {}, '')[1:] \
        == ['resume', 'abc']


def test_reasoning_effort_is_a_config_key_not_a_flag():
    """`-c` layers one value over config.toml, which is the documented way to
    set this per invocation. There is no `--effort`."""
    argv = codex.launch_argv('codex.exe', 'new', {'effort': 'high'}, '')
    assert argv[1:3] == ['-c', 'model_reasoning_effort=high']


def test_a_permission_mode_with_no_equivalent_is_dropped_not_rounded():
    """Claude Code's permission modes and Codex's approval policies are two
    vocabularies over the same idea, and they do not line up. `plan` and
    `acceptEdits` have no equivalent — Codex varies its SANDBOX, not the edit
    gate — so Codex keeps its own default rather than being handed the
    closest-looking value."""
    assert '-a' in codex.launch_argv('codex.exe', 'new', {'perm': 'default'}, '')
    for orphan in ('plan', 'acceptEdits', 'auto', ''):
        assert '-a' not in codex.launch_argv('codex.exe', 'new', {'perm': orphan}, '')


def test_the_launch_path_asks_the_harness_for_its_argv(monkeypatch, tmp_path):
    """The one gate that matters: `build_launch_command` is a hundred and forty
    lines of Claude Code's flags, and a Codex home must not reach any of them.
    The dispatch sits below everything harness-neutral — the project folder, the
    extra PATH, the telemetry, the home — and above the first `claude` flag."""
    sb = Sandbox(monkeypatch, tmp_path)
    from claude_sessions import main as main_mod
    home = codex_home(sb.root, [('s1', 'C:/work/alpha', 1, 0)])
    args, env, _folder = main_mod.build_launch_command(
        'C:/work/alpha', codex._enc('C:/work/alpha'), 'resume:s1',
        {'cfgdir': home, 'effort': 'high', 'model': 'gpt-5.5', 'perm': 'default',
         'name': 'x', 'worktree': '*'})
    assert os.path.basename(args[0]).startswith('codex')
    assert args[1:3] == ['resume', 's1']
    assert '--session-id' not in args and '--permission-mode' not in args
    # the home variable is Codex's, and CLAUDE_CONFIG_DIR is not pinned to it
    assert env['CODEX_HOME'] == home
    assert env.get('CLAUDE_CONFIG_DIR') != home


def test_a_new_codex_session_has_no_id_to_choose(monkeypatch, tmp_path):
    """Claude Code takes `--session-id`, which is the only way archeus can know
    a new session's id before a line is written. Codex has no such flag, so the
    id is Codex's to mint and archeus learns it from the index — which is why
    nothing is recorded against one here."""
    assert '--session-id' not in codex.launch_argv('codex.exe', 'new', {}, '')
