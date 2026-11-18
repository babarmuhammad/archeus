"""T-723: the highest-risk uncovered branches of
`archeus/harnesses/claude_code/adapter.py`.

Style and fixtures follow the closest existing tests of this module:
`tests/v1/unit/test_pv20_private_config.py`, which fakes the two seams
`base.spawn` reaches the OS through (`base.proc.spawn_detached`,
`proc.process_create_time`) so that no process is ever started, and
`tests/v1/contract/test_adapter_contract.py`, which reads an execution directory
of raw bytes back through `inspect` / `collect_result`. Same seams, same shape,
no new dependency. No process, no network, no sleep, nothing that needs one
platform over the other: every OS call is faked at those seams, stream and
contract files are written as bytes with the newlines this file chooses, and no
assertion reads an environment value or an OS error message.

The emphasis is the three things the card names. (1) The stream is the child's
own stdout, so any field may be of any type: what the adapter must never do is
raise out of `normalise`, invent a field Core trusts, or let the child's own
words decide who owns the end of the execution. (2) The hook payload: the one
settings file the adapter writes is the gate on every tool call, so what it
installs, and the two timeouts it carries, are read back from disk. (3) Session
discovery: the session id a finished execution reports is the only thing a
resume has to continue, and a resume that cannot find it must refuse rather than
start a fresh conversation.

Each test below names, in its docstring, the source branch whose removal or
inversion it would catch.
"""

import dataclasses
import itertools
import json
import os
import sys

import pytest
from claude_sessions import usage

from archeus.core.domain import ids
from archeus.harnesses import base
from archeus.harnesses.claude_code import adapter as cc
from archeus.harnesses.claude_code.adapter import normalise

PID = 424242                                  # the fake child's pid, always free
CREATED = 1712345678.5                        # its opaque create time
HOOK = (os.sep + 'x', 'hook.py')              # an argv: one part with a separator
STREAM = 'stream.jsonl'


# ── the seams: no process, no OS ──────────────────────────────────────

class FakeChild:
    """Only what the adapter ever asks a `Popen`: its pid, and its exit code."""

    def __init__(self, pid=PID):
        self.pid = pid
        self.code = None

    def poll(self):
        return self.code


class Launcher:
    """The two OS calls of `base.spawn` (the seams `test_pv20_private_config.py`
    fakes) plus the two of `stop`. `alive` is the OS's process table: a pid in it
    is a live process with that create time, and `kill_pid_tree` answers exactly
    as `proc.kill_pid_tree` does — True when it killed the process it was named
    for, False when the pair did not name a live one."""

    def __init__(self):
        self.alive = {PID: CREATED}
        self.rows = []
        self.children = []
        self.attempts = []                        # every ask to kill, refused or not
        self.kills = []                           # only the ones that killed

    def _child(self, pid):
        child = FakeChild(pid)
        self.children.append(child)
        return child

    def _record(self, kind, argv, cwd, env):
        self.rows.append({'kind': kind, 'argv': [str(a) for a in argv],
                          'cwd': cwd, 'env': dict(env)})

    def detached(self, argv, *, cwd, env, **kw):
        self._record('detached', argv, cwd, env)
        return self._child(PID), None

    def launch(self, argv, *, cwd, env, paths):
        self._record('isolated', argv, cwd, env)
        return self._child(PID), None

    def create_time(self, pid):
        try:
            return self.alive.get(int(pid))
        except (TypeError, ValueError):
            return None

    def kill(self, pid, create_time):
        self.attempts.append((pid, create_time))
        if create_time is None or self.alive.get(pid) != create_time:
            return False
        del self.alive[pid]
        self.kills.append((pid, create_time))
        return True

    @property
    def last(self):
        return self.rows[-1]


@pytest.fixture
def launch(monkeypatch):
    launcher = Launcher()
    monkeypatch.setattr(base.proc, 'spawn_detached', launcher.detached)
    monkeypatch.setattr(base.proc, 'process_create_time', launcher.create_time)
    monkeypatch.setattr(base.proc, 'kill_pid_tree', launcher.kill)
    return launcher


def _home(tmp_path):
    home = tmp_path / 'account-home'
    home.mkdir(exist_ok=True)
    return str(home)


def _spec(tmp_path, **kw):
    home = kw.pop('home', None) or _home(tmp_path)
    kw.setdefault('account', base.AccountRef('claude_code:test', home))
    kw.setdefault('task_contract', {'action_classes': [], 'estimate': 3})
    kw.setdefault('prompt', 'do the thing')
    return base.ExecutionSpec(execution_id=ids.new_id('execution'),
                              workdir=str(tmp_path), **kw)


def _bytes(lines):
    """The stream as the child's stdout left it: raw bytes, the newlines chosen
    here, never the platform's."""
    return b''.join((line if isinstance(line, (bytes, bytearray))
                     else json.dumps(line).encode('utf-8')) + b'\n' for line in lines)


def _write(path, data):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data if isinstance(data, (bytes, bytearray)) else
                json.dumps(data, indent=1).encode('utf-8'))


_DIRS = itertools.count()                      # one directory per call: no test reads
                                               # another call's `ended` or stream


def _exec_dir(tmp_path, *lines, ended=None, halted=False):
    """A finished execution directory: its stream, its `ended` tombstone, its
    halt report — whatever the test needs, all under `tmp_path`."""
    d = os.path.join(str(tmp_path), 'exec-%d' % next(_DIRS))
    os.makedirs(d, exist_ok=True)
    if lines:
        _write(os.path.join(d, STREAM), _bytes(lines))
    if ended is not None:
        _write(os.path.join(d, 'ended'), ended)
    if halted:
        _write(os.path.join(d, 'req', 'halted.json'), {'reason': 'ask'})
    return d


def _handle(exec_dir, pid=2 ** 22 + 7, create_time='gone'):
    return base.ProcessHandle(ids.new_id('execution'), pid, create_time, exec_dir)


def _adapter():
    return cc.ClaudeCodeAdapter(exe='claude')


def _flag(argv, name):
    return argv[argv.index(name) + 1] if name in argv else None


