"""T-826: pins on `archeus/harnesses/hook.py` that fail on the wrong code.

Every test here names a security-relevant branch of the hook (the identity
guards, the sentinels, the mailbox, the fail-closed answers) and fails if that
branch is inverted, removed or loosened; each was mutation-verified against a
scratch copy of the module under `/work/scratch` only. Nothing runs a process,
the network or a Windows API: the module is called in-process, its environment
is a plain dict, and every file is written as bytes with explicit content.

Covered elsewhere and pinned here only as a control: the halt JSON shape
(test_settings_sources_units E17, test_execution E49), the deny's exit-2
protocol (E16), the ACTIVE guard and a plainly forged id (E48), the timeout
halt itself (E19, E47).
"""

import io
import json
import os
import threading
import time

import pytest

from archeus.harnesses import hook

EID = 'exe_0' + 'A' * 25
TOKEN = 'hook_' + 'k' * 20
NO_ANSWER = 'Archeus did not answer; denied and halted (fail closed)'
NONCE = '07' * 16
NO_ID = 'this process has no Archeus execution identity'
GOOD = {'tool_name': 'Read', 'tool_input': {'file_path': 'a'}, 'cwd': 'w'}


def _exec_dir(tmp_path):
    return tmp_path / 'run' / 'exec' / EID


def _env(tmp_path, **drops):
    env = {'ARCHEUS_HOME': str(tmp_path), 'ARCHEUS_EXECUTION_ID': EID,
           'ARCHEUS_HOOK_TOKEN': TOKEN}
    for name in drops:
        env.pop(name)
    return env


def _run(tmp_path, monkeypatch, payload=None, env=None, wait=0.2):
    monkeypatch.setattr(hook, 'WAIT_S', wait)
    monkeypatch.setattr(hook, 'POLL_S', 0.01)
    monkeypatch.setattr(hook.os, 'urandom', lambda n: b'' * n)
    return hook.run(dict(GOOD, **(payload or {})), env or _env(tmp_path))


def _answer(tmp_path, seq, body, where='res'):
    d = _exec_dir(tmp_path) / where
    d.mkdir(parents=True, exist_ok=True)
    if isinstance(body, dict):
        body = dict(body, nonce=NONCE, digest=hook.request_digest(
            {'token': TOKEN, 'tool': 'Read', 'input': {'file_path': 'a'}, 'cwd': 'w',
             'nonce': NONCE, 'seq': seq}))
    raw = body if isinstance(body, bytes) else json.dumps(body).encode('utf-8')
    (d / ('%d.res.json' % seq)).write_bytes(raw)


def _reqs(tmp_path):
    req = _exec_dir(tmp_path) / 'req'
    return sorted(os.listdir(req)) if req.is_dir() else []


def _halted(tmp_path):
    with open(_exec_dir(tmp_path) / 'req' / 'halted.json', encoding='utf-8') as f:
        return json.load(f)


# ── the identity guards ───────────────────────────────────────────────────────

BAD_IDS = [('suffix', EID + 'x'),
           ('long', EID + 'A'),
           ('short', EID[:-1]),
           ('lower', 'exe_0' + 'a' * 25),
           ('confusable', 'exe_0' + 'I' * 25),
           ('time-overflow', 'exe_8' + 'A' * 25),
           ('plain', 'not-an-id')]


@pytest.mark.parametrize('bad', [v for _, v in BAD_IDS], ids=[i for i, _ in BAD_IDS])
def test_a_near_miss_execution_id_is_refused(tmp_path, monkeypatch, bad):
    env = _env(tmp_path)
    env['ARCHEUS_EXECUTION_ID'] = bad
    assert _run(tmp_path, monkeypatch, env=env) == ('halt', NO_ID)
    assert _reqs(tmp_path) == []


def test_the_exact_execution_id_is_accepted(tmp_path, monkeypatch):
    assert _run(tmp_path, monkeypatch) == ('halt', NO_ANSWER)


@pytest.mark.parametrize('missing',
                         ['ARCHEUS_HOME', 'ARCHEUS_HOOK_TOKEN', 'ARCHEUS_EXECUTION_ID'],
                         ids=['no-home', 'no-token', 'no-id'])
def test_every_identity_part_is_required(tmp_path, monkeypatch, missing):
    assert _run(tmp_path, monkeypatch,
                env=_env(tmp_path, **{missing: None})) == ('halt', NO_ID)


