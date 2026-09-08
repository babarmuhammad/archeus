"""Loops: the one Claude Code offers, and the one archeus adds.

A `/loop` is session-scoped — it fires only while its session is open and idle,
and has no documented state file — so the first half of these tests is about not
overclaiming: the registry holds what archeus itself started, "running" means
the process, and the turn count comes from the transcript.

The second half is the background kind, which exists because the first is no use
with everything closed. It is an OS scheduler entry running headless `claude -p`,
and the tests there are mostly about the guardrails, because those have to live
inside the thing the scheduler runs: nobody is watching a task that fires every
fifteen minutes for a week.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox

from claude_sessions import loops, main as main_mod, proc



class _Ok:
    """A CompletedProcess stand-in — proc.run returns one of these or None."""

    def __init__(self, stdout='', stderr='', returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


# ── the command ──────────────────────────────────────────────

def test_the_command_follows_the_documented_grammar():
    """Each combination means something different to Claude Code: an interval
    with a prompt is a fixed schedule, a prompt alone is self-paced, and neither
    runs loop.md. Getting this wrong silently changes what the loop does."""
    assert loops.loop_prompt('15m', 'check CI') == '/loop 15m check CI'
    assert loops.loop_prompt('', 'check CI') == '/loop check CI'
    assert loops.loop_prompt('15m', '') == '/loop 15m'
    assert loops.loop_prompt('', '') == '/loop'


def test_the_opening_prompt_reaches_the_command_line(monkeypatch, tmp_path):
    """`claude "<text>"` submits the first turn and stays interactive — the
    whole mechanism behind starting a loop, since there is nothing else to
    start but a session that begins by typing it."""
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, _folder, _sids = sb.add_project('alpha', n_sessions=1)
    opts = {'effort': '', 'model': '', 'perm': '', 'name': '', 'worktree': '',
            'agent': '', 'cfgdir': '', 'max_thinking': '', 'subagent_model': '',
            'prompt': '/loop 15m check CI'}
    args, _env, _f = main_mod.build_launch_command(actual, enc, 'new', opts)
    assert args[-1] == '/loop 15m check CI', args
    # …and only when asked for: an ordinary launch must not type anything
    opts['prompt'] = ''
    plain, _e, _f2 = main_mod.build_launch_command(actual, enc, 'new', opts)
    assert plain[-1] != '/loop 15m check CI'


# ── the registry ─────────────────────────────────────────────

def test_a_loop_is_recorded_where_the_account_lives(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, _f, _s = sb.add_project('alpha', n_sessions=1)
    row = loops.record(actual, enc, str(sb.cfg), '15m', 'check CI', 4242)
    assert row['text'] == '/loop 15m check CI'
    assert os.path.isfile(loops.registry_path(str(sb.cfg)))
    got = loops.listing(str(sb.cfg))
    assert len(got) == 1 and got[0]['id'] == row['id']


def test_running_means_the_process_is_alive(monkeypatch, tmp_path):
    """A loop has no state archeus can read. What it CAN read is whether the
    session it launched is still there, so that is what the board reports."""
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, _f, _s = sb.add_project('alpha', n_sessions=1)
    loops.record(actual, enc, str(sb.cfg), '', '', 4242)
    monkeypatch.setattr(proc, 'pid_alive', lambda pid: True)
    assert loops.listing(str(sb.cfg))[0]['running'] is True
    monkeypatch.setattr(proc, 'pid_alive', lambda pid: False)
    assert loops.listing(str(sb.cfg))[0]['running'] is False


def test_iterations_are_counted_from_the_transcript(monkeypatch, tmp_path):
    """Each fire is a turn in the session's own transcript — the only record of
    one that exists outside the session."""
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _sids = sb.add_project('alpha', n_sessions=0)
    started = time.time() - 600
    jsonl = os.path.join(folder, 'bbbb0000-0000-0000-0000-000000000000.jsonl')
    with open(jsonl, 'w', encoding='utf-8') as f:
        for i in range(3):
            stamp = time.strftime('%Y-%m-%dT%H:%M:%SZ',
                                  time.gmtime(started + 60 * (i + 1)))
            f.write(json.dumps({'type': 'assistant', 'timestamp': stamp,
                                'message': {'role': 'assistant',
                                            'content': [{'type': 'text', 'text': 'x'}]}}) + '\n')
        # one turn from BEFORE the loop started must not be counted
        old = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(started - 3600))
        f.write(json.dumps({'type': 'assistant', 'timestamp': old,
                            'message': {'role': 'assistant', 'content': []}}) + '\n')
    row = loops.record(actual, enc, str(sb.cfg), '', 'x', 4242)
    row['started'] = started
    monkeypatch.setattr(proc, 'pid_alive', lambda pid: True)
    monkeypatch.setattr(loops, '_load', lambda cfgdir=None: [row])
    got = loops.listing(str(sb.cfg))[0]
    assert got['iterations'] == 3, got
    assert got['last_activity'] >= 0


def test_stopping_ends_the_session_and_says_so(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, _f, _s = sb.add_project('alpha', n_sessions=1)
    row = loops.record(actual, enc, str(sb.cfg), '', '', 4242)
    killed = []
    monkeypatch.setattr(proc, 'pid_alive', lambda pid: True)
    monkeypatch.setattr(proc, 'kill_tree', lambda p: killed.append(p.pid))
    ok, msg = loops.stop(row['id'], str(sb.cfg))
    assert ok and killed == [4242] and 'ended' in msg.lower()
    assert loops.listing(str(sb.cfg))[0]['running'] is False


def test_stopping_something_already_gone_is_not_an_error(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, _f, _s = sb.add_project('alpha', n_sessions=1)
    row = loops.record(actual, enc, str(sb.cfg), '', '', 4242)
    monkeypatch.setattr(proc, 'pid_alive', lambda pid: False)
    ok, msg = loops.stop(row['id'], str(sb.cfg))
    assert ok and 'already' in msg


def test_a_loop_with_no_process_handle_is_refused(monkeypatch, tmp_path):
    """Never kill a pid archeus did not record — 0 is not a process."""
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, _f, _s = sb.add_project('alpha', n_sessions=1)
    row = loops.record(actual, enc, str(sb.cfg), '', '', 0)
    killed = []
    monkeypatch.setattr(proc, 'kill_tree', lambda p: killed.append(p.pid))
    ok, msg = loops.stop(row['id'], str(sb.cfg))
    assert not ok and not killed and 'handle' in msg


def test_forgetting_removes_the_row_and_nothing_else(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, _f, _s = sb.add_project('alpha', n_sessions=1)
    row = loops.record(actual, enc, str(sb.cfg), '', '', 4242)
    killed = []
    monkeypatch.setattr(proc, 'kill_tree', lambda p: killed.append(p.pid))
    loops.forget(row['id'], str(sb.cfg))
    assert loops.listing(str(sb.cfg)) == [] and not killed


def test_the_registry_does_not_grow_without_bound(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, _f, _s = sb.add_project('alpha', n_sessions=1)
    for _ in range(loops.MAX_KEPT + 5):
        loops.record(actual, enc, str(sb.cfg), '', '', 1)
    assert len(loops.listing(str(sb.cfg), with_activity=False)) == loops.MAX_KEPT


# ── the background kind ──────────────────────────────────────
#
# The point of this half: it must keep firing with archeus closed and no
# session anywhere. That means an OS scheduler entry, which also means every
# guardrail has to live in the thing the scheduler runs — the UI is not there.

def test_the_interval_becomes_a_schedule_the_os_understands():
    assert loops._interval_minutes('15m') == 15
    assert loops._interval_minutes('2h') == 120
    assert loops._interval_minutes('1d') == 1440
    assert loops._interval_minutes('30s') == 1        # cron/schtasks floor
    assert loops._interval_minutes('') == 60          # unparseable errs upward
    assert loops._interval_minutes('999d') == 7 * 1440


def test_windows_registers_a_task_with_no_stored_password(monkeypatch):
    """`/ru` would mean prompting for and storing a password. Running as the
    logged-on user is the right trade for a developer tool, and the UI says the
    loop fires while you are logged in."""
    seen = []
    monkeypatch.setattr(loops.proc, 'WINDOWS', True)
    monkeypatch.setattr(loops.proc, 'run',
                        lambda argv, **kw: seen.append(argv) or _Ok())
    ok, msg = loops.schedule('abc123', '15m', 'C:/acct')
    assert ok and 'schtasks' in seen[0][0]
    argv = seen[0]
    assert '/create' in argv and '/tn' in argv and 'archeus-loop-abc123' in argv
    assert '/sc' in argv and argv[argv.index('/sc') + 1] == 'minute'
    assert argv[argv.index('/mo') + 1] == '15'
    assert '/ru' not in argv, 'never ask for a password'
    cmd = argv[argv.index('/tr') + 1]
    assert '--loop-run' in cmd and 'abc123' in cmd and '--cfgdir' in cmd


def test_an_hourly_interval_is_scheduled_hourly(monkeypatch):
    seen = []
    monkeypatch.setattr(loops.proc, 'WINDOWS', True)
    monkeypatch.setattr(loops.proc, 'run', lambda argv, **kw: seen.append(argv) or _Ok())
    loops.schedule('x', '2h', '')
    assert seen[0][seen[0].index('/sc') + 1] == 'hourly'


def test_posix_rewrites_the_crontab_and_keeps_everyone_elses_lines(monkeypatch):
    """It is the user's crontab: every line that is not ours survives, the same
    read-modify-write discipline settings.json gets."""
    state = {'tab': '0 9 * * * backup.sh\n'}

    def fake(argv, **kw):
        if argv[:2] == ['crontab', '-l']:
            return _Ok(state['tab'])
        if argv[:2] == ['crontab', '-']:
            state['tab'] = kw.get('stdin') or ''
            return _Ok()
        return _Ok()
    monkeypatch.setattr(loops.proc, 'WINDOWS', False)
    monkeypatch.setattr(loops.proc, 'run', fake)

    ok, _ = loops.schedule('abc123', '15m', '')
    assert ok
    assert 'backup.sh' in state['tab']
    assert '*/15 * * * *' in state['tab'] and '# archeus-loop-abc123' in state['tab']

    ok, _ = loops.unschedule('abc123')
    assert ok
    assert 'backup.sh' in state['tab'] and 'archeus-loop-abc123' not in state['tab']


def test_a_run_is_headless_with_the_permission_mode_it_was_given(monkeypatch, tmp_path):
    """`claude -p` starts in Manual mode, so an unattended run does nothing
    unless it is told what it may do — and NEVER --bare, which skips hooks,
    skills, CLAUDE.md and memory: everything archeus provisions."""
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, _f, _s = sb.add_project('alpha', n_sessions=1)
    row = loops.record(actual, enc, str(sb.cfg), '15m', 'check CI', 0,
                       kind='schedule', perm='dontAsk')
    seen = {}

    def fake(argv, **kw):
        seen['argv'] = argv
        seen['kw'] = kw
        return _Ok('{"result":"nothing to do","total_cost_usd":0.02,'
                   '"session_id":"sid-1"}')
    monkeypatch.setattr(loops.proc, 'run', fake)
    monkeypatch.setattr(loops.proc, 'WINDOWS', True)
    assert loops.run_once(row['id'], str(sb.cfg)) == 0

    argv = seen['argv']
    assert '-p' in argv and '--output-format' in argv
    assert argv[argv.index('--permission-mode') + 1] == 'dontAsk'
    assert '--bare' not in argv
    assert seen['kw']['stdin'] == 'check CI', 'the prompt goes on stdin, not the argv'
    assert seen['kw']['cwd'] == actual
    assert seen['kw']['env']['CLAUDE_CONFIG_DIR'] == str(sb.cfg), 'the account picker'

    got = loops.listing(str(sb.cfg))[0]
    assert got['runs'] == 1 and got['last_cost'] == 0.02
    assert got['last_result'] == 'nothing to do' and got['journal']


def test_an_expired_loop_unschedules_itself(monkeypatch, tmp_path):
    """The guardrail lives in the runner, not the UI: a forgotten task is
    exactly the case where nobody is looking at a board."""
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, _f, _s = sb.add_project('alpha', n_sessions=1)
    row = loops.record(actual, enc, str(sb.cfg), '15m', 'x', 0, kind='schedule')
    rows = loops._load(str(sb.cfg))
    rows[-1]['expires'] = time.time() - 1
    loops._save(rows, str(sb.cfg))
    removed, ran = [], []
    monkeypatch.setattr(loops, 'unschedule', lambda i: removed.append(i) or (True, ''))
    monkeypatch.setattr(loops.proc, 'run', lambda *a, **kw: ran.append(a) or _Ok())
    assert loops.run_once(row['id'], str(sb.cfg)) == 0
    assert removed == [row['id']] and not ran, 'an expired loop must not spend money'
    assert loops.listing(str(sb.cfg))[0]['stopped']


def test_the_record_in_claude_md_is_rewritten_not_appended(monkeypatch, tmp_path):
    """Every scheduled run is a FRESH session, so this block is how the next one
    knows what the last ones did. It is read on every turn of every session in
    the project, so it must never grow."""
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, _f, _s = sb.add_project('alpha', n_sessions=1)
    with open(os.path.join(actual, 'CLAUDE.md'), 'w', encoding='utf-8') as f:
        f.write('# alpha\n\nMy own notes.\n')
    row = loops.record(actual, enc, str(sb.cfg), '15m', 'x', 0, kind='schedule')
    n = 0

    def fake(argv, **kw):
        return _Ok('{"result":"did thing %d","total_cost_usd":0.01}' % n
                   if '-p' in argv else '')
    monkeypatch.setattr(loops.proc, 'run', fake)
    for n in range(8):
        loops.run_once(row['id'], str(sb.cfg))
    md = open(os.path.join(actual, 'CLAUDE.md'), encoding='utf-8').read()
    assert md.count('ARCHEUS:LOOP:START') == 1, 'appended instead of rewritten'
    assert md.count('- 20') == loops.JOURNAL_IN_MD, 'the block grew past its cap'
    assert 'did thing 7' in md and 'did thing 0' not in md, 'newest first'
    assert 'My own notes.' in md, 'the user\'s own text survives every rewrite'


def test_a_failed_run_notifies(monkeypatch, tmp_path):
    """Nobody is watching a background loop. A run that fails every fifteen
    minutes in silence is the failure mode this exists to prevent."""
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, _f, _s = sb.add_project('alpha', n_sessions=1)
    row = loops.record(actual, enc, str(sb.cfg), '15m', 'x', 0, kind='schedule')
    sent = []
    monkeypatch.setattr(loops.proc, 'run',
                        lambda *a, **kw: _Ok('', 'model refused', 1))
    from claude_sessions import notify
    monkeypatch.setattr(notify, 'send', lambda t, m='': sent.append((t, m)))
    assert loops.run_once(row['id'], str(sb.cfg)) == 1
    assert sent and 'alpha' in sent[0][0]
    assert loops.listing(str(sb.cfg))[0]['last_error']


def test_a_scheduled_loop_with_no_prompt_runs_loop_md(monkeypatch, tmp_path):
    """Same precedence `/loop` applies — project loop.md over the account one —
    and read at RUN time, so editing it changes the next iteration."""
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, _f, _s = sb.add_project('alpha', n_sessions=1)
    os.makedirs(os.path.join(actual, '.claude'), exist_ok=True)
    with open(os.path.join(actual, '.claude', 'loop.md'), 'w', encoding='utf-8') as f:
        f.write('Check the release PR.\n')
    row = loops.record(actual, enc, str(sb.cfg), '15m', '', 0, kind='schedule')
    seen = {}
    monkeypatch.setattr(loops.proc, 'run',
                        lambda argv, **kw: seen.update(kw) or _Ok('{"result":"ok"}'))
    loops.run_once(row['id'], str(sb.cfg))
    assert seen['stdin'].strip() == 'Check the release PR.'


def test_stopping_a_scheduled_loop_removes_the_task(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, _f, _s = sb.add_project('alpha', n_sessions=1)
    row = loops.record(actual, enc, str(sb.cfg), '15m', 'x', 0, kind='schedule')
    killed, removed = [], []
    monkeypatch.setattr(loops.proc, 'kill_tree', lambda p: killed.append(p))
    monkeypatch.setattr(loops, 'unschedule', lambda i: removed.append(i) or (True, 'gone'))
    ok, _msg = loops.stop(row['id'], str(sb.cfg))
    assert ok and removed == [row['id']] and not killed


# ── the endpoint ─────────────────────────────────────────────

def test_start_launches_a_session_and_records_it(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, _f, _s = sb.add_project('alpha', n_sessions=1)
    from claude_sessions import gui, gui_api
    seen = {}

    def _fake(path, encoded, choice, opts, want_pid=False):
        seen.update(path=path, choice=choice, prompt=opts.get('prompt'))
        return (True, '', 777) if want_pid else (True, '')
    monkeypatch.setattr(gui, 'launch_session', _fake)
    r = gui_api.api_loop_start({}, {'path': actual, 'enc': enc,
                                    'cfgdir': str(sb.cfg), 'interval': '15m',
                                    'prompt': 'check CI'})
    assert r['ok'] and r['text'] == '/loop 15m check CI'
    assert seen['prompt'] == '/loop 15m check CI' and seen['choice'] == 'new'
    assert loops.listing(str(sb.cfg))[0]['pid'] == 777


def test_start_without_a_project_is_a_bad_request(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    from claude_sessions import gui_api
    try:
        gui_api.api_loop_start({}, {})
    except gui_api.BadRequest:
        return
    raise AssertionError('a loop with no project must be a 400')