def _events(*raw):
    return [ev for line in raw for ev in normalise(line)]


def _result(**kw):
    raw = {'type': 'result', 'subtype': 'success', 'is_error': False, 'result': 'done'}
    raw.update(kw)
    return raw


# ── the stream is the child's own stdout ─────────────────────────────

def test_g01_a_stderr_line_is_passed_through_exactly_as_the_reader_left_it():
    """adapter.py:63-64 (`if t == 'stderr': return [raw]`). `base.read_stream`
    hands back every line that is not a JSON object as `{'type': 'stderr',
    'text': ...}`; that branch is what keeps a traceback in front of Core. An
    inversion (or a `pass`) drops the crash evidence of exactly the runs that
    need reading, and a rewrite of `raw` would lose the reader's own fields."""
    line = {'type': 'stderr', 'text': 'Traceback (most recent call last):'}
    assert normalise(line) == [line] and normalise(line)[0] is line
    # a hostile child can name its own line stderr with anything in it: it is
    # still passed through, and still nothing else (no invented assistant turn)
    assert normalise({'type': 'stderr', 'text': 'x', 'result': 'y'}) == [
        {'type': 'stderr', 'text': 'x', 'result': 'y'}]
    assert _events({'type': 'unknown'}) == []


def test_g02_an_assistant_line_carries_every_field_core_reads_even_where_the_child_omitted_it():
    """adapter.py:71-76. The child writes its own blocks: a `text` block with no
    `text`, a `tool_use` with no name, input or id. The event keys are the
    contract Core reads (`KeyError` in a tailing loop is a lost execution), so
    the missing fields become `''`/None and the present ones are handed on
    verbatim; a block that is not an object, a `content` that is not a list and a
    `message` that is not an object contribute nothing rather than raising."""
    (text,) = normalise({'type': 'assistant', 'message': {'content': [{'type': 'text'}]}})
    assert text == {'type': 'assistant', 'text': '', 'lane': None}
    (tool,) = normalise({'type': 'assistant', 'parent_tool_use_id': 'tu_1',
                         'message': {'content': [{'type': 'tool_use'}]}})
    assert tool == {'type': 'tool', 'name': None, 'input': None, 'id': None, 'lane': 'tu_1'}
    # what the child does say is said unchanged, including a hostile input object
    (kept,) = normalise({'type': 'assistant', 'message': {'content': [
        {'type': 'tool_use', 'name': 'Bash', 'id': 't9', 'input': {'command': 'rm -rf /'}}]}})
    assert kept['input'] == {'command': 'rm -rf /'} and kept['name'] == 'Bash'
    # nothing usable: no event at all, never a half one
    for raw in ({'type': 'assistant'}, {'type': 'assistant', 'message': 'x'},
                {'type': 'assistant', 'message': {'content': 'x'}},
                {'type': 'assistant', 'message': {'content': {'type': 'text'}}},
                {'type': 'assistant', 'message': {'content': ['x', 7, None]}},
                {'type': 'assistant', 'message': {'content': [{'no_type': 1}]}}):
        assert normalise(raw) == []


def test_g03_the_served_model_is_recorded_only_for_a_string_that_names_one():
    """adapter.py:79-81 (`isinstance(msg.get('model'), str) and msg['model'] not
    in ('', '<synthetic>')`). This is the SERVED model of ADR-0031 §6: the
    ledger's provenance and the model an execution is charged for. An inversion
    of the `<synthetic>` test, or of the empty string, bills work to a model that
    never answered, and dropping the `isinstance` test lets the child name the
    model with an object Core then treats as a name."""
    def models(model):
        got = normalise({'type': 'assistant', 'message': {'model': model, 'content': []}})
        return [e['model'] for e in got if e['type'] == 'model']

    assert models('claude-haiku-4-5-20251001') == ['claude-haiku-4-5-20251001']
    for not_a_name in ('', '<synthetic>', None, 425, ['sonnet'], {'x': 1}, True):
        assert models(not_a_name) == [], not_a_name
    # a usage that is not an object is no usage, and one that is is handed on whole
    assert [e['type'] for e in normalise(
        {'type': 'assistant', 'message': {'usage': 'many', 'content': []}})] == []
    assert normalise({'type': 'assistant', 'message': {'usage': {'input_tokens': 3},
                                                      'content': []}})[-1] == {
        'type': 'usage', 'usage': {'input_tokens': 3}}


def test_g04_the_reported_summary_is_cut_at_exactly_two_thousand_characters():
    """adapter.py:88 (`str(raw.get('result') or '')`) with 95 (`text[:2000]`).
    This is the one bound on what the child can make Core store, show and
    re-read: off by one here either loses a character of a real answer or lets an
    unbounded line through, and without the `str(...)` a `result` that is a list
    or a number would reach Core as a non-string."""
    short = 'k' * 1999
    assert _events(_result(result=short))[0]['summary'] == short
    exact = 'k' * 2000
    assert _events(_result(result=exact))[0]['summary'] == exact
    long_ = 'k' * 4500
    cut = _events(_result(result=long_))[0]['summary']
    assert len(cut) == 2000 and long_.startswith(cut)
    assert _events(_result(result=425))[0]['summary'] == '425'
    for missing in (None, {}, [], False):
        assert _events(_result(result=missing))[0]['summary'] == ''


def test_g05_a_cost_of_zero_is_a_cost_and_a_usage_that_is_not_an_object_is_no_usage():
    """adapter.py:89-91 (`usage = dict(_dict(...))`, `if raw.get('total_cost_usd')
    is not None`). The inversion to a truthiness test loses a run that cost
    nothing on the meter — indistinguishable from a run whose cost was never
    reported — and a `usage` the child invented as a string would be merged into
    the ledger by Core as one."""
    (res,) = _events(_result(usage={'input_tokens': 9}, total_cost_usd=0))
    assert res['usage'] == {'input_tokens': 9, 'total_cost_usd': 0}
    (res,) = _events(_result(usage={'input_tokens': 9}, total_cost_usd=None))
    assert res['usage'] == {'input_tokens': 9}
    (res,) = _events(_result(usage={'input_tokens': 9}))
    assert res['usage'] == {'input_tokens': 9}
    for not_an_object in ('many', 7, ['tokens'], None):
        (res,) = _events(_result(usage=not_an_object, total_cost_usd=1.5))
        assert res['usage'] == {'total_cost_usd': 1.5}


