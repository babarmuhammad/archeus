"""T-725: the fail-closed branches of `archeus/harnesses/hook.py` nothing else reaches.

The module is Claude Code's PreToolUse command (p11-design-gate §10, ADR-0049 §3,
PV-19 O4, PV-20 §7.5). Its contract is that whatever it cannot decide, it denies or
halts, and the only exit codes it may ever leave are 0 (with the halt's deny on
stdout) and 2. The module's own tests already pin the protocol, the sentinel's
three-state read and the mailbox classes (`test_execution_units.py` §10, U-4), the
exit codes as a process (`test_settings_sources_units.py` E16-E19) and the estop,
identity and self-recursion guards end to end (`test_execution.py` E47-E49). None of
that is repeated here. What is left, in the order the risk falls, is: an answer that
arrives hostile or broken (hook.py:169-182), the payload the execution controls
(hook.py:139-161), the identity guards' boundary values (hook.py:133-136), the
sequence scan (hook.py:113-127), and the places a failure is swallowed and must still
answer (hook.py:90, 146, 189, 222).

Nothing here needs Windows or the Windows API. The OS calls are faked through the
seams the module's own tests use: monkeypatch on `os.replace`, `os.open`,
`hook.open`, and on `hook.WAIT_S` / `hook.POLL_S`, plus `sys.stdin` / `stdout` /
`stderr` for `main`. Answer files are written as bytes with explicit newlines, names
are ASCII without `?` or `:`, no assertion reads an OS error text, a live thread set
or a POSIX absolute path, no environment value comes near 32000 characters, and every
temporary file goes through `tmp_path`. No test waits more than 0.2 s of the hook's
own polling, and none sleeps over 1 s.
"""

import errno
import io
import json
import os
import sys

import pytest

from archeus.harnesses import hook

#: one valid execution id: `exe_` plus 26 characters of the Crockford alphabet, the first one 0-7
EID = 'exe_' + '0' + 'A' * 25
NONCE = 'ab' * 16
#: the hook's own deadline answer (hook.py:182)
NO_ANSWER = 'Archeus did not answer; denied and halted (fail closed)'


def _env(tmp_path, eid=EID, drop=(), **over):
    """The three variables a request needs, every test naming them itself; `drop`
    is the case where the variable is not in the environment at all."""
    env = {'ARCHEUS_HOME': str(tmp_path), 'ARCHEUS_EXECUTION_ID': eid,
           'ARCHEUS_HOOK_TOKEN': 'hook_t'}
    env.update(over)
    for key in drop:
        env.pop(key, None)
    return env


def _exec_dir(tmp_path, eid=EID):
    return os.path.join(str(tmp_path), 'run', 'exec', eid)


def _dirs(tmp_path, *names, eid=EID):
    """The execution's own directory and the class directories in it, made before
    the hook runs (a test that wants one of them absent makes it itself)."""
    d = _exec_dir(tmp_path, eid)
    os.makedirs(d, exist_ok=True)
    for name in names:
        os.makedirs(os.path.join(d, name), exist_ok=True)
    return d


@pytest.fixture(autouse=True)
def _fixed_nonce(monkeypatch):
    """The hook draws its request nonce with `os.urandom(16)`; fixing it lets a test
    write the answer Core would give before the hook asks."""
    real = os.urandom
    monkeypatch.setattr(os, 'urandom', lambda n: bytes.fromhex(NONCE) if n == 16 else real(n))


def _bound(seq, body, tool='Read', input=None, cwd=None):
    """*body* as Core answers it: echoing the nonce and the digest of the request
    the hook writes for this payload (hook.py:191-199)."""
    request = {'token': 'hook_t', 'tool': tool, 'input': input, 'cwd': cwd, 'nonce': NONCE,
               'seq': seq}
    return dict(body, nonce=NONCE, digest=hook.request_digest(request))


