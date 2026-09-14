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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox
from claude_sessions import codex, harnesses, sessions, store

ROLLOUT_COLS = ('id', 'rollout_path', 'cwd', 'preview', 'first_user_message',
                'model', 'tokens_used', 'git_branch', 'archived',
                'updated_at_ms', 'created_at_ms')


def _rollout(path, cwd, turns=2, model='gpt-5.5'):
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
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for r in recs:
            f.write(json.dumps(r) + '\n')
    return path


def codex_home(root, threads, exe=True):
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
                                     'rollout-%s.jsonl' % sid), cwd, turns)
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