@pytest.mark.parametrize('text, window', [
    ('You have hit your weekly limit. Resets in 3 days.', True),
    ('usage limit reached', True),
    ('out of quota', True),
    ('rate limited, retry in 2 seconds', False),
    ('too many requests', False),
    ('Error: status code": 429', False),
], ids=('weekly', 'usage', 'quota', 'rate', '429-words', '429-status'))
def test_g06_only_an_error_result_that_names_a_limit_is_a_limit(text, window):
    """adapter.py:92-93 (`if raw.get('is_error') and quota.is_limit_error(text)`
    with `is_window_limit`). The limit event is what stops Core spending another
    account's headroom, so it fires on the provider's own wording and only on an
    error: a warning that merely mentions a limit must not latch an account out,
    and an error that names no limit must not be read as one. `window` is the
    distinction between "wait a moment" and "this account is spent": a wrong
    answer there rotates an account that was fine."""
    (limit, res) = _events(_result(is_error=True, result=text))
    assert (limit['type'], res['type']) == ('limit', 'result')
    assert limit['window'] is window and limit['text'] == text
    assert res['is_error'] is True
    # the same words, not an error: no limit at all (and still a result)
    (res,) = _events(_result(is_error=False, result=text))
    assert res['is_error'] is False and res['summary'] == text
    # and no `is_error` field either way
    assert [e['type'] for e in _events({'type': 'result', 'result': text})] == ['result']
    # a limit refusal with no text of its own is not a limit: `text` is `str('')`
    assert [e['type'] for e in _events(_result(is_error=True, result=None))] == ['result']


def test_g07_a_billed_models_object_that_is_not_an_object_bills_nothing():
    """adapter.py:94-99 (`sorted(billed) if isinstance(billed, dict) else []`).
    BILLED is the usage's attribution (ADR-0031 §6): a `modelUsage` the child
    invented as a list or a string must attribute nothing, and the names it does
    carry are handed on sorted, so the record of one run is one record."""
    assert _events(_result(modelUsage=['a', 'b']))[0]['billed'] == []
    assert _events(_result(modelUsage='claude-x'))[0]['billed'] == []
    assert _events(_result(modelUsage=None))[0]['billed'] == []
    assert _events(_result())[0]['billed'] == []
    assert _events(_result(modelUsage={'claude-y': {}, 'claude-x': {}}))[0]['billed'] == [
        'claude-x', 'claude-y']


def test_g08_billed_models_with_keys_of_two_kinds_are_never_a_crash_nor_a_name():
    """adapter.py:99: `sorted(billed)` over a dict the child wrote. `{1: ...,
    'claude-x': ...}` is a dict, so g07's `isinstance` guard passes and `sorted`
    compares an int with a str — the `TypeError` escapes `normalise`, which is
    the one function whose whole promise is that the child cannot make it raise
    (adapter.py:59-61). The assertion is the invariant rather than one fix: the
    attribution is a sorted list of model names, and a key the child did not
    write as a string is not a name. Either adequate fix — attribute nothing, or
    keep the string keys — turns this red as XPASS; a fix that sorted the keys
    with `key=str` would keep the integer in the ledger and still be wrong."""
    billed = _events(_result(modelUsage={1: {}, 'claude-x': {}}))[0]['billed']
    assert billed == ['claude-x']


@pytest.mark.parametrize('is_error', ['yes', 1, [0], {'a': 1}, 'false'],
                         ids=('text', 'one', 'list', 'dict', 'the-word-false'))
def test_g09_a_tool_result_is_error_only_when_the_child_said_so_and_is_always_answered(
        is_error):
    """adapter.py:83-86 (`bool(block.get('is_error'))`, `block.get('tool_use_id')`).
    The is_error of a tool result is what a failing call looks like to Core; a
    truthy stand-in of any shape is True (including the string 'false', which is
    what a truthiness test would have got wrong), a tool_use_id the child forgot
    is None rather than a missing key, and a `user` line that carries nothing
    readable carries no event."""
    events = _events({'type': 'user', 'message': {'content': [
        {'type': 'tool_result', 'tool_use_id': 't1', 'is_error': is_error},
        {'type': 'tool_result'}, {'type': 'text'}, 'junk', None]}},
        {'type': 'user'}, {'type': 'user', 'message': 'x'},
        {'type': 'user', 'message': {'content': {'tool_use_id': 't2'}}})
    assert events == [{'type': 'tool_result', 'is_error': True, 'tool_use_id': 't1',
                       'lane': None},
                      {'type': 'tool_result', 'is_error': False, 'tool_use_id': None,
                       'lane': None}]
    # the system line, which is where a session id first appears (g29)
    assert _events({'type': 'system'}) == [{'type': 'system', 'subtype': None,
                                            'session_id': None}]
    assert _events({'type': 'system', 'subtype': 'init', 'session_id': 's1'}) == [
        {'type': 'system', 'subtype': 'init', 'session_id': 's1'}]