@pytest.mark.parametrize('missing',
                         ['ARCHEUS_HOME', 'ARCHEUS_HOOK_TOKEN', 'ARCHEUS_EXECUTION_ID'],
                         ids=['empty-home', 'empty-token', 'empty-id'])
def test_an_empty_identity_part_is_required_too(tmp_path, monkeypatch, missing):
    env = _env(tmp_path)
    env[missing] = ''
    assert _run(tmp_path, monkeypatch, env=env) == ('halt', NO_ID)


# ── PreCompact: recorded, never asked ─────────────────────────────────────────

def test_precompact_is_recorded_and_compacts(tmp_path, monkeypatch):
    assert _run(tmp_path, monkeypatch,
                {'hook_event_name': 'PreCompact', 'trigger': 'auto'}) == ('continue', '')
    assert _reqs(tmp_path) == ['precompact.json']
    with open(_exec_dir(tmp_path) / 'req' / 'precompact.json', encoding='utf-8') as f:
        rec = json.load(f)
    assert rec['trigger'] == 'auto' and 'at' in rec


def test_any_other_hook_event_asks_core(tmp_path, monkeypatch):
    assert _run(tmp_path, monkeypatch, {'hook_event_name': 'PreToolUse'}) == ('halt', NO_ANSWER)
    assert _reqs(tmp_path) == ['1.lock', '1.req.json', 'halted.json']


# ── decision / answer: what may leave on stdout ───────────────────────────────

def test_continue_answers_the_empty_object():
    assert hook.decision('continue') == {}


