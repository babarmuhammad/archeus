"""T-1031: the uncovered fail-closed branches of `archeus/harnesses/hook.py`,
lines 1-278 inclusive (the whole file; definitions and imports there are the
read-only context, and branch ownership stays inside this slice).

Existing coverage read first and not repeated: `test_execution_units.py` §10
and its PV-20/T-651 blocks (allow/deny answers, sentinel presence, request
cap, deadline halt, nonce-mismatch and stale-answer halt, concurrent
`_reserve`), `test_settings_sources_units.py` E16-E19 (the subprocess exit
codes, `guarded` with a working stderr, hostile WAIT_S) and
`test_command_allowlist_hook.py` (the canonicaliser's hook entry, not this
file). The probes the card starts with that those tests already pin are
replaced here, with evidence in the report: digest mismatch (the rewrite test
of review R4), nonce mismatch and missing nonce (the stale-answer test),
request cap (the two bound tests), deadline expiry (E19 and friends), the
`_reserve` half of the mailbox-write error (unwritable class 1 through
`main`). An answer-side size cap is not applicable: lines 1-278 of the hook
have no bound on the response read (`MAX_REQUEST_BYTES` guards only the
request body at line 194; the read at 209-210 has none).

The ten branches this file adds, fail-closed and denial first, then
boundaries, then error paths:

1. hook.py:220-221, 225-226 - a decision outside allow/deny/halt that carries
   the request's own nonce and digest is a halt, never an allow.
2. hook.py:216-218 - an answer with the right nonce but no judged digest is
   the rewritten request: halt (the card's focus: no judged binding, no
   answer).
3. hook.py:213, 216, 219 - a JSON answer that is not an object is never the
   answer; the isinstance guards keep `run` returning a halt instead of
   raising.
4. hook.py:102-110 - `_halted` swallows OSError: an unwritable mailbox still
   yields a halt from `run` itself (the half of the mailbox-write error the
   unwritable-class-1 test leaves untested).
5. hook.py:222-224 - Core's `halt` answer is recorded in halted.json (§9.1)
   and returned as a halt, before the loop can read anything else.
6. hook.py:159-162 - the identity guard on a missing/empty home or token and
   a wrong-shape execution id halts before anything is written under home.
7. hook.py:208-212 - a half-written (malformed) JSON answer keeps the hook
   polling: the ValueError side of the read, then the real answer is accepted.
8. hook.py:70-71, 92 - a `continue` answer (PreCompact) carries no permission
   decision at all: stdout is `{}`, exit 0.
9. hook.py:72-81 with 223-224 - a `halt` answer with no reason still denies
   the call with the default reason on stdout, never an empty one.
10. hook.py:263-267 - `guarded` returns the deny's exit code even when the
    failure notice cannot be written: a failed stderr write must not become
    the undocumented exit code Claude Code lets the call through on.

Everything is in-process on tmp_path with the seams the module's own tests
use: monkeypatched `hook.open` (as the unreadable-class-2 test), a patched
`os.urandom` so the nonce is knowable before the run, and sentinel files
written plainly. No subprocess, no network, no sleeps over one second, no
Windows-specific behaviour, no assertion on OS error text.
"""

import io
import json
import os
import sys
from types import SimpleNamespace

import pytest

from archeus.core.domain import ids
from archeus.harnesses import hook

TOKEN = 'hook_t'
RANDOM = b'\xa5' * 16                  # the seam under os.urandom(16)
NONCE = RANDOM.hex()
NO_IDENTITY = 'this process has no Archeus execution identity'
PAYLOAD = {'tool_name': 'Read', 'tool_input': {'file_path': 'a.txt'}}


def _body(seq=None):
    """The request body `run` builds for PAYLOAD, optionally with the sequence
    number `_reserve` appends: what the hook digests and what an answer must
    have been judged against."""
    body = {'token': TOKEN, 'tool': PAYLOAD['tool_name'], 'input': PAYLOAD['tool_input'],
            'cwd': PAYLOAD.get('cwd'), 'nonce': NONCE}
    return body if seq is None else dict(body, seq=seq)


def _digest():
    return hook.request_digest(_body(1))