def test_g10_the_reader_hands_the_adapter_every_line_it_wrote_and_nothing_still_arriving(
        tmp_path, launch):
    """adapter.py:234-236 (`inspect` -> `base.read_stream` + `normalise`). The child
    writes stdout and stderr into one file, so the adapter must keep the events
    it understands, turn the rest into the stderr evidence of g01, and never read
    a line that is still being written: the offset it returns is where the next
    read starts, and an offset that moved past a partial line loses an event for
    good."""
    d = os.path.join(str(tmp_path), 'exec')
    os.makedirs(d)
    path = os.path.join(d, STREAM)
    with open(path, 'wb') as f:
        f.write(b'{"type": "system", "subtype": "init", "session_id": "s1"}\n'
                b'Traceback (most recent call last):\n'
                b'[1, 2]\n'
                b'\xff\xfe not utf-8\n'
                b'{"type": "assistant", "message": {"content": [{"type": "tex')
    handle = _handle(d)
    snap = _adapter().inspect(handle)
    types = [e['type'] for e in snap.events]
    assert types == ['system', 'stderr', 'stderr', 'stderr'], snap.events
    assert snap.events[0]['session_id'] == 's1'
    assert snap.events[1]['text'].startswith('Traceback')
    assert snap.offset == os.path.getsize(path) - len(b'{"type": "assistant", "message"'
                                                     b': {"content": [{"type": "tex')
    with open(path, 'ab') as f:
        f.write(b't"}], "model": "claude-x"}}\n')
    more = _adapter().inspect(handle, snap.offset)
    assert [e['type'] for e in more.events] == ['assistant', 'model']
    assert more.offset == os.path.getsize(path)
    # a stream that is not there yet is nothing read, and the offset does not move
    gone = _handle(os.path.join(str(tmp_path), 'nothing'))
    assert _adapter().inspect(gone, 41) == base.Snapshot((), 41)


# ── the hook payload: the one file the adapter writes ────────────────

def _settings(spec):
    path = _adapter()._settings(spec)
    assert path == os.path.join(base.ExecPaths(spec.execution_id).res, 'settings.json')
    assert os.path.isfile(path)
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def test_g11_no_hook_asked_for_means_no_hook_installed_and_no_preflight_switch_without_a_broker(
        tmp_path):
    """adapter.py:139-153 (`if spec.hook_settings:` at 144, `if spec.broker is not
    None:` at 151). An empty `hooks` object is the honest answer to "Core asked for no
    gate": a half-built PreToolUse entry with an empty command would make Claude
    Code fail open on every call. And `skipWebFetchPreflight` belongs to a
    brokered process only: written without one it silently changes what an
    unbrokered CLI fetches."""
    doc = _settings(_spec(tmp_path))
    assert doc == {'hooks': {}}
    assert 'skipWebFetchPreflight' not in doc
    doc = _settings(_spec(tmp_path, broker=base.BrokerLaunch(54321, 'brk_a1b2')))
    assert doc == {'hooks': {}, 'skipWebFetchPreflight': True}


def test_g12_the_hook_is_installed_for_both_events_with_its_own_argv_and_both_timeouts(
        tmp_path):
    """adapter.py:144-149. Every part of the hook command is quoted and joined
    (a part with a separator in it stays one part: an unquoted path is a hook
    that never runs, and a hook that never runs lets every tool call through),
    PreToolUse is matched with `*` under `HOOK_TIMEOUT_S` and PreCompact under
    30 — the two numbers the design gate put on different clocks, so they are
    read apart here. The file is rewritten whole on every spawn, which is why a
    broker that went away does not leave its key behind (g11's other half)."""
    spec = _spec(tmp_path, hook_settings=(sys.executable, 'hook dir', 'hook.py'),
                 broker=base.BrokerLaunch(54321, 'brk_a1b2'))
    doc = _settings(spec)
    want = ' '.join('"%s"' % a for a in (sys.executable, 'hook dir', 'hook.py'))
    (pre,) = doc['hooks']['PreToolUse']
    (compact,) = doc['hooks']['PreCompact']
    assert pre['matcher'] == '*'
    assert 'matcher' not in compact
    assert [h['type'] for h in pre['hooks']] == ['command'] == [h['type'] for h in
                                                               compact['hooks']]
    assert [h['command'] for h in pre['hooks']] == [want] == [h['command']
                                                              for h in compact['hooks']]
    assert pre['hooks'][0]['command'].count('" "') == 2      # three quoted parts
    assert 'hook dir' in pre['hooks'][0]['command']
    assert doc['skipWebFetchPreflight'] is True
    again = _settings(_spec(tmp_path, hook_settings=(sys.executable, 'hook dir',
                                                     'hook.py')))
    assert again['hooks'] == doc['hooks'] and 'skipWebFetchPreflight' not in again


def test_g13_the_two_hook_deadlines_are_the_ones_the_design_names(tmp_path):
    """adapter.py:48 with 145-149 (`'timeout': HOOK_TIMEOUT_S` for PreToolUse,
    `'timeout': 30` for PreCompact). Swapping them puts the backstop on the long
    clock and the gate on the short one: a hook Claude Code times out is not
    documented to block the call, so a gate with too short a deadline is a gate
    that is not there, and a context backstop with too long one never arrives."""
    spec = _spec(tmp_path, hook_settings=HOOK)
    doc = _settings(spec)
    (pre,) = doc['hooks']['PreToolUse']
    (compact,) = doc['hooks']['PreCompact']
    assert pre['hooks'][0]['timeout'] == cc.HOOK_TIMEOUT_S == 120
    assert compact['hooks'][0]['timeout'] == 30
    assert compact['hooks'][0]['timeout'] < pre['hooks'][0]['timeout']


# ── the argv: what the process is told to be ─────────────────────────

def test_g14_an_estimate_outside_the_table_gets_the_default_bound_never_the_largest(
        tmp_path):
    """adapter.py:161 (`MAX_TURNS.get(int(spec.task_contract.get('estimate',
    3)), 60)`). `--max-turns` is the only thing that makes the agent bounded; an
    estimate the table does not know must fall to the middle default of 60, not
    to 100 (the largest, which an inversion of the lookup would hand to a task
    that named nothing) and not to no flag at all, which is unbounded."""
    def turns(contract):
        a = _adapter().argv(_spec(tmp_path, task_contract=dict(contract)), 'sess')
        return _flag(a, '--max-turns')

    for estimate, want in ((1, '20'), (2, '40'), (3, '60'), (4, '80'), (5, '100')):
        assert turns({'estimate': estimate}) == str(want)
    assert turns({}) == '60'                          # no estimate named at all
    assert turns({'estimate': 3}) == '60'
    for unknown in (0, 6, 99, -1, '40'):
        assert turns({'estimate': unknown}) == '60', unknown
    assert turns({'estimate': '4'}) == '80'           # the CLI's own digits still count