def test_allow_answers_with_the_allow_decision_only():
    assert hook.decision('allow') == {
        'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'allow'}}


@pytest.mark.parametrize('kind', ['deny', '', 'ALLOW', 'halt '],
                         ids=['deny', 'empty', 'upper-allow', 'padded-halt'])
def test_only_allow_halt_and_continue_answer_on_stdout(kind):
    with pytest.raises(ValueError):
        hook.decision(kind)


def test_the_deny_speaks_stderr_and_its_default_reason():
    assert hook.answer('deny', '') == ('', 'denied by Archeus', 2)
    assert hook.answer('deny', 'nope') == ('', 'nope', 2)


def test_an_empty_halt_reason_gets_the_named_one():
    out, err, code = hook.answer('halt', '')
    assert (out, err, code) == (json.dumps(hook.decision('halt', 'halted by Archeus')), '', 0)
    assert json.loads(out)['stopReason'] == 'halted by Archeus'


# ── the mailbox: _mailbox, _halted, the sequence ──────────────────────────────

def test_the_mailbox_is_made_once_and_never_remade(tmp_path, monkeypatch):
    missing = tmp_path / 'gone'
    hook._mailbox(str(missing))
    assert missing.is_dir()
    real_makedirs = hook.os.makedirs

    def refused(*args, **kwargs):
        raise OSError(13, '')
    monkeypatch.setattr(hook.os, 'makedirs', refused)
    hook._mailbox(str(missing))                      # isdir answers: no remade
    monkeypatch.setattr(hook.os, 'makedirs', real_makedirs)


def test_halted_records_and_survives_a_box_it_cannot_write(tmp_path, monkeypatch):
    box = tmp_path / 'req'
    hook._halted(str(box), 3, 'because')
    with open(box / 'halted.json', encoding='utf-8') as f:
        assert {'seq': 3, 'reason': 'because'}.items() <= json.load(f).items()

    def refused(_box):
        raise OSError(13, '')
    monkeypatch.setattr(hook, '_mailbox', refused)
    hook._halted(str(tmp_path / 'other'), 1, 'x')
    assert not (tmp_path / 'other').exists()
    monkeypatch.setattr(hook, '_mailbox', lambda _box: None)
    broken = tmp_path / 'broken'
    broken.mkdir()
    (broken / ('halted.json.%d.tmp' % os.getpid())).mkdir()
    hook._halted(str(broken), 1, 'x')
    assert not (broken / 'halted.json').exists()


def test_the_request_takes_the_next_free_sequence(tmp_path, monkeypatch):
    req = _exec_dir(tmp_path) / 'req'
    req.mkdir(parents=True)
    for name in ('3.lock', '7.lock', 'x.lock', 'precompact.json'):
        (req / name).write_bytes(b'')
    _answer(tmp_path, 8, {'decision': 'allow'})
    assert _run(tmp_path, monkeypatch) == ('allow', '')
    with open(req / '8.req.json', encoding='utf-8') as f:
        assert json.load(f) == {'token': TOKEN, 'tool': 'Read', 'input': {'file_path': 'a'},
                                'cwd': 'w', 'nonce': NONCE, 'seq': 8}
    assert not (req / '4.req.json').exists()


def test_a_stolen_sequence_number_is_retried_not_a_crash(tmp_path, monkeypatch):
    real_open = os.open
    stolen = []

    def racing(path, flags, mode=0o777):
        if path.endswith('1.lock') and not stolen:
            real_open(path, os.O_CREAT | os.O_WRONLY, mode)
            stolen.append(path)
            raise FileExistsError(path)
        return real_open(path, flags, mode)
    monkeypatch.setattr(hook.os, 'open', racing)
    _answer(tmp_path, 2, {'decision': 'allow'})
    assert _run(tmp_path, monkeypatch) == ('allow', '')
    assert _reqs(tmp_path) == ['1.lock', '2.lock', '2.req.json']


def test_a_response_beside_the_request_is_never_read(tmp_path, monkeypatch):
    got = {}
    asker = threading.Thread(target=lambda: got.setdefault(
        'answer', _run(tmp_path, monkeypatch, wait=5)))
    asker.start()
    req = _exec_dir(tmp_path) / 'req'
    for _ in range(200):                                # wait for the chosen seq
        names = [n for n in os.listdir(req) if n.endswith('.req.json')] if req.is_dir() else []
        if names:
            break
        time.sleep(0.01)
    assert names, 'the hook never even asked'
    seq = names[0].split('.')[0]
    _answer(tmp_path, int(seq), {'decision': 'allow'}, where='req')
    asker.join(timeout=60)
    assert got['answer'] == ('halt', NO_ANSWER)         # the neighbour was not the answer
    assert (req / ('%s.res.json' % seq)).exists()


# ── the sentinels ─────────────────────────────────────────────────────────────

def test_a_missing_sentinel_is_absent(tmp_path):
    assert hook._sentinel(str(tmp_path / 'gone'), 'emergency stop', 'why') is None


@pytest.mark.parametrize('where', ['estop', 'pause'], ids=['estop', 'flag'])
def test_a_sentinel_that_cannot_be_read_halts_fail_closed(tmp_path, monkeypatch, where):
    real_lstat = os.lstat
    blocked = tmp_path / 'run' / 'STOP' if where == 'estop' \
        else _exec_dir(tmp_path) / 'ctl' / 'PAUSE'
    blocked.parent.mkdir(parents=True, exist_ok=True)
    blocked.write_bytes(b'')

    def denying(path, **kw):
        if str(path) == str(blocked):
            raise OSError(13, '')
        return real_lstat(path, **kw)
    monkeypatch.setattr(hook.os, 'lstat', denying)
    want = "cannot determine the emergency stop's state; halted (fail closed)" if where == 'estop' \
        else "cannot determine the PAUSE flag's state; halted (fail closed)"
    assert _run(tmp_path, monkeypatch) == ('halt', want)
    assert _halted(tmp_path)['seq'] is None


@pytest.mark.parametrize('flag, why',
                         [('STOP', 'stopped by Archeus'), ('PAUSE', 'paused by Archeus'),
                          ('HANDOFF', 'handing off to a fresh session')],
                         ids=['stop', 'pause', 'handoff'])
def test_each_execution_flag_halts_its_own_way(tmp_path, monkeypatch, flag, why):
    ctl = _exec_dir(tmp_path) / 'ctl'
    ctl.mkdir(parents=True)
    (ctl / flag).write_bytes(b'')
    assert _run(tmp_path, monkeypatch) == ('halt', why)
    assert {'seq': None, 'reason': why}.items() <= _halted(tmp_path).items()
    assert _reqs(tmp_path) == ['halted.json']       # nothing was ever asked


def test_the_emergency_stop_wins_while_the_hook_waits(tmp_path, monkeypatch):
    (tmp_path / 'run').mkdir(parents=True, exist_ok=True)
    estop = tmp_path / 'run' / 'STOP'
    real_sleep = time.sleep
    planted = []

    def planting(seconds):
        if not planted:
            estop.write_bytes(b'')
            planted.append(1)
        return real_sleep(seconds)
    monkeypatch.setattr(hook.time, 'sleep', planting)
    assert _run(tmp_path, monkeypatch, wait=5) == ('halt', 'emergency stop')
    assert _halted(tmp_path)['seq'] == 1


# ── the answer from Core: only a trusted one decides ──────────────────────────

@pytest.mark.parametrize('body',
                         [[1, 2], 'allow', {'decision': 'approve'},
                          {'decision': 'ALLOW'}, {'decision': None}, b'not json'],
                         ids=['list', 'string', 'unknown', 'upper', 'null', 'garbage'])
def test_an_answer_the_hook_cannot_trust_fails_closed(tmp_path, monkeypatch, body):
    _answer(tmp_path, 1, body)
    assert _run(tmp_path, monkeypatch) == ('halt', NO_ANSWER)
    assert _halted(tmp_path)['reason'] == 'Archeus did not answer'


def test_a_halt_answer_halts_with_its_own_record(tmp_path, monkeypatch):
    _answer(tmp_path, 1, {'decision': 'halt', 'reason': 'policy says no'})
    assert _run(tmp_path, monkeypatch) == ('halt', 'policy says no')
    assert {'seq': 1, 'reason': 'policy says no'}.items() <= _halted(tmp_path).items()


def test_an_answer_with_no_halt_reason_stays_empty(tmp_path, monkeypatch):
    _answer(tmp_path, 1, {'decision': 'halt'})
    assert _run(tmp_path, monkeypatch) == ('halt', '')
    assert {'seq': 1, 'reason': ''}.items() <= _halted(tmp_path).items()


def test_an_allow_answer_leaves_no_halt_record(tmp_path, monkeypatch):
    _answer(tmp_path, 1, {'decision': 'allow', 'reason': 'ok'})
    assert _run(tmp_path, monkeypatch) == ('allow', 'ok')
    assert _reqs(tmp_path) == ['1.lock', '1.req.json']


def test_the_missing_answer_is_the_named_fail_closed_halt(tmp_path, monkeypatch):
    assert _run(tmp_path, monkeypatch, wait=0.15) == ('halt', NO_ANSWER)
    assert {'seq': 1, 'reason': 'Archeus did not answer'}.items() <= _halted(tmp_path).items()


# ── main: a broken hook never allows ──────────────────────────────────────────

def _main(tmp_path, monkeypatch, capsys, stdin_text):
    monkeypatch.delenv('ARCHEUS_HOOK_ACTIVE', raising=False)
    monkeypatch.setattr(hook.sys, 'stdin', io.StringIO(stdin_text))
    code = hook.main()
    return code, capsys.readouterr()


def test_a_broken_input_halts_by_name_of_its_failure(tmp_path, monkeypatch, capsys):
    code, seen = _main(tmp_path, monkeypatch, capsys, 'this is not json')
    out = json.loads(seen.out)
    assert code == 0 and seen.err == ''
    assert out['continue'] is False and out['hookSpecificOutput']['permissionDecision'] == 'deny'
    assert out['stopReason'] == 'the Archeus hook failed: JSONDecodeError'


def test_a_payload_that_is_not_an_object_halts_by_value_error(tmp_path, monkeypatch, capsys):
    code, seen = _main(tmp_path, monkeypatch, capsys, '[1, 2]')
    assert code == 0 and seen.err == ''
    assert json.loads(seen.out)['stopReason'] == 'the Archeus hook failed: ValueError'


def test_a_deny_leaves_stdout_empty_and_exit_two(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(hook, 'run', lambda payload, env: ('deny', 'nope'))
    code, seen = _main(tmp_path, monkeypatch, capsys, '{"tool_name": "Read"}')
    assert (code, seen.out, seen.err) == (2, '', 'nope')


def test_an_allow_leaves_the_decision_on_stdout_at_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(hook, 'run', lambda payload, env: ('allow', 'ignored'))
    code, seen = _main(tmp_path, monkeypatch, capsys, '{"tool_name": "Read"}')
    assert code == 0 and seen.err == ''
    assert json.loads(seen.out) == hook.decision('allow')