def _write(path, obj):
    with open(str(path), 'w', encoding='utf-8') as f:
        json.dump(obj, f)


def _read(path):
    with open(str(path), encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    """The hook over an empty fresh mailbox: the class directories exist, so
    the first request takes sequence 1, and `os.urandom` is the seam that lets
    every answer below be written before the hook ever starts waiting."""
    eid = ids.new_id('execution')
    home = str(tmp_path)
    d = os.path.join(home, 'run', 'exec', eid)
    box, answers, ctl = (os.path.join(d, n) for n in ('req', 'res', 'ctl'))
    os.makedirs(box)
    os.makedirs(answers)
    os.makedirs(ctl)
    monkeypatch.setattr(hook.os, 'urandom', lambda n: RANDOM)
    monkeypatch.setattr(hook, 'WAIT_S', 5.0)         # fail fast, never the import-time 60
    env = {'ARCHEUS_HOME': home, 'ARCHEUS_EXECUTION_ID': eid, 'ARCHEUS_HOOK_TOKEN': TOKEN}
    return SimpleNamespace(env=env, home=home, d=d, box=box, answers=answers, ctl=ctl)


def _answer(rig, obj):
    """One class-2 answer for sequence 1, written before the hook runs."""
    path = os.path.join(rig.answers, '1.res.json')
    with open(str(path), 'w', encoding='utf-8') as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj))
    return path


def _halted(box):
    return _read(os.path.join(box, 'halted.json'))


# ── 1: a decision outside the three is a halt even with the judged binding ───

@pytest.mark.parametrize('decision', ['ask', 'Allow', None], ids=['ask', 'caps', 'null'])
def test_a_decision_outside_allow_deny_halt_halts_fail_closed(rig, decision):
    """hook.py:220-221, 225-226: the binding checks pass, so a Core bug or a
    truncated write of some other vocabulary must still end at the fail-closed
    halt; nothing in this repo's tests answers a request with a fourth word."""
    _answer(rig, {'decision': decision, 'nonce': NONCE, 'digest': _digest(),
                  'reason': 'looks fine'})
    assert hook.run(dict(PAYLOAD), rig.env) == (
        'halt', 'Archeus did not answer; denied and halted (fail closed)')
    rec = _halted(rig.box)
    assert (rec['seq'], rec['reason']) == (1, 'Archeus did not answer')
    assert isinstance(rec['at'], float)
    assert sorted(os.listdir(rig.box)) == ['1.lock', '1.req.json', 'halted.json']
    assert _read(os.path.join(rig.box, '1.req.json')) == _body(1)


# ── 2: the answer must carry the judged digest, not merely the fresh nonce ───

def test_an_answer_with_the_nonce_but_no_judged_digest_halts(rig):
    """hook.py:216-218: the nonce proves freshness, not content. The stale-
    answer test never reaches the digest line (its nonces are wrong) and the
    rewrite test always carries a digest (LocalNode.respond writes one): an
    answer that simply omits the judged binding is this branch."""
    _answer(rig, {'decision': 'allow', 'nonce': NONCE, 'reason': 'trust me'})
    kind, why = hook.run(dict(PAYLOAD), rig.env)
    assert (kind, why) == ('halt', 'the request was rewritten before Archeus answered it')
    rec = _halted(rig.box)
    assert (rec['seq'], rec['reason']) == (1, 'the request changed before Archeus answered it')
    assert sorted(os.listdir(rig.box)) == ['1.lock', '1.req.json', 'halted.json']


# ── 3: a JSON answer that is not an object is never the answer ───────────────

@pytest.mark.parametrize('raw', ['["allow"]', '"allow"', '42'], ids=['list', 'string', 'number'])
def test_an_answer_that_is_not_an_object_is_never_the_answer(rig, raw):
    """hook.py:213, 216, 219: without the isinstance guards a list answer
    raises AttributeError out of `run` (the read's try only wraps the open and
    the parse), so an in-process caller loses the halt it was promised."""
    res = _answer(rig, raw)
    assert hook.run(dict(PAYLOAD), rig.env) == (
        'halt', 'Archeus did not answer; denied and halted (fail closed)')
    assert _halted(rig.box)['reason'] == 'Archeus did not answer'
    assert _read(res) == json.loads(raw)                      # read, refused, untouched