def _core_says(d, seq, body, **payload):
    """Core's answer in class 2 before the hook asks: `res/<seq>.res.json`. A dict is
    bound to the request (`_bound`); bytes are given verbatim, so a test can hand
    the hook a torn document or a top-level value that is not an object."""
    res = os.path.join(d, 'res')
    os.makedirs(res, exist_ok=True)
    path = os.path.join(res, '%d.res.json' % seq)
    raw = body if isinstance(body, bytes) else json.dumps(_bound(seq, body, **payload))
    with open(path, 'wb') as f:
        f.write(raw.encode('utf-8') if isinstance(raw, str) else raw)
    return path


def _read(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _estop(tmp_path):
    run = os.path.join(str(tmp_path), 'run')
    os.makedirs(run, exist_ok=True)
    open(os.path.join(run, 'STOP'), 'wb').close()


class _Stream:
    """sys.stdout/sys.stderr with the two methods the hook uses, recording what it
    wrote. `fail` is what a write raises, for a stream that cannot be written."""

    def __init__(self, fail=None, reconfigure_fails=None):
        self.out = []
        self._fail = fail
        self._reconfigure_fails = reconfigure_fails

    def write(self, text):
        if self._fail is not None:
            raise self._fail
        self.out.append(text)
        return len(text)

    def flush(self):
        pass

    def reconfigure(self, **kw):
        if self._reconfigure_fails is not None:
            raise self._reconfigure_fails


class _StreamWithoutReconfigure:
    """A stdout with no `reconfigure` at all, as a replaced or older stream has."""

    def __init__(self):
        self.out = []

    def write(self, text):
        self.out.append(text)
        return len(text)

    def flush(self):
        pass


def _main(monkeypatch, env, stdin_text, drop=(), stdout=None, stderr=None):
    """`main` the way `__main__` calls it: the environment through os.environ, the
    payload on stdin, the answer on stdout/stderr. `ARCHEUS_HOOK_ACTIVE` is seeded
    empty first so monkeypatch restores what `main` itself writes (the seam
    `test_an_unwritable_class_1_halts_and_asks_nothing` uses)."""
    for key in ('ARCHEUS_HOME', 'ARCHEUS_EXECUTION_ID', 'ARCHEUS_HOOK_TOKEN') + tuple(drop):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('ARCHEUS_HOOK_ACTIVE', '')          # seeded before, restored after
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    out = stdout if stdout is not None else _Stream()
    err = stderr if stderr is not None else _Stream()
    monkeypatch.setattr(sys, 'stdin', io.StringIO(stdin_text))
    monkeypatch.setattr(sys, 'stdout', out, raising=False)
    monkeypatch.setattr(sys, 'stderr', err, raising=False)
    code = hook.main()
    return code, ''.join(out.out), ''.join(err.out)


@pytest.fixture
def fast(monkeypatch):
    """The hook's own deadline and poll, shortened: a hook that is never answered
    still finishes in a fraction of a second."""
    monkeypatch.setattr(hook, 'WAIT_S', 0.2)
    monkeypatch.setattr(hook, 'POLL_S', 0.01)


# ── the answer nothing may ever read as an allow ─────────────────────────────

@pytest.mark.parametrize('body', [b'"allow"', b'42', b'null', b'[]', b'true', b'"halt"'],
                         ids=['string-allow', 'number', 'null', 'list', 'bool', 'string-halt'])
def test_H02_a_top_level_json_answer_is_never_an_answer(tmp_path, fast, body):
    """hook.py:175-177 (`isinstance(got, dict)` else None, then the `break`): a
    document that is not an object holds no decision, so the hook waits out its
    deadline and halts. Read the top-level value as the decision, or fall through
    to the default allow, and the call that Claude Code is about to run goes
    through on `"allow"`."""
    d = _dirs(tmp_path, 'req', 'res')
    answer = _core_says(d, 1, body)
    assert hook.run({'tool_name': 'Read'}, _env(tmp_path)) == ('halt', NO_ANSWER)
    assert os.path.exists(answer)                                  # there, and refused
    assert _read(os.path.join(d, 'req', 'halted.json'))['seq'] == 1


@pytest.mark.parametrize('body', [
    {'decision': 'ALLOW'}, {'decision': 'allow '}, {'decision': True}, {'decision': 1},
    {'decision': None}, {'decision': ['allow']}, {}, {'permissionDecision': 'allow'}],
    ids=['upper', 'trailing-space', 'true', 'one', 'null', 'list', 'empty', 'wrong-field'])
def test_H03_only_the_three_words_in_the_decision_field_answer(tmp_path, fast, body):
    """hook.py:176-177 (`kind not in ('allow', 'deny', 'halt')` -> `break`): the
    word is compared exactly, in the field `decision`, or there is no answer. A
    case-insensitive or `str(...)`-coercing comparison turns `'ALLOW'`, `True` or a
    list into an allow, and `test_execution_units` has no case for any of them."""
    d = _dirs(tmp_path, 'req', 'res')
    _core_says(d, 1, body)
    assert hook.run({'tool_name': 'Read'}, _env(tmp_path)) == ('halt', NO_ANSWER)
    record = _read(os.path.join(d, 'req', 'halted.json'))
    assert (record['seq'], record['reason']) == (1, 'Archeus did not answer')


def test_H04a_a_torn_answer_is_not_an_answer(tmp_path, fast, monkeypatch):
    """hook.py:172-174, the `ValueError` side: Core's file is half-written and the
    JSON does not parse. Only `OSError` had a test (`test_an_unreadable_class_2_
    answer_is_never_accepted`); a decoder error that escapes the loop, or one read
    as an allow, is the same hole as a torn write being trusted."""
    d = _dirs(tmp_path, 'req', 'res')
    answer = _core_says(d, 1, b'{"decision": "allow"')             # no closing brace
    assert hook.run({'tool_name': 'Read'}, _env(tmp_path)) == ('halt', NO_ANSWER)
    with open(answer, 'rb') as f:
        assert f.read() == b'{"decision": "allow"'                  # left for Core, unread


def test_H04b_a_torn_answer_is_polled_again_and_the_whole_one_answers(tmp_path, monkeypatch):
    """hook.py:172-174 (`time.sleep(POLL_S); continue`): the undecodable read is
    retried, and the complete document behind it is honoured. Turn the `continue`
    into a `break` and a hook would halt an execution over one half-written file;
    drop `ValueError` from the `except` and the same file crashes the hook."""
    d = _dirs(tmp_path, 'req', 'res')
    answer = _core_says(d, 1, b'{"decision": "allo')
    whole = json.dumps(_bound(1, {'decision': 'allow', 'reason': 'ok'})).encode('utf-8')
    reads = iter([b'{"decision": "allo', whole])
    real_open = open

    def reopened(path, *a, **kw):
        if os.fspath(path) == answer:
            return io.StringIO(next(reads).decode('utf-8'))
        return real_open(path, *a, **kw)

    monkeypatch.setattr(hook, 'open', reopened, raising=False)
    monkeypatch.setattr(hook, 'WAIT_S', 5.0)          # the retry must not race the deadline
    assert hook.run({'tool_name': 'Read'}, _env(tmp_path)) == ('allow', 'ok')


def test_H05a_cores_halt_halts_the_agent_and_reports_the_sequence(tmp_path, fast):
    """hook.py:178-179 (`if kind == 'halt': _halted(box, seq, ...)`): Core's halt
    is recorded with the sequence it answers, and never becomes an allow. E17 only
    ever halts through the estop, so this is the only test of Core's own halt."""
    d = _dirs(tmp_path, 'req', 'res')
    _core_says(d, 1, {'decision': 'halt', 'reason': 'core says stop'})
    assert hook.run({'tool_name': 'Read'}, _env(tmp_path)) == ('halt', 'core says stop')
    record = _read(os.path.join(d, 'req', 'halted.json'))
    assert (record['seq'], record['reason']) == (1, 'core says stop')


def test_H05b_a_halt_with_no_reason_still_denies_the_call_with_one(tmp_path, monkeypatch):
    """hook.py:58 (`reason = reason or 'halted by Archeus'`) through hook.py:178-180:
    Core halts without a reason, and the stdout document still carries a reason and
    the PreToolUse deny. Drop the default and Claude Code gets an empty stopReason
    beside `continue: false`; drop the deny and the call in flight runs anyway."""
    d = _dirs(tmp_path, 'req', 'res')
    _core_says(d, 1, {'decision': 'halt'})
    code, out, err = _main(monkeypatch, _env(tmp_path), '{"tool_name": "Read"}')
    assert (code, err) == (0, '')
    assert out == json.dumps({'continue': False, 'stopReason': 'halted by Archeus',
                              'hookSpecificOutput': {'hookEventName': 'PreToolUse',
                                                     'permissionDecision': 'deny',
                                                     'permissionDecisionReason':
                                                         'halted by Archeus'}})
    assert _read(os.path.join(d, 'req', 'halted.json'))['seq'] == 1


def test_H06_a_deny_with_no_reason_is_still_exit_2_with_something_on_stderr(
        tmp_path, monkeypatch):
    """hook.py:71-72 (`return '', reason or 'denied by Archeus', DENY_EXIT`): E16
    denies with a reason, so the default is unpinned. A deny must never put JSON on
    stdout — Claude Code reads stdout only at exit 0 — and must never exit 0."""
    d = _dirs(tmp_path, 'req', 'res')
    _core_says(d, 1, {'decision': 'deny'}, tool='Bash')
    code, out, err = _main(monkeypatch, _env(tmp_path), '{"tool_name": "Bash"}')
    assert (code, out, err) == (2, '', 'denied by Archeus')
    assert os.listdir(os.path.join(d, 'res')) == ['1.res.json']


# ── the payload, which is the execution's, not Core's ────────────────────────

def test_H09_the_request_carries_only_the_four_fields_the_hook_writes(tmp_path, monkeypatch):
    """hook.py:160-161 + :125 (`dict(body, seq=seq)`): the request is built from the
    environment and four payload keys, so a payload that brings its own `seq`,
    `token` or `decision` cannot spend another sequence number, answer for itself,
    or speak with a token it was not given. The large input is the payload limit
    this module has: it is written out whole, neither truncated nor refused."""
    d = _dirs(tmp_path, 'req', 'res')
    big = 'x' * 20000
    _core_says(d, 1, {'decision': 'allow'}, input={'file_path': big}, cwd='work')
    payload = {'tool_name': 'Read', 'tool_input': {'file_path': big}, 'cwd': 'work',
               'seq': 99, 'token': 'forged', 'decision': 'allow', 'hook_event_name': 'ToolUse'}
    assert hook.run(payload, _env(tmp_path)) == ('allow', '')
    with open(os.path.join(d, 'req', '1.req.json'), encoding='utf-8') as f:
        req = json.load(f)
    assert sorted(req) == ['cwd', 'input', 'nonce', 'seq', 'token', 'tool']
    assert (req['seq'], req['token'], req['tool'], req['cwd']) == (1, 'hook_t', 'Read', 'work')
    assert req['input'] == {'file_path': big}                        # verbatim, not truncated
    assert 'decision' not in req
    assert os.listdir(os.path.join(d, 'res')) == ['1.res.json']      # sequence 1 was the number


@pytest.mark.parametrize('event', ['precompact', 'PRECOMPACT', 'PreCompact ', 'PreCompact\n'],
                         ids=['lower', 'upper', 'trailing-space', 'trailing-newline'])
def test_H09b_a_payload_that_mimics_the_precompact_name_cannot_slip_the_gate(
        tmp_path, fast, event):
    """hook.py:139 (`payload.get('hook_event_name') == 'PreCompact'`): the compare is
    exact, and it is the only line of the gate an execution can reach with its own
    payload. `lower()`, `strip()` or a `startswith` here lets a tool call name itself
    a compaction and be answered `continue` with no request, no sentinel read and no
    answer from Core at all."""
    d = _dirs(tmp_path, 'req', 'res')
    assert hook.run({'hook_event_name': event, 'tool_name': 'Read'},
                    _env(tmp_path)) == ('halt', NO_ANSWER)
    assert os.path.exists(os.path.join(d, 'req', '1.req.json'))      # it was asked, not skipped
    assert 'precompact.json' not in os.listdir(os.path.join(d, 'req'))


def test_H12_a_precompact_that_cannot_be_recorded_still_compacts(tmp_path):
    """hook.py:146-147 (`except OSError: pass`): class 1 is a file, so opening the
    record fails inside `_mailbox`. A PreCompact is a signal for Core and never a
    decision (p12-design-gate §13.1), so the failure is swallowed and the answer is
    still `continue`; let the OSError escape and the hook dies in front of a
    compaction it was never asked to judge."""
    d = _dirs(tmp_path)
    open(os.path.join(d, 'req'), 'wb').close()                       # not a directory
    assert hook.run({'hook_event_name': 'PreCompact', 'trigger': 'auto'},
                    _env(tmp_path)) == ('continue', '')
    assert os.listdir(d) == ['req']


def test_H12b_a_precompact_answers_the_empty_document_and_asks_nothing(tmp_path, monkeypatch):
    """hook.py:51-52 (`return {}`) through main: a compaction's stdout is exactly `{}`
    at exit 0 — no permissionDecision for Claude Code to act on, and no request.
    Answer `allow` instead, and every compaction is also a blanket allow."""
    d = _dirs(tmp_path, 'req')
    code, out, err = _main(monkeypatch, _env(tmp_path),
                           json.dumps({'hook_event_name': 'PreCompact', 'trigger': 'auto'}))
    assert (code, out, err) == (0, '{}', '')
    assert os.listdir(os.path.join(d, 'req')) == ['precompact.json']


# ── the identity guards' boundary values ─────────────────────────────────────

@pytest.mark.parametrize('over, drop', [
    ({'ARCHEUS_EXECUTION_ID': 'exe_' + 'A' * 25}, ()),
    ({'ARCHEUS_EXECUTION_ID': 'exe_' + 'A' * 27}, ()),
    ({'ARCHEUS_EXECUTION_ID': 'exe_' + 'I' * 26}, ()),
    ({'ARCHEUS_EXECUTION_ID': 'exe_' + 'a' * 26}, ()),
    ({'ARCHEUS_EXECUTION_ID': 'EXE_' + 'A' * 26}, ()),
    ({'ARCHEUS_EXECUTION_ID': EID + '.'}, ()),
    ({'ARCHEUS_EXECUTION_ID': EID + '\n'}, ()),
    ({'ARCHEUS_EXECUTION_ID': ' ' + EID}, ()),
    ({'ARCHEUS_EXECUTION_ID': ''}, ()),
    ({'ARCHEUS_HOME': ''}, ()), ({'ARCHEUS_HOOK_TOKEN': ''}, ()),
    ({}, ('ARCHEUS_HOME',)), ({}, ('ARCHEUS_HOOK_TOKEN',)), ({}, ('ARCHEUS_EXECUTION_ID',)),
], ids=['id-25', 'id-27', 'id-excluded-letter', 'id-lower', 'id-upper-prefix', 'id-trailing-dot',
        'id-trailing-newline', 'id-leading-space', 'id-empty', 'home-empty', 'token-empty',
        'no-home', 'no-token', 'no-id'])
def test_H08_an_identity_that_is_not_exactly_one_halts_and_writes_nothing(tmp_path, fast,
                                                                          over, drop):
    r"""hook.py:40 + :135 (`_ID.match`, the `\Z` anchor) and :131-136: 25 and 27
    characters, an excluded letter, either case and a trailing newline are all
    refused before a single path is built. E48 tries one traversal value; `\Z`, not
    `$`, is what refuses a name with a newline glued on it, and the whole `run`
    short-circuits — so nothing under ARCHEUS_HOME is created for a process that is
    nobody."""
    assert hook.run({'tool_name': 'Read'}, _env(tmp_path, drop=drop, **over)) == (
        'halt', 'this process has no Archeus execution identity')
    assert not os.path.exists(os.path.join(str(tmp_path), 'run'))


def test_H08b_the_active_mark_halts_before_anything_is_read(tmp_path, monkeypatch):
    """hook.py:133-134 (`if environ.get('ARCHEUS_HOOK_ACTIVE')`): the guard is
    first, ahead of the identity check, so a hook re-installed inside its own hook
    halts on the mark even while it holds a perfect identity — and never takes a
    sequence number, which is what a recursive hook would otherwise spend forever."""
    d = _dirs(tmp_path, 'req')
    _core_says(d, 1, {'decision': 'allow'})
    code, out, err = _main(monkeypatch, _env(tmp_path, ARCHEUS_HOOK_ACTIVE='1'),
                           '{"tool_name": "Read"}')
    assert code == 0
    assert json.loads(out)['stopReason'] == 'the Archeus hook may not run inside itself'
    assert json.loads(out)['hookSpecificOutput']['permissionDecision'] == 'deny'
    assert os.listdir(os.path.join(d, 'req')) == []                  # nothing asked, nothing halted


# ── the sequence scan, which runs over a directory the execution writes ──────

def test_H10a_the_next_sequence_number_is_the_highest_numeric_one_plus_one(tmp_path):
    """hook.py:115-117: the numbers are read out of the names that begin with digits
    and the next is `max(...)+1` — so `halted.json`, `notes.txt` and a torn
    `.req.part` are skipped, kept, and spent, and a `0.lock` never restarts the
    count at 1. Drop the `isdigit` filter and a name is read as a number that is not
    one; drop the `max` and two hooks answer the same request."""
    d = _dirs(tmp_path, 'req')
    box = os.path.join(d, 'req')
    for name in ('halted.json', 'notes.txt', '0.lock', '7.req.json', '9.req.part', '5'):
        with open(os.path.join(box, name), 'wb') as f:
            f.write(b'{}')
    _core_says(d, 10, {'decision': 'allow'})
    assert hook.run({'tool_name': 'Read'}, _env(tmp_path)) == ('allow', '')
    assert sorted(os.listdir(box)) == sorted(['0.lock', '5', '7.req.json', '9.req.part',
                                               '10.lock', '10.req.json', 'halted.json',
                                               'notes.txt'])


def test_H10b_a_number_taken_under_the_hook_s_own_feet_is_retried(tmp_path, monkeypatch):
    """hook.py:121-122 (`except FileExistsError: continue`): a concurrent hook wins
    the exclusive `<seq>.lock` between the listing and the create, and the hook
    re-scans instead of dying or reusing the number. Without the retry a lost race
    is an uncaught `FileExistsError`, and the crash is a halt for an execution that
    only lost a race."""
    d = _dirs(tmp_path, 'req')
    box = os.path.join(d, 'req')
    lock = os.path.join(box, '1.lock')
    _core_says(d, 1, {'decision': 'allow'})
    lost = []
    real_open = os.open

    def once_lost(path, flags, *a, **kw):
        if os.fspath(path) == lock and not lost:
            lost.append(1)
            raise FileExistsError(errno.EEXIST, 'taken')
        return real_open(path, flags, *a, **kw)

    monkeypatch.setattr(os, 'open', once_lost)
    assert hook.run({'tool_name': 'Read'}, _env(tmp_path)) == ('allow', '')
    assert len(lost) == 1 and os.path.exists(lock)
    assert os.path.exists(os.path.join(box, '1.req.json'))


def test_H10c_a_hostile_name_in_the_mailbox_never_becomes_an_allow(tmp_path, fast, monkeypatch):
    """hook.py:115-116 again, hostile side: `str.isdigit()` is true for characters
    `int()` refuses (a superscript digit), and class 1 is writable by the execution.
    The listing is patched rather than the name created, so this is the same on every
    file system. Whatever the scan makes of it, `main` answers a halt and a deny, not
    an allow (`test_execution_units` has no case for a mailbox poisoned by its own
    execution)."""
    d = _dirs(tmp_path, 'req')
    box = os.path.join(d, 'req')
    real_listdir = os.listdir
    seen = []

    def poisoned(path, *a, **kw):
        if os.fspath(path) == box:
            seen.append(1)
            return ['\u00b2.req.json']                  # isdigit() True, int() a ValueError
        return real_listdir(path, *a, **kw)

    monkeypatch.setattr(os, 'listdir', poisoned)
    code, out, err = _main(monkeypatch, _env(tmp_path), '{"tool_name": "Read"}')
    assert seen and code == 0
    assert os.path.exists(os.path.join(box, '1.req.json'))          # the superscript took no number
    answer = json.loads(out)
    assert answer['continue'] is False
    assert answer['hookSpecificOutput']['permissionDecision'] == 'deny'


# ── the deadline, and the failures the hook swallows ─────────────────────────

@pytest.mark.parametrize('wait', [0.0, -1.0], ids=['zero', 'negative'])
def test_H11_a_wait_that_leaves_no_time_never_accepts_an_answer(tmp_path, monkeypatch, wait):
    """hook.py:163-164 (`deadline = time.monotonic() + WAIT_S`, then `while ... <`):
    with no time to wait the hook does not read the answer at all — a stale or
    planted `1.res.json` is not a permit, and `ARCHEUS_HOOK_WAIT=0` shuts the gate
    rather than opening it. Invert the comparison and the loop runs on forever."""
    d = _dirs(tmp_path, 'req', 'res')
    _core_says(d, 1, {'decision': 'allow'})
    monkeypatch.setattr(hook, 'WAIT_S', wait)
    assert hook.run({'tool_name': 'Read'}, _env(tmp_path)) == ('halt', NO_ANSWER)
    assert _read(os.path.join(d, 'req', 'halted.json'))['seq'] == 1


@pytest.mark.parametrize('why', ['replace', 'mailbox'], ids=['replace-fails', 'mailbox-file'])
def test_H07_a_halt_that_cannot_be_written_is_still_a_halt(tmp_path, monkeypatch, why):
    """hook.py:90-91 (`except OSError: pass` in `_halted`): the report Core reads is
    best effort and the decision is not. Class 1 refuses the write one way or the
    other — `os.replace` fails, or the mailbox is a file and cannot be created — and
    `run` still returns the halt instead of raising out to `main`."""
    d = _dirs(tmp_path)
    box = os.path.join(d, 'req')
    _estop(tmp_path)
    if why == 'mailbox':
        open(box, 'wb').close()
    else:
        def broken(src, dst, *a, **kw):
            raise OSError(errno.EIO, 'cannot publish the halt')
        monkeypatch.setattr(os, 'replace', broken)
    assert hook.run({'tool_name': 'Read'}, _env(tmp_path)) == ('halt', 'emergency stop')
    assert not os.path.exists(os.path.join(box, 'halted.json'))       # nothing half-written


def test_H13_main_answers_even_with_a_stdout_it_cannot_prepare(tmp_path, monkeypatch):
    """hook.py:187-190 (`except (AttributeError, ValueError, OSError): pass` around
    `stream.reconfigure`): stdout may be a replaced object with no `reconfigure`, or
    one whose reconfigure fails, and the hook still writes its halt. Let that escape
    and the answer is lost with the stream — the worst moment to lose it."""
    for stream in (_StreamWithoutReconfigure(),
                   _Stream(reconfigure_fails=AttributeError('reconfigure')),
                   _Stream(reconfigure_fails=ValueError('closed')),
                   _Stream(reconfigure_fails=OSError(errno.EIO, 'stream'))):
        code, out, err = _main(monkeypatch, _env(tmp_path, ARCHEUS_EXECUTION_ID=''),
                               '{"tool_name": "Read"}', stdout=stream)
        assert (code, err) == (0, '')
        answer = json.loads(out)
        assert answer['continue'] is False
        assert answer['stopReason'] == 'this process has no Archeus execution identity'
        assert answer['hookSpecificOutput']['permissionDecision'] == 'deny'


@pytest.mark.parametrize('stdin_text', ['["allow"]', '"allow"', '42', 'null', 'true'],
                         ids=['list', 'string', 'number', 'null', 'bool'])
def test_H14_a_hook_input_that_is_not_an_object_halts(tmp_path, monkeypatch, stdin_text):
    """hook.py:194-196 (`if not isinstance(payload, dict): raise ValueError`): the
    payload arrives on stdin from whatever the agent is, and only an object gets into
    `run`. E18 covers the input that is not JSON at all; this covers the JSON that is
    valid but is not a payload — dropping the check reaches `payload.get` and turns
    the reason into an `AttributeError` instead of the documented one."""
    code, out, err = _main(monkeypatch, _env(tmp_path), stdin_text)
    assert (code, err) == (0, '')
    answer = json.loads(out)
    assert answer['continue'] is False and answer['stopReason'] == (
        'the Archeus hook failed: ValueError')
    assert answer['hookSpecificOutput']['permissionDecision'] == 'deny'
    assert answer['hookSpecificOutput']['permissionDecisionReason'] == (
        'the Archeus hook failed: ValueError')


def test_H15_a_guard_that_cannot_report_still_denies(monkeypatch):
    """hook.py:222-223 (`except Exception: pass` around the deny's stderr write):
    `guarded` is the last thing between an escaping failure and an exit code Claude
    Code lets the call through on, so it has to return 2 even when it cannot say so.
    E18 runs it with a working stderr only."""
    stderr = _Stream(fail=OSError(errno.EIO, 'no stderr'))
    monkeypatch.setattr(sys, 'stderr', stderr, raising=False)
    assert hook.guarded(lambda: 1) == hook.DENY_EXIT
    assert hook.guarded(lambda: 1 / 0) == hook.DENY_EXIT
    assert hook.guarded(lambda: sys.exit(4)) == hook.DENY_EXIT
    assert stderr.out == []                                # the write failed, and stayed hidden
    monkeypatch.setattr(sys, 'stderr', _Stream(), raising=False)
    assert hook.guarded(lambda: 0) == 0                    # an answer still answers untouched
    assert hook.guarded(lambda: hook.DENY_EXIT) == hook.DENY_EXIT


# ── the wait value is parsed at import, outside every guard ──────────────────

@pytest.mark.parametrize('raw, expected', [
    ('30', 30.0), ('0', 0.0), ('not-a-number', 60.0), ('', 60.0), ('-1', 60.0),
    ('nan', 60.0), ('inf', hook.MAX_WAIT_S), ('1e9', hook.MAX_WAIT_S)],
    ids=['plain', 'zero', 'words', 'empty', 'negative', 'nan', 'inf', 'huge'])
def test_H01_a_wait_value_that_cannot_hold_the_hook_open_or_kill_it(raw, expected):
    """hook.py:44-51: `wait_s` runs at import, outside `guarded`, so a value that does
    not parse must give the default instead of an exit code Claude Code lets the call
    through on, and one that never ends is capped below Claude Code's own timeout."""
    assert hook.wait_s(raw) == expected