def test_g15_a_resume_continues_that_session_and_never_opens_a_new_one(tmp_path):
    """adapter.py:168 (`['--resume', session] if spec.resume_ref else
    ['--session-id', session]`). The inversion starts a brand-new conversation
    with the prompt "Continue the task from where you stopped." — a silent,
    plausible-looking run with none of the task's context in it."""
    a = _adapter().argv(_spec(tmp_path, resume_ref='sess-1'), 'sess-1')
    assert _flag(a, '--resume') == 'sess-1' and '--session-id' not in a
    b = _adapter().argv(_spec(tmp_path), 'sess-2')
    assert _flag(b, '--session-id') == 'sess-2' and '--resume' not in b
    # an empty resume ref is no session to resume: the fresh id of `--session-id`,
    # never `--resume ""`, which is what an inverted truthiness test would pass
    c = _adapter().argv(_spec(tmp_path, resume_ref=''), 'sess-3')
    assert _flag(c, '--session-id') == 'sess-3' and '--resume' not in c


def test_g16_the_model_and_effort_are_passed_only_when_one_was_chosen(tmp_path):
    """adapter.py:169-172 (`if spec.model:` / `if spec.effort:`). An empty
    `--model ""` or `--effort ""` is not "the account's default", it is the CLI's
    choice of a model the account may not have, so the flags disappear with the
    value rather than arriving empty."""
    a = _adapter().argv(_spec(tmp_path, model='sonnet', effort='high'), 'sess')
    assert _flag(a, '--model') == 'sonnet' and _flag(a, '--effort') == 'high'
    for kw in ({}, {'model': '', 'effort': ''}, {'model': None, 'effort': None}):
        b = _adapter().argv(_spec(tmp_path, **kw), 'sess')
        assert '--model' not in b and '--effort' not in b, kw


def test_g17_an_isolated_execution_never_gets_the_account_home_as_its_config_dir(
        tmp_path, launch, monkeypatch):
    """adapter.py:188-191 (`if spec.isolation is not None: env['CLAUDE_CONFIG_DIR']
    = ExecPaths(...).config` / `elif home:`). `CLAUDE_CONFIG_DIR` is Claude Code's
    account selector: an isolated process that read the account's home would run
    its own execution's code with the account's login, and an assignment that
    read `setdefault` would let a caller's own env win. On the detached path the
    home is the account's, expanded, and still wins over anything in `spec.env`."""
    other = str(tmp_path / 'someone-elses-account')
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', other)          # what Core itself inherited
    iso = _spec(tmp_path, isolation=launch,
                env=dict(base.CAPABILITY_ENV, ARCHEUS_HOOK_TOKEN='hook_t1'))
    _adapter().start(iso)
    row = launch.last
    assert row['kind'] == 'isolated'
    assert row['env']['CLAUDE_CONFIG_DIR'] == base.ExecPaths(iso.execution_id).config
    assert row['env']['CLAUDE_CONFIG_DIR'] != iso.account.home_ref != other
    # the detached process runs on the account it was dispatched on, and the
    # adapter's own choice beats anything the caller put in `spec.env`
    detached = _spec(tmp_path, env={'CLAUDE_CONFIG_DIR': str(tmp_path / 'nope')})
    _adapter().start(detached)
    assert launch.last['kind'] == 'detached'
    assert launch.last['env']['CLAUDE_CONFIG_DIR'] == os.path.expanduser(
        detached.account.home_ref)
    # no account: the adapter names no home, so what the process inherited stands
    # (the module says so at its head: relocating that is R3-B's, not this one's)
    _adapter().start(_spec(tmp_path, account=None))
    assert launch.last['env'].get('CLAUDE_CONFIG_DIR') == other


def test_g18_a_key_the_spec_carries_never_reaches_the_child(tmp_path, launch):
    """adapter.py:192-193 (`for k in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN'):
    env.setdefault(k, None)`). The module's own header (adapter.py:16-20, the
    product's `config.account_env`, which `pop`s them) says a key in the
    environment shadows the account login, and `setdefault` only clears the one
    the process inherited: a key that arrives in `spec.env` survives and the
    execution authenticates as the key's owner while the ledger, the hook and the
    rate accounting all name the account in `home_ref`."""
    spec = _spec(tmp_path, env={'ANTHROPIC_API_KEY': 'sk-from-the-spec',
                                'ANTHROPIC_AUTH_TOKEN': 'tok-from-the-spec',
                                'CLAUDE_CODE_OAUTH_TOKEN': 'oauth-from-the-spec'})
    _adapter().start(spec)
    for key in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN'):
        assert key not in launch.last['env'], key


def test_g19_the_headless_marker_travels_with_the_prompt_and_the_resumed_session_with_the_process(
        tmp_path, launch):
    """adapter.py:196-202 (`session = spec.resume_ref or str(uuid.uuid4())`, the
    prompt + HEADLESS_MARK, `self._stopped.discard`). The marker is what makes the
    legacy account hooks stand down inside the child, so a prompt without it runs
    the user's own hooks against a managed execution; and a new session id on a
    resume is g15's bug seen from the other side. `_stopped.discard` is the
    harder half: without it an execution that was stopped once is reported
    `killed` for the rest of its life, and a stop is never retried."""
    from claude_sessions.sessions import HEADLESS_MARK
    adapter = _adapter()
    spec = _spec(tmp_path, prompt='do the thing')
    handle = adapter.start(spec)
    paths = base.ExecPaths(spec.execution_id)
    with open(paths.prompt, encoding='utf-8') as f:
        assert f.read() == 'do the thing\n\n' + HEADLESS_MARK
    session = _flag(launch.last['argv'], '--session-id')
    assert session and session != spec.execution_id
    assert _flag(launch.last['argv'], '--resume') is None
    # a stop, then the next process of the same execution: not `killed` again
    adapter.stop(handle)
    assert adapter.collect_result(handle).exit_reason == 'killed'
    base.mark_ended(paths, 1)
    again = dataclasses.replace(spec, process_seq=2)
    resumed = adapter.resume(again, {'session': session})
    assert _flag(launch.last['argv'], '--resume') == session
    assert _flag(launch.last['argv'], '--session-id') is None
    with open(base.ExecPaths(spec.execution_id).prompt, encoding='utf-8') as f:
        body = f.read()
    assert body.startswith('Continue the task') and body.endswith(HEADLESS_MARK)
    assert adapter.collect_result(resumed).exit_reason != 'killed'