# ── 4: a halt is still returned when the halt cannot be written ──────────────

@pytest.mark.parametrize('broken', ['makedirs', 'open'], ids=['mailbox-file', 'tmp-open'])
def test_a_halt_is_still_returned_when_the_halt_cannot_be_written(tmp_path, monkeypatch,
                                                                  broken):
    """hook.py:102-110: the unwritable-class-1 test crashes in `_reserve`
    through `main`; neither test runs `_halted`'s swallow. An execution denied
    its mailbox must not turn the report of a halt into a crash of `run`."""
    eid = ids.new_id('execution')
    home = str(tmp_path)
    d = os.path.join(home, 'run', 'exec', eid)
    ctl = os.path.join(d, 'ctl')
    box = os.path.join(d, 'req')
    os.makedirs(ctl)
    open(os.path.join(ctl, 'STOP'), 'w').close()
    env = {'ARCHEUS_HOME': home, 'ARCHEUS_EXECUTION_ID': eid, 'ARCHEUS_HOOK_TOKEN': TOKEN}
    if broken == 'makedirs':                                   # the mailbox itself is a file
        with open(box, 'w', encoding='utf-8') as f:
            f.write('not a directory')
    else:                                                      # the tmp write is refused
        os.makedirs(box)
        real = open

        def denied(path, *a, **kw):
            if os.path.basename(os.fspath(path)).startswith('halted.json.'):
                raise PermissionError(13, 'the mailbox is read-only', os.fspath(path))
            return real(path, *a, **kw)
        monkeypatch.setattr(hook, 'open', denied, raising=False)
    assert hook.run(dict(PAYLOAD), env) == ('halt', 'stopped by Archeus')
    if broken == 'open':
        assert os.listdir(box) == []               # the refused tmp left nothing behind
    else:
        assert os.path.isfile(box)                 # still the file, never made into a dir


# ── 5: Core's halt is recorded, which is how §9.1 reads it ───────────────────

def test_cores_halt_answer_is_recorded_and_returned(rig):
    """hook.py:222-224: E17 halts at the estop before asking, and the waiting
    tests halt at 205; no existing test has Core answer `halt`, so the record
    that tells a halted process from a finished one is unpinned there."""
    _answer(rig, {'decision': 'halt', 'nonce': NONCE, 'digest': _digest(),
                  'reason': 'policy says stop'})
    assert hook.run(dict(PAYLOAD), rig.env) == ('halt', 'policy says stop')
    assert _halted(rig.box)['seq'] == 1
    assert _halted(rig.box)['reason'] == 'policy says stop'
    assert sorted(os.listdir(rig.box)) == ['1.lock', '1.req.json', 'halted.json']


# ── 6: no identity, no mailbox: the guard runs before any write ──────────────

@pytest.mark.parametrize('drop', [
    {'ARCHEUS_HOME': None}, {'ARCHEUS_HOME': ''},
    {'ARCHEUS_HOOK_TOKEN': None}, {'ARCHEUS_HOOK_TOKEN': ''},
    {'ARCHEUS_EXECUTION_ID': ''}, {'ARCHEUS_EXECUTION_ID': 'exe_' + '8' + '0' * 25},
    {'ARCHEUS_EXECUTION_ID': 'not-an-id'}],
    ids=['no-home', 'home-empty', 'no-token', 'token-empty', 'eid-empty', 'eid-shape-8',
         'eid-text'])
def test_the_hook_halts_before_touching_the_mailbox_without_an_identity(tmp_path, monkeypatch,
                                                                         drop):
    """hook.py:159-162: E48 covers the flag and one wrong id in a subprocess
    and never without a home or a token; the ulid test only matches the regex.
    Each case carries everything else a request needs, and nothing may be
    written under home by a process that is not an execution's."""
    monkeypatch.setattr(hook, 'WAIT_S', 0.2)   # a broken guard must fail fast, not wait 60 s
    env = {'ARCHEUS_HOME': str(tmp_path), 'ARCHEUS_EXECUTION_ID': ids.new_id('execution'),
           'ARCHEUS_HOOK_TOKEN': TOKEN}
    for key, value in drop.items():
        if value is None:
            del env[key]
        else:
            env[key] = value
    assert hook.run(dict(PAYLOAD), env) == ('halt', NO_IDENTITY)
    assert not os.path.exists(os.path.join(str(tmp_path), 'run'))   # no mailbox, no dirs


