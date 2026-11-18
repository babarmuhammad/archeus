"""T-708: the branches of `archeus/harnesses/base.py` that carried no test.

Written from the source, branch by branch. The file is the process I/O contract,
and the branches picked here are the ones whose failure mode is a leaked secret,
a second process writing one stream, or a Core that dies on a line it did not
expect: the spawn rule's refusals (`spawn`, base.py:347-353), who owns a failed
start (base.py:355-368, 391-394), what the stream reader does with output it did
not write (`read_stream`, base.py:632-649), the environment an execution is
offered (`_isolated_env`, base.py:560-566), and what is left holding the
opted-in servers' keys when an end or a write fails (base.py:577-604, 610-622).

Everything here is platform-neutral in intent: the process itself is always a
fake handed to the launch seams (`spec.isolation.launch`, `proc.spawn_detached`),
and the one test that needs a POSIX symlink skips on Windows, where the
Windows-only code (`_windows_rows`, `_absolute`'s nt branch) is the thing that is
already covered elsewhere.
"""
import dataclasses
import json
import os
import sys
from types import SimpleNamespace

import pytest

from archeus.core.domain import ids
from archeus.harnesses import base
from claude_sessions import config


@pytest.fixture(autouse=True)
def _no_real_process(monkeypatch):
    """Nothing here may start a process: the fake launch is in the spec or nowhere."""
    def boom(*args, **kwargs):
        raise AssertionError('a real detached process was started')
    monkeypatch.setattr(base.proc, 'spawn_detached', boom)
    monkeypatch.setattr(base.proc, 'process_create_time', lambda pid: 1.0)