@pytest.mark.parametrize('state', [None, {}, [], {'session': ''}, {'other': 's'},
                                   {'session': None}],
                         ids=('none', 'empty', 'empty-list', 'empty-session', 'no-key',
                              'null-session'))
def test_g20_a_resume_with_no_session_refuses_rather_than_starting_something_new(
        tmp_path, launch, state):
    """adapter.py:205-209 (`if not session: raise base.SpawnFailed('no Claude
    session to resume')`). The alternative is g15: an execution that reports
    success having continued nothing. And nothing is started on the way out — a
    spawn marker here would read to reconciliation as "a process may exist"."""
    adapter = _adapter()
    spec = _spec(tmp_path)
    with pytest.raises(base.SpawnFailed) as got:
        adapter.resume(spec, state)
    assert 'no Claude session to resume' in str(got.value)
    assert launch.rows == []
    paths = base.ExecPaths(spec.execution_id)
    assert not os.path.exists(paths.spawning) and not os.path.exists(paths.pid)


def test_g21_an_execution_never_talks_to_its_stdin_again_and_never_claims_a_pause(tmp_path,
                                                                                 launch):
    """adapter.py:212-216: `send` is the refusal (`NotImplementedError`) because
    the prompt is written before the process exists — silently accepting a
    message would drop it; and `pause` reports `halted=False` because the pause
    is a flag the hook reads at the next tool call, not something this adapter
    can do to a running headless process — claiming a halt that had not happened
    would end the execution's own gate."""
    adapter = _adapter()
    handle = adapter.start(_spec(tmp_path))
    with pytest.raises(NotImplementedError):
        adapter.send(handle, 'one more thing')
    assert adapter.pause(handle) == base.PauseResult(halted=False)
    assert adapter.pause(_handle(str(tmp_path))) == base.PauseResult(halted=False)
    assert adapter.id == 'claude_code'


# ── liveness: who is running, and who may be killed ──────────────────

def test_g22_its_own_child_is_asked_first_and_last(tmp_path, launch):
    """adapter.py:219-222 (`if child is not None and child.pid == handle.pid`).
    The inversion of the `code is None` test reports a live process as exited
    (Core collects its result too early and verifies an unfinished directory) or
    a finished one as running (it never collects at all). The pid comparison is
    the other half: a handle whose pid is not the stored child's may not be
    answered from that child."""
    adapter = _adapter()
    handle = adapter.start(_spec(tmp_path))
    assert adapter.status(handle) == base.ProcStatus('running', None)
    launch.children[0].code = 0
    assert adapter.status(handle) == base.ProcStatus('exited', 0)
    launch.children[0].code = 3
    assert adapter.status(handle) == base.ProcStatus('exited', 3)
    # the same execution id with another pid is not this child: no answer from it,
    # even while that child is still running (which is when the difference shows)
    launch.children[0].code = None
    forged = base.ProcessHandle(handle.execution_id, PID + 1, CREATED, handle.exec_dir)
    assert adapter.status(forged) == base.ProcStatus('exited', None)
    assert adapter.status(handle) == base.ProcStatus('running', None)


def test_g23_a_process_this_core_did_not_start_is_alive_only_by_its_pid_and_create_time(
        tmp_path, launch):
    """adapter.py:223-225 (`handle.create_time is not None and
    proc.process_create_time(handle.pid) == handle.create_time`). After a Core
    restart there is no Popen: the pair is the only proof. Either test weakened
    reports a dead execution as running (it is never collected, its task never
    finishes) or, worse, reports a recycled pid as the execution that recorded
    it, which then gets its result read and its files verified."""
    adapter = _adapter()
    other = 2 ** 22 + 33
    launch.alive[other] = CREATED
    live = base.ProcessHandle(ids.new_id('execution'), other, CREATED, str(tmp_path))
    assert adapter.status(live) == base.ProcStatus('running', None)
    recycled = base.ProcessHandle(live.execution_id, other, 'a different create time',
                                  str(tmp_path))
    assert adapter.status(recycled).state == 'exited'
    # a handle that never recorded a create time can never be proven alive
    launch.alive[PID] = CREATED
    nameless = base.ProcessHandle(ids.new_id('execution'), PID, None, str(tmp_path))
    assert adapter.status(nameless).state == 'exited'


@pytest.mark.parametrize('ended, last, want', [
    ({'exit_code': 7}, None, 7),                      # the tombstone answers
    (None, False, 0),                                  # the result implies one
    (None, True, 1),
    ({'exit_code': None}, True, 1),                    # a tombstone with no code
    (None, None, None),                                # nothing ever said
    ({'exit_code': 0}, True, 0),                        # the tombstone wins
], ids=('tombstone', 'result-ok', 'result-error', 'no-code', 'silent', 'tombstone-wins'))
def test_g24_a_lost_process_ends_with_the_code_it_left_or_the_one_it_implies(
        tmp_path, launch, ended, last, want):
    """adapter.py:226-232 (`ended = base.read_json(...); code = ended.get(
    'exit_code'); if code is None: ... 1 if res[-1].get('is_error') else 0`).
    The exit code decides `ok` versus `error` downstream; a Core that restarted
    after the child died has only these two files, and reading neither as 0 would
    report a crashed run as a clean one."""
    lines = [_result(is_error=last)] if last is not None else [
        {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'hi'}]}}]
    d = _exec_dir(tmp_path, *lines, ended=ended)
    assert _adapter().status(_handle(d)) == base.ProcStatus('exited', want)