# ── 7: a half-written answer keeps the hook polling, not crashes ─────────────

def test_a_half_written_answer_keeps_the_hook_polling_until_the_real_one(rig, monkeypatch):
    """hook.py:208-212: the unreadable-class-2 test covers the OSError side of
    the read and never recovers; no test hands the hook a truncated JSON
    answer (a torn write by Core is normal while the answer lands) and then
    the real one. It must poll, accept the good answer, and halt nothing."""
    res = os.path.join(rig.answers, '1.res.json')
    _write(res, {'decision': 'allow', 'nonce': NONCE, 'digest': _digest(), 'reason': 'fine'})
    seen, real_open = [], open

    def torn_first(path, *a, **kw):
        if os.fspath(path) == res and not seen:
            seen.append('torn')
            return io.StringIO('{"decision": "allow"')         # json.load raises ValueError
        return real_open(path, *a, **kw)
    monkeypatch.setattr(hook, 'open', torn_first, raising=False)
    assert hook.run(dict(PAYLOAD), rig.env) == ('allow', 'fine')
    assert seen == ['torn']                                    # the torn read really happened
    assert 'halted.json' not in os.listdir(rig.box)            # a torn read halts nothing


# ── 8: a PreCompact answer never speaks the permission protocol ──────────────

def test_a_precompact_answer_carries_no_permission_decision():
    """hook.py:70-71 with 92: the vocabulary test pins allow, halt and the
    deny raise, and the precompact tests stop at `run`; nothing pins that the
    stdout of a continue is the empty object. An allow dict here would let a
    PreCompact answer grant a tool call."""
    assert hook.decision('continue') == {}
    out, err, code = hook.answer('continue')
    assert (code, err) == (0, '')
    assert json.loads(out) == {}                               # no permissionDecision at all
    assert 'hookSpecificOutput' not in out


# ── 9: a halt answer with no reason still denies with one ────────────────────

def test_a_halt_answer_with_no_reason_still_denies_with_a_reason(rig):
    """hook.py:223-224 (`or ''`) with 72-81 (`or 'halted by Archeus'`): every
    existing halt names its reason, so the two defaults that keep a stop
    reason non-empty on stdout are unexercised there."""
    _answer(rig, {'decision': 'halt', 'nonce': NONCE, 'digest': _digest()})
    kind, why = hook.run(dict(PAYLOAD), rig.env)
    assert (kind, why) == ('halt', '')
    assert _halted(rig.box)['seq'] == 1 and _halted(rig.box)['reason'] == ''
    out, err, code = hook.answer('halt', why)
    assert (code, err) == (0, '')
    o = json.loads(out)
    assert o['continue'] is False and o['stopReason'] == 'halted by Archeus'
    assert o['hookSpecificOutput']['permissionDecision'] == 'deny'
    assert o['hookSpecificOutput']['permissionDecisionReason'] == 'halted by Archeus'


# ── 10: even an unwritable stderr cannot invent an exit code ─────────────────

def test_guarded_denies_even_when_the_stderr_write_fails(monkeypatch):
    """hook.py:263-267: E18 exercises `guarded` with a working stderr only.
    Without the inner swallow the notice's OSError escapes `guarded` and the
    interpreter's uncaught-error exit (1) is exactly the undocumented code
    Claude Code lets the call through on."""
    class BrokenStderr:
        def write(self, *a):
            raise OSError(5, 'the pipe is closed')

        def flush(self, *a):
            raise OSError(5, 'the pipe is closed')

    monkeypatch.setattr(sys, 'stderr', BrokenStderr())
    assert hook.guarded(lambda: 7) == hook.DENY_EXIT           # an invented code
    assert hook.guarded(lambda: 0) == 0                        # still not swallowing the ok
    assert hook.guarded(lambda: sys.exit(3)) == hook.DENY_EXIT