class FakeIsolation:
    """The isolated launch seam: records what it was handed, returns or raises what
    the test says. `launch` is the only thing `_start` asks of it."""

    def __init__(self, fail=None, reply=None):
        self.launches = []
        self.fail = fail
        self.reply = reply

    def launch(self, argv, *, cwd, env, paths):
        self.launches.append({'argv': list(argv), 'cwd': cwd, 'env': dict(env),
                              'paths': paths})
        if self.fail is not None:
            raise self.fail
        return (self.reply or SimpleNamespace(pid=424242)), None


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A machine with one banned tree, one tool directory on PATH, and nothing else."""
    home = str(tmp_path / 'home')
    account = str(tmp_path / 'account-home')
    work = str(tmp_path / 'work')
    tools = str(tmp_path / 'tools')
    for d in (home, account, work, tools):
        os.makedirs(d, exist_ok=True)
    monkeypatch.setenv('HOME', home)
    monkeypatch.setenv('USERPROFILE', home)
    for name in ('TEMP', 'TMP'):
        monkeypatch.setenv(name, str(tmp_path / name.lower()))
    monkeypatch.delenv('ARCHEUS_EXECUTION_ID', raising=False)
    monkeypatch.setenv('PATH', tools)
    return {'home': home, 'account': account, 'work': work, 'tools': tools}


def _spec(world, **kw):
    kw.setdefault('isolation', FakeIsolation())
    return base.ExecutionSpec(execution_id=ids.new_id('execution'), prompt='go',
                              workdir=world['work'], **kw)


def _files(where):
    return sorted(os.listdir(where)) if os.path.isdir(where) else []


# --------------------------------------------------------------------------- spawn rule

def test_BA01_a_resume_is_refused_while_the_last_process_has_no_end(world):
    """`spawn` base.py:347-353: `if last.get('process_seq', 1) != seq - 1 or not
    os.path.exists(paths.ended)` — the false side of the second clause. Process k > 1
    needs proof the k - 1'th process is GONE, and the only proof is its `ended`
    tombstone; P11's invariant is that one execution never has two processes at once,
    so a resumed execution whose last process never ended is refused, not started
    beside it. Invert the clause and two processes write one `stream.jsonl`, the
    offset accounting is meaningless, and the hook events of one are attributed to
    the other."""
    spec = _spec(world)
    base.spawn(spec, ['x'])
    paths = base.ExecPaths(spec.execution_id)
    base.mark_ended(paths, 0)
    second = dataclasses.replace(spec, process_seq=2, isolation=FakeIsolation())
    base.spawn(second, ['x'])
    paths2 = base.ExecPaths(second.execution_id)
    assert os.path.exists(paths2.pid)                       # the resume did start
    assert base.read_json(paths2.spawning)['process_seq'] == 2

    # and its own resume, with process 2 still unwitnessed: refused, untouched
    third = dataclasses.replace(spec, process_seq=3, isolation=FakeIsolation())
    with pytest.raises(base.AlreadySpawned, match='may still be running'):
        base.spawn(third, ['x'])
    assert third.isolation.launches == []                    # nothing reached the launch
    assert base.read_json(paths2.spawning)['process_seq'] == 2     # the marker still owns it
    assert base.read_json(paths2.pid)['process_seq'] == 2          # no second pid either


def test_BA02_a_resume_that_skips_a_generation_is_refused_even_with_an_end(world):
    """`spawn` base.py:351-353: the first clause, `last.get('process_seq', 1) != seq - 1`.
    An `ended` tombstone proves a process ended; it does not prove it was the process
    this resume is asking to follow, and a marker naming process 2 cannot be the
    predecessor of process 4. Invert it and a Core that lost a tick starts process 4
    over a still-recorded process 2 — the same stream, the same prompt file, two
    processes the manager only watches one of."""
    spec = _spec(world)
    base.spawn(spec, ['x'])
    paths = base.ExecPaths(spec.execution_id)
    base.mark_ended(paths, 0)
    base.spawn(dataclasses.replace(spec, process_seq=2, isolation=FakeIsolation()), ['x'])
    base.mark_ended(paths, 0)
    assert os.path.exists(paths.ended)                       # there IS an end on record
    assert base.read_json(paths.spawning)['process_seq'] == 2

    four = dataclasses.replace(spec, process_seq=4, isolation=FakeIsolation())
    with pytest.raises(base.AlreadySpawned, match='may still be running'):
        base.spawn(four, ['x'])
    assert four.isolation.launches == []
    assert base.read_json(paths.spawning)['process_seq'] == 2
    assert base.read_json(paths.pid)['process_seq'] == 2


def test_BA03_a_resume_with_no_marker_at_all_is_refused(world):
    """`spawn` base.py:351: `last = read_json(paths.spawning) or {}` and the `1` default
    of `last.get('process_seq', 1)`. A missing marker is not a free pass: read as `{}`
    it claims process 1 as the predecessor, and with the tombstone gone too nothing on
    disk proves the last process ended, so the resume is refused. The contract it breaks
    is the one `spawn`'s own docstring states — a marker means a process may exist — and
    the fail-closed reading of "we cannot tell" is a refusal, because the alternative is
    two processes on one stream. (The state this test builds — a marker deleted with its
    tombstone — is what a partial clean-up leaves; `config.write_atomic` keeps a *torn*
    marker unlikely, which is the case the next test takes up.)"""
    spec = _spec(world)
    base.spawn(spec, ['x'])
    paths = base.ExecPaths(spec.execution_id)
    base.mark_ended(paths, 0)
    # the marker of process 1 is gone and its tombstone with it: a resume asks for
    # process 2 and gets nothing started
    os.remove(paths.spawning)
    os.remove(paths.ended)
    with pytest.raises(base.AlreadySpawned, match='may still be running'):
        base.spawn(dataclasses.replace(spec, process_seq=2, isolation=FakeIsolation()),
                   ['x'])


@pytest.mark.parametrize('seq', [0, 1])
def test_BA04_the_first_process_needs_no_marker_and_the_second_needs_one(world, seq):
    """`spawn` base.py:347-349: `if seq <= 1:` and its `os.path.exists(paths.spawning)`
    refusal. `process_seq` comes from the caller, so both boundaries matter: 1 (or 0)
    with a marker already there is a process that exists, and > 1 is the resume rule.
    Invert `<= 1` to `< 1` and a `process_seq` of 0 walks past the marker check and
    starts a second process beside the first — while a genuine first process (seq 1)
    falls into the resume rule and can never start at all."""
    spec = _spec(world)
    base.spawn(spec, ['x'])                                 # process 1 of this execution
    with pytest.raises(base.AlreadySpawned):
        base.spawn(dataclasses.replace(spec, process_seq=seq, isolation=FakeIsolation()),
                   ['x'])


def test_BA05_a_marker_that_cannot_be_read_is_still_a_marker(world):
    """`spawn` base.py:350-353 fail-closed: an unreadable marker must read as
    "a process may exist" — `AlreadySpawned`, which every caller handles — and not as
    an exception no caller catches. `config.write_atomic` makes a torn marker unlikely
    and a Core that died, or a user with write access to the run directory, makes it
    possible; either way the refusal is the answer, the crash is not."""
    spec = _spec(world)
    base.spawn(spec, ['x'])
    paths = base.ExecPaths(spec.execution_id)
    base.mark_ended(paths, 0)
    with open(paths.spawning, 'w', encoding='utf-8') as f:
        f.write('{"execution_id": ')                        # as a lost write leaves it
    with pytest.raises(base.AlreadySpawned):
        base.spawn(dataclasses.replace(spec, process_seq=2, isolation=FakeIsolation()),
                   ['x'])


# ------------------------------------------------------------------------ failed starts

def test_BA06_a_prompt_that_cannot_be_written_starts_nothing_and_says_which_file(world):
    """`_start` base.py:391-394: `if not config.write_atomic(paths.prompt, spec.prompt):
    raise OSError(...)` into `except OSError as err: _refuse(..., SpawnWriteFailed)`.
    A prompt that is not on disk means the child would read whatever the LAST attempt
    left in `prompt.txt` — another execution's instructions, on another execution's
    stdin — so the refusal must name prompt.txt, charge like a workspace that cannot
    be made, and never reach the launch. The tombstone's `error` is the only record a
    human ever sees."""
    spec = _spec(world)
    paths = base.ExecPaths(spec.execution_id)
    real = config.write_atomic
    prompt = os.path.basename(paths.prompt)

    def write(path, data, *args, **kwargs):
        if os.path.basename(path) == prompt:
            return False
        return real(path, data, *args, **kwargs)
    config.write_atomic = write
    try:
        with pytest.raises(base.SpawnWriteFailed) as got:
            base.spawn(spec, ['x'])
    finally:
        config.write_atomic = real
    assert prompt in str(got.value)
    assert spec.isolation.launches == []                    # nothing was ever launched
    assert not os.path.exists(paths.pid)                    # and nothing to reconcile
    ended = base.read_json(paths.ended)
    assert ended['exit_code'] is None and prompt in ended['error']


def test_BA07_a_pid_that_cannot_be_written_kills_the_child_and_refuses(world, monkeypatch):
    """`spawn` base.py:367-371 (T-647#5): a child nobody recorded can be neither stopped
    nor reconciled, so a `pid.json` that cannot be written kills it and refuses with
    `SpawnWriteFailed` and an `ended` tombstone, and only then is `ended` true. Without
    the kill the tombstone would be false proof for a running process, and a resume
    would start a second one beside it."""
    spec = _spec(world)
    paths = base.ExecPaths(spec.execution_id)
    real = config.write_json_atomic
    killed = []

    def write(path, obj, **kwargs):
        if os.fspath(path) == paths.pid:
            raise OSError(28, 'No space left on device')
        return real(path, obj, **kwargs)
    monkeypatch.setattr(config, 'write_json_atomic', write)
    monkeypatch.setattr(base.proc, 'kill_tree', killed.append)
    with pytest.raises(base.SpawnWriteFailed) as got:
        base.spawn(spec, ['x'])
    assert 'could not record the process' in str(got.value)
    assert len(spec.isolation.launches) == 1
    assert [c.pid for c in killed] == [424242]
    assert not os.path.exists(paths.pid)
    assert base.read_json(paths.ended)['exit_code'] is None


def test_BA08_a_bug_in_the_launcher_is_not_a_spawn_failure_but_still_loses_the_keys(world):
    """`spawn` base.py:355-366: the `except BaseException` re-raises whatever came, and
    turns it into a tombstone + `SpawnFailed` only `if isinstance(err, OSError)`. Two
    halves, one test: a non-OSError is a bug and must reach the caller unchanged (the
    execution is not charged for it, and `ended` is NOT written, because writing a
    tombstone is Core's answer for a start that failed cleanly), and yet this attempt's
    `mcp.json` still goes — the third-party keys it copies are never left behind by a
    failed attempt (T-099)."""
    spec = _spec(world, isolation=FakeIsolation(fail=ValueError('a bug, not the disk')))
    paths = base.ExecPaths(spec.execution_id)
    os.makedirs(paths.res, exist_ok=True)
    with open(paths.mcp, 'w', encoding='utf-8') as f:
        f.write(json.dumps({'mcpServers': {'gh': {'headers': {'Authorization': '***'}}}}))
    with pytest.raises(ValueError, match='a bug, not the disk'):
        base.spawn(spec, ['x'])
    assert not os.path.exists(paths.mcp)                    # the keys went with it
    assert not os.path.exists(paths.ended)                  # and no end was claimed


def test_BA09_an_isolation_cannot_launch_then_a_resume_may_follow(world):
    """`spawn` base.py:361-365: `if isinstance(err, OSError): _refuse(paths, str(err),
    err)` — the launch's own failure, which `_start`'s `except OSError` never saw. It
    must be a `SpawnFailed` every caller handles (never an exception that stops the
    manager's thread, T-102), with the reason in the tombstone for the operator, the
    original exception as the cause, this attempt's MCP config gone, and NOTHING left
    that would stop the next attempt: because a refusal is not an end of a process
    that ran, the execution may be resumed once the boundary is back."""
    spec = _spec(world, isolation=FakeIsolation(fail=OSError(22, 'invalid handle')))
    paths = base.ExecPaths(spec.execution_id)
    with pytest.raises(base.SpawnFailed, match='invalid handle') as got:
        base.spawn(spec, ['x'])
    assert isinstance(got.value.__cause__, OSError)
    ended = base.read_json(paths.ended)
    assert ended['exit_code'] is None and 'invalid handle' in ended['error']
    assert not os.path.exists(paths.mcp) and not os.path.exists(paths.pid)

    # the same execution, boundary fixed: the refusal did not consume its resume
    again = dataclasses.replace(spec, process_seq=2, isolation=FakeIsolation())
    handle, _ = base.spawn(again, ['x'])
    assert handle.execution_id == spec.execution_id
    assert base.read_json(paths.pid)['process_seq'] == 2
    assert len(again.isolation.launches) == 1


# ---------------------------------------------------------------------- hostile stream

@pytest.mark.parametrize('raw, expect', [
    pytest.param(b'5\n', [{'type': 'stderr', 'text': '5'}], id='a bare number'),
    pytest.param(b'[1, 2]\n', [{'type': 'stderr', 'text': '[1, 2]'}], id='a bare array'),
    pytest.param(b'"a string"\n', [{'type': 'stderr', 'text': '"a string"'}],
                 id='a bare string'),
    pytest.param(b'null\n', [{'type': 'stderr', 'text': 'null'}], id='null'),
    pytest.param(b'true\n', [{'type': 'stderr', 'text': 'true'}], id='true'),
    pytest.param(b'{"a": 1}{"b": 2}\n', [{'type': 'stderr', 'text': '{"a": 1}{"b": 2}'}],
                 id='two events on one line'),
    pytest.param(b'{"broken": \n', [{'type': 'stderr', 'text': '{"broken":'}],
                 id='a torn object'),
    pytest.param(b'Traceback (most recent call last):\n',
                 [{'type': 'stderr', 'text': 'Traceback (most recent call last):'}],
                 id='a traceback'),
    pytest.param(b'{"type": "result", "usage": {"cost": 1.5}}\n',
                 [{'type': 'result', 'usage': {'cost': 1.5}}], id='an object passes through'),
])
def test_BA10_a_stream_line_that_is_not_an_object_is_kept_as_stderr(tmp_path, raw, expect):
    """`read_stream` base.py:644-648: `except ValueError: ev = None` and
    `events.append(ev if isinstance(ev, dict) else {'type': 'stderr', 'text': line})`.
    Valid JSON that is not an object parses and would be handed onward by
    `adapter.py:235` (`inspect`) into `normalise`, whose first line is
    `raw.get('type')` (adapter.py:62) — a bare `5` there is an AttributeError on the
    manager's thread, which is exactly the crash T-102 forbids — so it must arrive as a
    stderr event holding the exact text, and nothing may be dropped: a traceback or a
    bare `Killed` is just what a crash leaves behind. The contract it breaks is 3 (the
    CLI's output, all of it, in order)."""
    path = os.path.join(str(tmp_path), 'stream.jsonl')
    with open(path, 'wb') as f:
        f.write(raw)
    events, offset = base.read_stream(path)
    assert events == expect
    assert all(isinstance(ev, dict) for ev in events)       # never a bare value onward
    assert offset == os.path.getsize(path)                  # read once, not rescanned


@pytest.mark.parametrize('raw, expect', [
    pytest.param(b'{"t": "\xff\xfe"}\n', {'t': '\ufffd\ufffd'},
                 id='invalid utf-8 inside an object'),
    pytest.param(b'\xff\xfe not json at all\n',
                 {'type': 'stderr', 'text': '\ufffd\ufffd not json at all'},
                 id='invalid utf-8 that never was json'),
])
def test_BA11_a_stream_line_that_is_not_utf8_survives_as_an_event(tmp_path, raw, expect):
    """`read_stream` base.py:641: `raw.decode('utf-8', errors='replace')`. A CLI that
    writes a GBK byte or a truncated emoji must not raise (that exception stops the
    manager's thread) and must not lose the line: the undecodable byte becomes U+FFFD
    and the event still counts, once, with its text."""
    path = os.path.join(str(tmp_path), 'stream.jsonl')
    with open(path, 'wb') as f:
        f.write(raw)
    events, offset = base.read_stream(path)
    assert events == [expect]
    assert '\ufffd' in json.dumps(events[0], ensure_ascii=False)
    assert offset == os.path.getsize(path)


@pytest.mark.parametrize('raw, expect, end', [
    pytest.param(b'\n\n   \n{"a": 1}\n', [{'a': 1}], None, id='blank lines between events'),
    pytest.param(b'\n \n', [], None, id='a file of blank lines still advances'),
    pytest.param(b'', [], 0, id='an empty file'),
    pytest.param(b'{"a": 1}', [], 0, id='an event with no newline is left for later'),
    pytest.param(b'{"a": 1}\r\n{"b": 2}\r\n', [{'a': 1}, {'b': 2}], None, id='CRLF'),
    pytest.param(b'{"a": 1}\r{"b": 2}\n', [{'type': 'stderr', 'text': '{"a": 1}\r{"b": 2}'}], None,
                 id='a bare CR is not a line end'),
    pytest.param(b'{"a": 1}\n{"b": 2}\n', [{'a': 1}, {'b': 2}], None, id='two events'),
])
def test_BA12_the_stream_is_read_in_complete_lines_from_an_exact_byte_offset(tmp_path, raw,
                                                                             expect, end):
    """`read_stream`: `f.readline` ends a line on LF only (a bare CR does not), a line
    without one is left for later, `if not line: continue`, and the returned offset
    counts every consumed byte. The offset is the only thing between "every event, in order" and
    duplicate or lost events, so it advances over exactly the bytes that were consumed —
    including the blank ones — and stops before a trailing partial line, which the next
    read picks up. `end` is the expected offset when it is not the whole file."""
    path = os.path.join(str(tmp_path), 'stream.jsonl')
    with open(path, 'wb') as f:
        f.write(raw)
    events, offset = base.read_stream(path)
    assert events == expect
    assert offset == (len(raw) if end is None else end)
    assert base.read_stream(path, offset) == ([], offset)   # nothing is ever read twice
    # an offset past the end is not an error and loses nothing
    assert base.read_stream(path, len(raw) + 100) == ([], len(raw) + 100)


# ---------------------------------------------------------------------- offered variables

@pytest.mark.parametrize('token', [
    pytest.param('hook_', id='the prefix alone'),
    pytest.param('hook_ok\n', id='a token with a newline after it'),
    pytest.param('hook_ok\nsecond', id='two tokens in one value'),
    pytest.param('hook_ok b', id='a token with a space in it'),
    pytest.param('hook_ok\tb', id='a token with a tab in it'),
    pytest.param('hook_ok;b=1', id='a token with a shell metacharacter in it'),
    pytest.param('hook_ok.env', id='a token with a dot in it'),
    pytest.param('hook_/etc/passwd', id='a token that is a path'),
    pytest.param('HOOK_' + 'A' * 43, id='the wrong prefix case'),
    pytest.param('\u2014hookx' + 'A' * 38, id='a lookalike prefix'),
])
def test_BA13_a_hook_token_that_is_not_a_token_refuses_the_spawn_before_anything_starts(
        world, token):
    """`_isolated_env` base.py:560-562: `if not _HOOK_TOKEN.fullmatch(v): raise
    ValueError('ARCHEUS_HOOK_TOKEN is not a hook token')`, with
    `_HOOK_TOKEN = re.compile(r'hook_[A-Za-z0-9_-]+')` (base.py:41), raised through
    `_start` base.py:404-407. The token is what the guard stands a hook down for, so a
    value Core did not mint — an empty tail, a stray newline (a second value to anything
    that splits the line), a space, a tab, the wrong prefix case, a non-ASCII lookalike
    of it — must refuse the whole spawn, name the variable and never the value, and
    above all never reach the launch. `fullmatch`, not `match`: drop the anchor and
    `'hook_ok; curl -s evil'` is a token and the child's environment carries it."""
    spec = _spec(world, env={'ARCHEUS_HOOK_TOKEN': token})
    with pytest.raises(base.SpawnFailed) as got:
        base.spawn(spec, ['x'])
    assert 'ARCHEUS_HOOK_TOKEN' in str(got.value)
    assert token not in str(got.value)                      # named, never quoted
    assert token not in json.dumps(base.read_json(base.ExecPaths(spec.execution_id).ended))
    assert spec.isolation.launches == []


def test_BA14_the_shape_core_mints_is_accepted_reaching_the_child_unchanged(world):
    """The other side of base.py:560-562 and base.py:41: `manager.py:278` mints
    `'hook_' + secrets.token_urlsafe(32)`, whose alphabet is `A-Za-z0-9-_` — the `-` and
    `_` included — and `_HOOK_TOKEN` carries no length bound at all. Tighten the class
    (drop `-` or `_`) or add a bound, and every execution whose hooks were issued a
    token becomes a spawn that cannot start: a refusal that reads as a broken harness,
    with nothing on disk saying "the token". The accepted value must also reach the
    child byte for byte, because the hook posts it back and a mangled one verifies as no
    hook at all (contract 6)."""
    minted = 'hook_' + 'aB9-_' * 8 + 'Z'                   # the alphabet token_urlsafe
    assert '-' in minted and '_' in minted                  # gives: `-` and `_` included
    spec = _spec(world, env={'ARCHEUS_HOOK_TOKEN': minted})
    base.spawn(spec, ['x'])
    assert len(spec.isolation.launches) == 1
    assert spec.isolation.launches[0]['env']['ARCHEUS_HOOK_TOKEN'] == minted
    # and a token of any length still spawns: `_HOOK_TOKEN` bounds the alphabet and the
    # prefix, never the length, so no second, undocumented rule decides what may start
    # (whoever CHECKS a token has its own bound; refusing here would move that rule into
    # the spawner and turn it into a spawn failure)
    long_spec = _spec(world, env={'ARCHEUS_HOOK_TOKEN': 'hook_' + 'aB9-_' * 9})
    base.spawn(long_spec, ['x'])
    assert len(long_spec.isolation.launches) == 1


def test_BA15_the_private_config_is_matched_by_where_it_is_not_by_its_spelling(world):
    """`_isolated_env` base.py:563-567: `same = {os.path.normcase(os.path.realpath(x))
    for x in (v, paths.config)}` and `if len(same) != 1`. An adapter may name the
    execution's private `CLAUDE_CONFIG_DIR` in an equivalent spelling — up through the
    directory it sits in and back, with a trailing separator — and that IS the config it
    is allowed to have; a directory that merely resembles it (a sibling, a name with
    this one as its prefix) is another execution's config, or the user's real one, and
    refuses. Compare the strings instead of the resolved paths and Core refuses its own
    adapter; compare prefixes and an execution is handed someone else's logins."""
    good = _spec(world)
    paths = base.ExecPaths(good.execution_id)
    spelled = os.path.join(paths.state, '..', 'state', 'config') + os.sep
    ok = dataclasses.replace(good, env={'CLAUDE_CONFIG_DIR': spelled})
    base.spawn(ok, ['x'])
    assert len(ok.isolation.launches) == 1
    # the offered spelling was accepted as a name for the private config, and what the
    # child is given is Core's own derived path (base.py:567 `continue`s before the
    # `out[name] = v` below it): the child never carries a path Core did not derive
    assert ok.isolation.launches[0]['env']['CLAUDE_CONFIG_DIR'] == paths.config

    evil = _spec(world)
    evil_paths = base.ExecPaths(evil.execution_id)
    evil = dataclasses.replace(evil, env={'CLAUDE_CONFIG_DIR': evil_paths.config + '-other'})
    with pytest.raises(base.SpawnFailed) as got:
        base.spawn(evil, ['x'])
    assert 'CLAUDE_CONFIG_DIR' in str(got.value) and '-other' not in str(got.value)
    assert evil.isolation.launches == []


# ---------------------------------------------------------------------- the keys left over

def test_BA16_an_end_that_cannot_be_written_still_takes_the_keys_with_it(world):
    """`mark_ended` base.py:577-580: the `finally: drop_mcp_config(paths)`. The MCP
    config is a copy of the user's opted-in third-party servers WITH their headers, in
    the execution's own `res/`; the tombstone is Core's record of the end. When the
    record cannot be written the keys must still go — a `try` whose drop follows the
    write is one un-writable disk away from leaving them behind for good (only the boot
    sweep would). The contract it breaks is 8."""
    spec = _spec(world)
    paths = base.ExecPaths(spec.execution_id)
    os.makedirs(paths.res, exist_ok=True)
    with open(paths.mcp, 'w', encoding='utf-8') as f:
        f.write(json.dumps({'mcpServers': {'gh': {'headers': {'Authorization': '***'}}}}))
    with open(paths.mcp + '.4242.tmp', 'w', encoding='utf-8') as f:
        f.write('{"mcpServers": {"gh": {"headers": {"Authorization": "***"}}}}')
    real = config.write_json_atomic

    def write(path, obj, **kwargs):
        if os.fspath(path) == paths.ended:
            return False
        return real(path, obj, **kwargs)
    config.write_json_atomic = write
    try:
        with pytest.raises(OSError):
            base.mark_ended(paths, 0)
    finally:
        config.write_json_atomic = real
    assert not os.path.exists(paths.ended)                  # the record did not appear
    assert not os.path.exists(paths.mcp)                    # the keys went anyway
    assert not os.path.exists(paths.mcp + '.4242.tmp')      # and its temp copy with it


def test_BA17_a_key_file_that_cannot_be_removed_is_logged_not_raised(world, caplog,
                                                                     monkeypatch):
    """`drop_mcp_config` base.py:597-604: the `except OSError as err: log.warning(...)`.
    An end that is happening must not be lost because one file is stuck (its directory
    busy, its file held by another process), so the failure is logged with the execution
    id — the only thing that makes it findable — and the sweep retries; and the OTHER
    copies in the same directory are still removed. Swallowing the warning instead of
    logging it is the failure: a key file that quietly never goes is a leak nobody sees."""
    spec = _spec(world)
    paths = base.ExecPaths(spec.execution_id)
    os.makedirs(paths.res, exist_ok=True)
    for name in (base.MCP_CONFIG, base.MCP_CONFIG + '.7.tmp'):
        with open(os.path.join(paths.res, name), 'w', encoding='utf-8') as f:
            f.write('{"mcpServers": {}}')
    real_remove = os.remove

    def remove(path, *args, **kwargs):
        if os.fspath(path) == paths.mcp:
            raise PermissionError(13, os.fspath(path))
        return real_remove(path, *args, **kwargs)
    monkeypatch.setattr(os, 'remove', remove)
    with caplog.at_level('WARNING', logger='archeus.harnesses'):
        base.drop_mcp_config(paths)                         # never raises
    assert 'its MCP config was not removed' in caplog.text
    assert paths.execution_id in caplog.text                # findable from the warning
    assert base.MCP_CONFIG + '.7.tmp' not in _files(paths.res)


def test_BA18_an_execution_that_wrote_nothing_is_swept_without_an_error():
    """`drop_mcp_config` base.py:592-596 (`except OSError: tmps = []`, "no res directory:
    nothing was written") and `sweep_mcp_configs` base.py:610-614 (`except
    FileNotFoundError: return`). Both run on paths that may not exist — the sweep runs at
    boot over a `run/exec` that a first run never created, and a drop runs for an
    execution refused before its directories were made. Raise there and Core does not
    boot, or an end that was happening is lost. The contract it breaks is 1: a Core that
    cannot come up serves nothing."""
    paths = base.ExecPaths(ids.new_id('execution'))
    assert not os.path.isdir(os.path.dirname(paths.mcp))    # the premise: nothing was made
    base.drop_mcp_config(paths)                             # no raise
    assert not os.path.isdir(os.path.join(base.run_dir(), 'exec'))    # the premise
    assert base.sweep_mcp_configs(set()) is None


# ------------------------------------------------------------------------------ _inside

@pytest.mark.parametrize('entry, roots, expect', [
    pytest.param('banned', ['banned'], True, id='the banned directory itself'),
    pytest.param('banned/sub', ['banned'], True, id='below it'),
    pytest.param('banned-evil', ['banned'], False,
                 id='a sibling that only shares its prefix'),
    pytest.param('banned/../banned-evil', ['banned'], False,
                 id='a spelling that walks out of it'),
    pytest.param('other', ['banned'], False, id='unrelated'),
    pytest.param('banned', [], False, id='nothing is banned'),
])
def test_BA19_a_path_is_inside_another_only_below_it_not_beside_it(tmp_path, entry, roots,
                                                                   expect):
    """`_inside` base.py:458-464: `if a == b or a.startswith(b.rstrip(os.sep) + os.sep)`
    with `a`/`b` the normcased `realpath` of the two. This one predicate decides which
    PATH entries reach an isolated process (base.py:537), which verifier toolchain
    directories are refused as "inside the scratch" (base.py:498) and whether SystemRoot
    counts as banned (base.py:478), so both halves matter: drop the `+ os.sep` and a
    directory bans its own siblings by name-prefix (`C:\\tools` bans `C:\\toolsmith`, and
    the agent starts with a PATH it cannot run from); drop the `startswith` and a
    `banned-evil` counts as inside `banned`, which is the trivial way to put a user's
    account tree back on a child's PATH. Everything is joined under *tmp_path*, so the
    same assertion holds whatever the drive separator is."""
    def real(p):
        return os.path.join(str(tmp_path), p)
    for d in (os.path.join('banned', 'sub'), 'banned-evil', 'other'):
        os.makedirs(real(d), exist_ok=True)
    assert base._inside(real(entry), [real(r) for r in roots]) is expect


@pytest.mark.skipif(sys.platform == 'win32', reason='a POSIX symlink; on Windows the '
                                                    'equivalent is a junction, and the '
                                                    'point is what realpath resolves')
def test_BA20_a_link_into_a_banned_tree_is_inside_it(tmp_path):
    """`_inside` base.py:459 and 461: `os.path.realpath(...)`, applied before the
    comparison. An entry that is a symlink into the account's home IS an entry into the
    account's home: the child would be handed a PATH directory it can write through to
    the user's credentials. Compare the given string instead of the resolved one and the
    ban is walked around by anyone who can name a directory."""
    home = str(tmp_path / 'account-home')
    os.makedirs(os.path.join(home, '.claude'))
    link = str(tmp_path / 'tools-link')
    os.symlink(os.path.join(home, '.claude'), link)
    assert base._inside(link, [home]) is True
    assert base._inside(link + os.sep, [home]) is True
    # and a link that points out of the banned tree is not inside it
    outside = str(tmp_path / 'tools')
    os.makedirs(outside)
    out_link = str(tmp_path / 'tools-link-out')
    os.symlink(outside, out_link)
    assert base._inside(out_link, [home]) is False


# ------------------------------------------------------------------ one home, one account

def test_BA22_one_real_home_is_one_account_key_whichever_way_it_is_written(world, monkeypatch):
    """`canonical_home` base.py:61-64 (`normcase(abspath(expanduser(home)))`) and
    `default_ref` base.py:67-73 (key `<harness>:<canonical home>`, `home_ref` the
    absolute real path). This is what an account IS in the ledger and what session
    discovery reads: write one home four ways and get four accounts, and the same
    login has four policies, four rate ledgers and four sets of sessions — and the two
    "different" accounts are the same credentials. The other half is `home_ref`: the
    folding belongs to the key only, because the process must run exactly where the
    user's own CLI runs (base.py:71-72), so a folded key must never become the path."""
    home = os.path.join(world['account'], 'Dot-Claude')
    os.makedirs(home, exist_ok=True)
    monkeypatch.setenv('HOME', world['account'])            # what `~` means here
    monkeypatch.setenv('USERPROFILE', world['account'])
    forms = [home, home + os.sep, os.path.join(os.path.dirname(home), '.', 'Dot-Claude'),
             os.path.join(world['account'], 'Dot-Claude', '..', 'Dot-Claude'),
             os.path.join('~', 'Dot-Claude')]
    keys = {base.canonical_home(f) for f in forms}
    assert len(keys) == 1 and keys == {base.canonical_home(home)}
    ref = base.default_ref('claude_code', forms[1])
    assert ref.account_id == 'claude_code:%s' % base.canonical_home(home)
    assert ref.home_ref == os.path.abspath(home)            # never the folded key
    assert ref.home_ref.endswith('Dot-Claude')              # the case the user typed
    # a different home, and a different harness on the same home, are different accounts
    other = os.path.join(world['account'], 'Dot-Claude-Extra')
    assert base.canonical_home(other) != base.canonical_home(home)
    assert base.default_ref('pi', home).account_id != ref.account_id
    assert base.default_ref('pi', home).home_ref == ref.home_ref


# ------------------------------------------------------------------- the broker binding

@pytest.mark.parametrize('port, token', [
    pytest.param(80, 'brk_', id='the prefix alone'),
    pytest.param(80, 'brk_a\n', id='a token with a newline after it'),
    pytest.param(80, 'brk_a\nb', id='two tokens in one value'),
    pytest.param(80, 'brk_a;b=1', id='a token with a metacharacter in it'),
    pytest.param(80, None, id='no token at all'),
    pytest.param(80, 42, id='a token that is a number'),
    pytest.param(80, b'brk_a', id='a token that is bytes'),
])
def test_BA21_a_broker_binding_that_is_not_a_port_and_a_token_is_a_valueerror(port, token):
    """`BrokerLaunch.__post_init__` base.py:125-129: `if not (isinstance(self.token, str)
    and _BROKER_TOKEN.fullmatch(self.token)): raise ValueError('not a broker token')`.
    The `isinstance` half is not decoration: drop it and `fullmatch(None)` raises
    TypeError, which is not the `ValueError` an election path handles, so a bad binding
    becomes a crash in the manager's thread instead of a refusal (T-102). The empty-tail,
    newline and metacharacter cases are the base.py:42 pattern's boundary — this token is
    the child's only credential to the broker, and `brk_` alone is the shape of "no
    credential", which the bridge would accept as a match against nothing."""
    with pytest.raises(ValueError):             # never TypeError: callers handle this one
        base.BrokerLaunch(port, token)