def test_g25_only_the_process_this_execution_started_may_be_killed(tmp_path, launch):
    """adapter.py:238-244 (`if not proc.kill_pid_tree(handle.pid,
    handle.create_time): if proc.process_create_time(handle.pid) is not None:
    raise base.StopRefused`). Three answers, and the middle one is the whole
    point: a pid that now belongs to another live process is never killed and the
    caller is told — an inversion here kills a stranger (possibly the user's own
    `claude`) and reports the execution stopped. The third is what a stop of
    something already gone does NOT do: neither refuse nor mark `_stopped`, so a
    later result is `error` and never `killed`."""
    adapter = _adapter()
    handle = adapter.start(_spec(tmp_path))
    adapter.stop(handle)
    assert launch.kills == [(PID, CREATED)]
    assert adapter.collect_result(handle).exit_reason == 'killed'
    adapter.stop(handle)                                   # stopping what is gone
    assert launch.kills == [(PID, CREATED)]                 # never a second kill
    assert len(launch.attempts) == 2

    stolen_pid = 2 ** 22 + 33                    # a live process of someone else's
    launch.alive[stolen_pid] = CREATED
    stolen = base.ProcessHandle(ids.new_id('execution'), stolen_pid, 'not-its-time',
                                str(tmp_path))
    with pytest.raises(base.StopRefused):
        adapter.stop(stolen)
    assert launch.alive.get(stolen_pid) == CREATED           # the survivor is alive
    assert launch.kills == [(PID, CREATED)]                  # and it was never killed
    assert adapter.collect_result(stolen).exit_reason != 'killed'
    # a process that is simply gone is not a refusal, and not a stop either
    gone = base.ProcessHandle(ids.new_id('execution'), 2 ** 22 + 99, CREATED, str(tmp_path))
    assert adapter.stop(gone) is None
    assert adapter.collect_result(gone).exit_reason == 'error'


# ── collect_result: who owns the end, and what continues it ──────────────────

def test_g26_a_limit_anywhere_in_the_stream_owns_the_end_whatever_else_it_said(tmp_path,
                                                                               launch):
    """adapter.py:254-256 (`if any(e.get('type') == 'limit' for e in events):
    failure = 'limit' elif last.get('is_error'): ...`). The limit check is over
    every event, not the last one, and it comes first: an execution that hit the
    ceiling and then reported an ordinary task error must still be charged to the
    account's ceiling, or Core rotates to another account and spends its headroom
    on the same refusal."""
    d = _exec_dir(tmp_path, _result(is_error=True, subtype='error_during_execution',
                                    result='You have hit your weekly limit.'))
    got = _adapter().collect_result(_handle(d))
    assert (got.failure, got.exit_reason) == ('limit', 'error')
    # the refusal arrived on an earlier turn and the last line was clean: still a limit
    d2 = _exec_dir(tmp_path,
                   _result(is_error=True, result='quota exceeded', session_id='s1'),
                   _result(result='done', session_id='s1'))
    got = _adapter().collect_result(_handle(d2))
    assert got.failure == 'limit' and got.exit_reason == 'ok'


@pytest.mark.parametrize('subtype, want', [
    ('error_during_execution', 'resource'),
    ('error_max_turns', 'task'),
    ('error_during_execution extra', 'task'),
    (None, 'task'),
    (425, 'task'),
], ids=('resource', 'max-turns', 'unknown', 'none', 'not-a-name'))
def test_g27_the_subtype_names_the_owner_of_an_error_end_and_only_an_error_end(
        tmp_path, launch, subtype, want):
    """adapter.py:44 (`_ERR`) with 256-257 (`failure = _ERR.get(last.get(
    'subtype'), 'task')`). Who is charged for an ended execution — its resources
    or its task — decides whether the task is retried at all; an unmapped subtype
    falls to `task`, and the whole branch stands or falls on `is_error`, so a
    result that only mentions an error subtype while saying it succeeded charges
    nothing to anybody."""
    d = _exec_dir(tmp_path, _result(is_error=True, subtype=subtype, result='it failed'))
    got = _adapter().collect_result(_handle(d))
    # no `ended` tombstone: the code is the one its own result implies (g24)
    assert (got.failure, got.exit_reason, got.exit_code) == (want, 'error', 1)
    d2 = _exec_dir(tmp_path, _result(is_error=False, subtype=subtype))
    assert _adapter().collect_result(_handle(d2)).failure is None


def test_g28_a_halt_is_reported_and_only_a_stop_this_adapter_issued_reads_as_killed(
        tmp_path, launch):
    """adapter.py:258-260 (`halted = os.path.exists(base.halted_path(...))`,
    `reason = 'killed' if handle.execution_id in self._stopped else ('ok' if
    st.exit_code == 0 and not last.get('is_error') else 'error')`). `ok` needs
    both halves — a code of 0 and no error in the result — because the child that
    failed its own task can still exit cleanly; and `halted` is the hook's claim,
    read from the file the hook wrote, never from the child's words."""
    clean = _exec_dir(tmp_path, _result(result='done'), ended={'exit_code': 0})
    got = _adapter().collect_result(_handle(clean))
    assert (got.exit_reason, got.exit_code, got.halted) == ('ok', 0, False)
    assert got.reported_summary == 'done' and got.usage_total is True
    # a clean exit that reported its own failure is not ok
    lied = _exec_dir(tmp_path, _result(result='nope', is_error=True), ended={'exit_code': 0})
    assert _adapter().collect_result(_handle(lied)).exit_reason == 'error'
    # the hook's halt report is what makes `halted` true, whatever the child said
    halted = _exec_dir(tmp_path, _result(result='done'), ended={'exit_code': 0}, halted=True)
    assert _adapter().collect_result(_handle(halted)).halted is True
    # an execution that produced no result at all is not a total of anything
    quiet = _exec_dir(tmp_path, ended={'exit_code': 0})
    got = _adapter().collect_result(_handle(quiet))
    assert (got.usage_total, got.reported_summary, got.exit_reason) == (False, '', 'ok')


def test_g29_the_session_a_finished_execution_reports_is_the_one_it_can_continue_with(
        tmp_path, launch):
    """`collect_result`: `session = last.get('session_id') or newest` and
    `adapter_state={'session': session} if session else None`. This is session
    discovery: it is the only handle a later `resume` has (g20 refuses without
    it), so the result's own id wins, a run whose result line lost it falls back
    to the NEWEST line that named one (a run that continues a session names a newer
    one than it started with), a child that invented a falsy id falls back
    too, and an execution that named no session hands Core nothing to resume with
    rather than a `{'session': None}` that reads as a session.
    """
    d = _exec_dir(tmp_path, {'type': 'system', 'subtype': 'init', 'session_id': 's-first'},
                  _result(session_id='s-last'))
    assert _adapter().collect_result(_handle(d)).session_ref == 's-last'
    d2 = _exec_dir(tmp_path, {'type': 'system', 'subtype': 'init', 'session_id': 's-first'},
                   {'type': 'system', 'subtype': 't', 'session_id': 's-second'},
                   _result())
    got = _adapter().collect_result(_handle(d2))
    assert got.session_ref == 's-second' and got.adapter_state == {'session': 's-second'}
    d3 = _exec_dir(tmp_path, {'type': 'system', 'session_id': ''}, _result(session_id=0))
    assert _adapter().collect_result(_handle(d3)).session_ref is None
    # no session anywhere: no state, and the refusal of g20 is what follows
    quiet = _exec_dir(tmp_path, _result())
    assert _adapter().collect_result(_handle(quiet)).adapter_state is None
    with pytest.raises(base.SpawnFailed):
        _adapter().resume(_spec(tmp_path), _adapter().collect_result(
            _handle(quiet)).adapter_state)


def test_g30_the_transcript_path_and_the_counted_usage_come_from_the_last_result(tmp_path, launch):
    """adapter.py:262-264 (`reported_summary=last.get('summary', '')`,
    `usage=last.get('usage') or {}`, `usage_total=bool(results)`,
    `transcript_path=os.path.join(handle.exec_dir, 'stream.jsonl')`). The last
    result is the one that counts (an execution retries internally), the path is
    what the verifier and the trace reader open, and `usage_total` claims a
    harness total: said for a run with no result at all, Core would read an
    empty usage as a complete one."""
    d = _exec_dir(tmp_path, _result(result='first', usage={'input_tokens': 1},
                                    total_cost_usd=0.1),
                  _result(result='second', usage={'input_tokens': 5}))
    got = _adapter().collect_result(_handle(d))
    assert got.reported_summary == 'second' and got.usage == {'input_tokens': 5}
    assert got.usage_total is True
    assert got.transcript_path == os.path.join(d, STREAM)
    assert got.usage_total is True and got.failure is None


# ── discovery: what the harness may be asked to do at all ────────────

def test_g31_it_calls_itself_installed_only_when_the_binary_is_there(tmp_path, monkeypatch):
    """`discover` (`self._exe or proc.which('claude')`,
    `HarnessInfo(self.id, bool(exe), None, exe)`). `installed` decides whether
    Core routes work here at all: reporting it installed without the binary turns
    every execution into a spawn failure, and reporting the exe it did not find
    hands the manager a path to run that does not exist."""
    seen = []
    found = str(tmp_path / 'claude.exe')
    monkeypatch.setattr(cc.proc, 'which',
                        lambda name: (seen.append(name), found)[1])
    info = cc.ClaudeCodeAdapter().discover()
    assert seen == ['claude'] and info.installed is True
    assert info.executable == found and info.version is None
    assert info.id == 'claude_code'
    monkeypatch.setattr(cc.proc, 'which', lambda name: (seen.append(name), None)[1])
    assert cc.ClaudeCodeAdapter().discover().installed is False
    assert cc.ClaudeCodeAdapter().discover().executable is None
    # an exe named by the caller is taken as found, without asking the OS again
    del seen[:]
    assert cc.ClaudeCodeAdapter(exe=found).discover().installed is True
    assert seen == []


def test_g32_it_never_claims_a_login_it_cannot_find(tmp_path, monkeypatch):
    """adapter.py:134-137 (`ok = bool(usage._creds(account.home_ref))`). An
    account with no stored login that authenticates is work dispatched to a
    provider that will refuse it, charged to the account that was named; the
    refusal also names the home it looked in, which is the only clue an operator
    gets when the home is the wrong one."""
    home = _home(tmp_path)
    asked = []
    monkeypatch.setattr(usage, '_creds', lambda cfgdir=None: (asked.append(cfgdir), {})[1])
    st = _adapter().authenticate(base.AccountRef('claude_code:test', home))
    assert st.ok is False and 'no Claude login' in st.detail and home in st.detail
    assert asked == [home]                       # the home it was named, not the ambient one
    for creds in ({'claudeAiOauth': {'accessToken': 't'}}, {'anything': 1}):
        del asked[:]
        monkeypatch.setattr(usage, '_creds', lambda cfgdir=None, c=creds: (asked.append(
            cfgdir), c)[1])
        st = _adapter().authenticate(base.AccountRef('claude_code:test', home))
        assert st.ok is True and st.detail == '' and asked == [home]


def test_g33_the_enforcement_it_promises_is_the_hook_and_its_account_key_is_canonical(
        tmp_path, monkeypatch):
    """adapter.py:121-132: `capabilities` names `'hook'` as the enforcement — the
    one Core may not treat as a sandbox — and `default_account` is the fixed key
    of ADR-0048 D-25.1, canonical in the key and the real path in `home_ref`, so
    the process runs exactly where the account lives and one home is one key.
    The home is named as a `~` path, because that is where the key and the real
    path part company: an account keyed on the unexpanded form is a second key
    for one home, and a process whose `CLAUDE_CONFIG_DIR` is a literal `~` reads
    no login at all."""
    from claude_sessions import config
    monkeypatch.setattr(config, 'resolve_config_dir', lambda cfgdir=None: '~/Dot-Claude')
    caps = _adapter().capabilities()
    assert caps.enforcement == 'hook' and caps.structured_output == 'native'
    assert {'resume', 'headless', 'code_edit'} <= caps.capabilities
    assert caps.usage_measures == frozenset({'tokens'})
    home = os.path.expanduser('~/Dot-Claude')
    ref = _adapter().default_account()
    assert ref.account_id == 'claude_code:%s' % base.canonical_home(home)
    assert ref.home_ref == os.path.abspath(home)
    assert '~' not in ref.account_id + ref.home_ref
