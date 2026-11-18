"""T-1029: the highest-risk uncovered branches of archeus/node/local.py lines
1033-1100 inclusive - `LocalNode.pending_requests` and `LocalNode.respond`, the
Mailbox digest and the answered cache. No source file is edited here; every OS
call the slice does is answered through the seams the existing tests already use
(real files under the per-test ARCHEUS_HOME, `os.utime` for the clock, fakes for
`config.write_json_atomic` and `local.time`), so the file passes or fails the
same way on Linux and Windows. No process, no network, no DLL.

The ten branches, ranked fail-closed and denial first, then boundaries, then the
error path (the report carries the closest-existing-test evidence for each):

1. local.py:1092-1093  respond(request=None): the answer to an unreadable
   request echoes nonce null and digest null (True side of both ternaries).
2. local.py:1071       res not None with an unreadable (None) request body:
   `(body or {})` matches Core's null-nonce answer and settles the pair once.
3. local.py:1043-1045  the request box is gone: the answered memo for that
   execution is dropped, not just the empty list returned.
4. local.py:1071       a planted class-2 answer with nonce null does not answer
   a request that carries a nonce: the request stays due (PV-20 §7.5).
5. local.py:1090-1093  respond answers the judged dict, never a second read of
   the request file the execution can rewrite after the judgment.
6. local.py:1063-1066  the memo stamp covers the answer file too: a same-size
   rewrite of res/N.res.json breaks the skip and the request is judged again.
7. local.py:1072       a pair answered inside the settle window is not
   memoised, so a rewrite that keeps the recorded stamp cannot hide it.
8. local.py:1047,1072  the settle boundary is strict: a pair whose stamp sits
   exactly at `time_ns() - 2 * 10**9` is not memoised; one ns older is.
9. local.py:1046,1076  the answered cache is keyed by execution id: one
   execution's memo never skips another's identically named request.
10. local.py:1088-1094 respond's atomic write failing raises, records no
   answer, and happens only after the class 2 directory was made (order).
"""

import json
import os
import shutil
import time
from types import SimpleNamespace

import pytest
from claude_sessions import config

from archeus.core.domain import ids
from archeus.harnesses import hook
from archeus.infra import paths
from archeus.node import local
from archeus.node.local import LocalNode

#: the settle window pending_requests uses (local.py:1047), restated here so the
#: boundary tests pin the constant the source owns
SETTLE_NS = 2 * 10**9


def _memo(monkeypatch):
    """A private answered cache for the test: the module dict otherwise carries
    entries across tests, and every assertion here is about one execution."""
    box = {}
    monkeypatch.setattr(local, '_ANSWERED', box)
    return box


def _box(eid, with_res=True):
    p = paths.ExecPaths(eid)
    os.makedirs(p.req)
    if with_res:
        os.makedirs(p.res, exist_ok=True)
    return p


def _write(box, name, raw):
    """Bytes on disk, exactly the bytes named: no text mode, no newline luck."""
    with open(os.path.join(box, name), 'wb') as f:
        f.write(raw if isinstance(raw, bytes) else json.dumps(raw).encode('utf-8'))


def _read(box, name):
    with open(os.path.join(box, name), encoding='utf-8') as f:
        return json.load(f)


def _stamp_of(path):
    st = os.stat(path)
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def _age(path, at_ns):
    os.utime(path, ns=(at_ns, at_ns))


def _answered_pair(p, seq, nonce):
    """req/N.req.json and res/N.res.json echoing one nonce, as an answered pair
    looks once Core has judged it (the nonce match is what pending_requests reads)."""
    req = b'{"tool": "Read", "nonce": "%s"}' % nonce.encode('utf-8')
    res = b'{"decision": "allow", "reason": "", "nonce": "%s", "digest": null}' % \
        nonce.encode('utf-8')
    _write(p.req, '%d.req.json' % seq, req)
    _write(p.res, '%d.res.json' % seq, res)
    return (os.path.join(p.req, '%d.req.json' % seq),
            os.path.join(p.res, '%d.res.json' % seq))


def _long_ago():
    return int((time.time() - 60) * 10**9)


# ── 1. fail closed: the answer to an unreadable request is all nulls ─────────

def test_core_s_answer_to_an_unreadable_request_carries_no_nonce_and_no_digest(monkeypatch):
    """local.py:1092-1093, the True side of both ternaries: an unreadable request
    comes back as None so Core answers it, and that answer must echo nonce null
    and digest null. Compute the digest anyway (`hook.request_digest(None)`) and
    respond raises TypeError; skip the answer anyway and no file exists."""
    _memo(monkeypatch)
    eid = ids.new_id('execution')
    p = _box(eid, with_res=False)
    _write(p.req, '1.req.json', b'{"tool": "Read"')            # torn by a kill: unreadable
    assert LocalNode.pending_requests(eid) == [(1, None)]      # fail closed: Core must judge
    LocalNode.respond(eid, 1, None, 'deny', 'unreadable request')
    assert sorted(os.listdir(p.res)) == ['1.res.json']
    assert _read(p.res, '1.res.json') == {'decision': 'deny', 'reason': 'unreadable request',
                                          'nonce': None, 'digest': None}


# ── 2. fail closed: that null-nonce answer answers the unreadable pair once ──

def test_the_answer_core_wrote_to_an_unreadable_request_answers_it_once(monkeypatch):
    """local.py:1071 with the request body None: `(body or {}).get('nonce')` is
    None, Core's answer carries nonce null, and the settled pair is answered and
    memoised. Reach 1071 with a missing answer instead (every existing unreadable
    test) and `res is not None` short-circuits before the body is ever consulted;
    demand a non-null answer nonce instead and the unreadable request is reported
    forever, which is the fail-closed promise broken the other way."""
    memo = _memo(monkeypatch)
    eid = ids.new_id('execution')
    p = _box(eid)
    _write(p.req, '1.req.json', b'{"tool": "Read"')             # the request rotted...
    _write(p.res, '1.res.json',                                 # ...and Core answered it all nulls
           b'{"decision": "deny", "reason": "unreadable", "nonce": null, "digest": null}')
    pair = (os.path.join(p.req, '1.req.json'), os.path.join(p.res, '1.res.json'))
    old = _long_ago()
    for path in pair:
        _age(path, old)
    assert LocalNode.pending_requests(eid) == []                # ...and Core answered it
    assert memo[eid] == {'1': (_stamp_of(pair[0]), _stamp_of(pair[1]))}
    monkeypatch.setattr(local, '_read_object',
                        lambda path: pytest.fail('re-read %s' % path))
    assert LocalNode.pending_requests(eid) == []                # the memo answers, no re-read


# ── 3. fail closed: a vanished request box revokes its memo ──────────────────

def test_a_vanished_request_box_drops_the_answered_memo(monkeypatch):
    """local.py:1043-1045: when the box is gone the execution's whole sequence
    space may be rebuilt, so its memo must go with it. The closest existing tests
    hit this except-branch only with an empty memo (an unknown execution id) or
    drop the memo through `ended`; deleting the pop line passes them all."""
    memo = _memo(monkeypatch)
    eid = ids.new_id('execution')
    p = _box(eid)
    old = _long_ago()
    for path in _answered_pair(p, 1, 'n'):
        _age(path, old)
    assert LocalNode.pending_requests(eid) == [] and memo[eid]   # memo live, as the tick keys on it
    shutil.rmtree(p.dir)                                        # the execution's area is gone
    assert LocalNode.pending_requests(eid) == []
    assert eid not in memo                                      # the pop, or the old stamps survive
    # a rebuilt box may reuse the number: the request is due again, not skipped
    os.makedirs(p.req)
    _write(p.req, '1.req.json', {"tool": "Read", "nonce": "reused-1"})
    assert LocalNode.pending_requests(eid) == [(1, {"tool": "Read", "nonce": "reused-1"})]


# ── 4. denial: an answer the execution planted in class two answers nothing ──

def test_a_planted_class_two_answer_without_the_request_s_nonce_leaves_it_due(monkeypatch):
    """local.py:1071 False with a planted answer: class 2 is the execution's own
    directory, so a `{"decision": "allow"}` file Core never wrote must not be
    taken as an answer. The forgery the existing PV-20 §7.5 test plants sits in
    req/ and dies at the name filter (local.py:1052) before the nonce check is
    ever consulted; a reported pair is also never memoised."""
    memo = _memo(monkeypatch)
    eid = ids.new_id('execution')
    p = _box(eid)
    body = {"tool": "Bash", "input": {"command": "rm -rf build"}, "nonce": "n9"}
    _write(p.req, '1.req.json', body)
    forged = {"decision": "allow", "reason": "answered myself", "nonce": None}
    _write(p.res, '1.res.json', forged)
    assert LocalNode.pending_requests(eid) == [(1, body)]       # the denial holds: still due
    assert memo[eid] == {}                                      # a reported pair is never memoised
    assert _read(p.res, '1.res.json') == forged                 # Core reads, it does not police files
    LocalNode.respond(eid, 1, body, 'deny', 'not this way')     # Core's own answer settles it
    assert LocalNode.pending_requests(eid) == []
    assert _read(p.res, '1.res.json')['nonce'] == 'n9'


# ── 5. denial: the answer is for the judged content, not for the file now ────

def test_the_answer_echoes_the_judged_request_not_the_rewritten_file(monkeypatch):
    """local.py:1090-1093: respond answers the very dict pending_requests
    returned. The existing rewrite test (test_execution_units r4) swaps the file
    before the judgment, so re-read-after-judge and answer-from-the-judged-dict
    write the same bytes there; swapping after the judgment is the R4 hole this
    pins: a re-read would answer the attacker's content with the judge's allow."""
    memo = _memo(monkeypatch)
    eid = ids.new_id('execution')
    p = _box(eid, with_res=False)
    judged = {"tool": "Read", "input": {"file_path": "README.md"}, "nonce": "k1"}
    evil = {"tool": "Write", "input": {"file_path": "nested/evil.dll"}, "nonce": "k1"}
    _write(p.req, '1.req.json', judged)
    ((seq, request),) = LocalNode.pending_requests(eid)
    assert request == judged
    _write(p.req, '1.req.json', evil)                           # second process swaps, keeps the nonce
    LocalNode.respond(eid, seq, request, 'allow', 'a read is fine')
    answer = _read(p.res, '1.res.json')
    assert answer['nonce'] == 'k1'
    assert answer['digest'] == hook.request_digest(judged)
    assert answer['digest'] != hook.request_digest(evil)        # the hook still halts: not its content
    assert memo[eid] == {}                                      # respond never touches the memo


# ── 6. stamp integrity: the answer file is part of the memo, not just the req ─

def test_a_swapped_answer_of_the_same_size_reopens_the_request(monkeypatch):
    """local.py:1063-1066: the memo stamp covers both files. The existing
    changed-on-disk test rewrites only the request side; a stamp keyed on the
    request alone, or on size alone without mtime, passes every existing test and
    lets an execution quietly replace a matching answer with a non-matching one -
    here a same-size, same-inode swap that only the recorded time can see."""
    memo = _memo(monkeypatch)
    eid = ids.new_id('execution')
    p = _box(eid)
    pair = _answered_pair(p, 1, 'n')
    old = _long_ago()
    for path in pair:
        _age(path, old)
    assert LocalNode.pending_requests(eid) == []
    assert memo[eid] == {'1': (_stamp_of(pair[0]), _stamp_of(pair[1]))}
    before = os.stat(pair[1])
    with open(pair[1], 'r+b') as f:                             # swap the answer, byte for byte
        f.write(b'{"nonce": "x", "decision": "allow", "reason": "", "digest": null}')
    assert os.stat(pair[1]).st_size == before.st_size
    os.utime(pair[1], ns=(before.st_mtime_ns + 10**9, before.st_mtime_ns + 10**9))
    assert LocalNode.pending_requests(eid) == [(1, {"tool": "Read", "nonce": "n"})]
    assert memo[eid] == {}                                      # the swapped pair is due, not memoised


# ── 7. boundary: nothing answered inside the settle window is memoised ───────

def test_a_pair_answered_within_the_settle_window_is_never_memoised(monkeypatch):
    """local.py:1072: the memo is only for pairs older than the clock's
    resolution. Existing tests rely on the OS moving mtime between their own
    writes, so removing the settled guard entirely passes them all; here the
    rewrite keeps the recorded stamp (same inode, same size, the mtime put back),
    so a wrongly memoised fresh pair would swallow the rewritten request -
    exactly the lost-request fail-open the comment at local.py:1057-1062 sells."""
    memo = _memo(monkeypatch)
    eid = ids.new_id('execution')
    p = _box(eid)
    pair = _answered_pair(p, 1, 'n1')                           # fresh files: inside the window
    assert LocalNode.pending_requests(eid) == []                # answered: not due...
    assert memo[eid] == {}                                      # ...but too fresh to be memoised
    before = os.stat(pair[0])
    with open(pair[0], 'r+b') as f:                             # same size, same inode, new nonce
        f.write(b'{"tool": "Read", "nonce": "n2"}')
    os.utime(pair[0], ns=(before.st_atime_ns, before.st_mtime_ns))
    after = os.stat(pair[0])
    assert (after.st_size, after.st_mtime_ns, after.st_ino) == \
        (before.st_size, before.st_mtime_ns, before.st_ino)     # the stamp did not move
    assert LocalNode.pending_requests(eid) == [(1, {"tool": "Read", "nonce": "n2"})]


# ── 8. boundary: the settle age is strict at the equality point ──────────────

def test_a_pair_exactly_at_the_settle_age_is_not_memoised(monkeypatch):
    """local.py:1047 with local.py:1072 (`x[0] < settled`): a pair whose stamp
    sits exactly at `time_ns() - 2 * 10**9` is not old enough to memoise, one
    microsecond under it is. Existing tests use 60-second-old pairs (settled by a
    mile) or fresh ones (unsettled by one), so `<=`, a wrong constant or a lost
    comparison passes them; all three pairs are answered, so none may be reported."""
    memo = _memo(monkeypatch)
    now = (time.time_ns() // 10**6) * 10**6                     # us-aligned: coarse st_mtime survive
    settled = now - SETTLE_NS
    monkeypatch.setattr(local, 'time', SimpleNamespace(time_ns=lambda: now))
    eid = ids.new_id('execution')
    p = _box(eid)
    ages = {1: settled - 10**6, 2: settled, 3: now}             # under, exactly on, fresh
    stamps = {}
    for seq, at in ages.items():
        pair = _answered_pair(p, seq, 'q%d' % seq)
        for path in pair:
            _age(path, at)
        if any(os.stat(path).st_mtime_ns != at for path in pair):
            pytest.skip('this filesystem loses nanosecond mtimes; the boundary cannot be pinned')
        stamps[seq] = (_stamp_of(pair[0]), _stamp_of(pair[1]))
    assert LocalNode.pending_requests(eid) == []                # all three answered: none due
    assert list(memo[eid]) == ['1']                             # strict <: only the pair under it
    assert memo[eid]['1'] == stamps[1]


# ── 9. answered-cache integrity: the memo is keyed by execution, not by name ─

def test_one_execution_s_memo_never_skips_another_execution_s_request(monkeypatch):
    """local.py:1046 and 1076: `_ANSWERED` is keyed by execution id. Every other
    mailbox test drives one box per case, so keying the memo by the file name, or
    by the box's basename instead of the id - both of which let an answered pair
    in one execution silence the identically named request in another - passes
    the whole existing suite; only two live boxes of the same shape catch it."""
    memo = _memo(monkeypatch)
    answered, due = ids.new_id('execution'), ids.new_id('execution')
    pa = _box(answered)
    old = _long_ago()
    pair_a = _answered_pair(pa, 1, 'same')
    for path in pair_a:
        _age(path, old)
    pb = _box(due, with_res=False)                              # same '1.req.json', same nonce...
    _write(pb.req, '1.req.json', b'{"tool": "Read", "nonce": "same"}')   # ...and no answer at all
    assert LocalNode.pending_requests(answered) == []
    assert LocalNode.pending_requests(due) == [(1, {"tool": "Read", "nonce": "same"})]
    assert memo[answered] == {'1': (_stamp_of(pair_a[0]), _stamp_of(pair_a[1]))}
    assert memo[due] == {}                    # the queried box is rebuilt empty: nothing skipped, nothing kept


# ── 10. error path: a failed atomic answer is an error, never a silent answer ─

def test_an_atomic_answer_that_fails_leaves_the_request_due(monkeypatch):
    """local.py:1088-1094: respond makes class 2, then hands the judged content to
    the atomic writer. No existing test fails the writer: swallowing its error
    (or answering before the write) would silently drop Core's judgment, and the
    request would sit pending against an answer file that never came. The error
    must surface, nothing may be recorded as the answer, and the directory must
    exist before the writer is asked (order)."""
    memo = _memo(monkeypatch)
    eid = ids.new_id('execution')
    p = _box(eid, with_res=False)
    body = {"tool": "Read", "input": {"file_path": "README.md"}, "nonce": "k9"}
    _write(p.req, '1.req.json', body)
    assert LocalNode.pending_requests(eid) == [(1, body)]
    calls = []
    real_makedirs = os.makedirs

    def watch_makedirs(path, *a, **kw):
        calls.append(('makedirs', os.fspath(path)))
        return real_makedirs(path, *a, **kw)

    def failing_writer(path, obj, **kw):
        calls.append(('write', os.fspath(path)))
        assert obj == {'decision': 'allow', 'reason': 'yes', 'nonce': 'k9',
                       'digest': hook.request_digest(body)}     # the judged content was assembled
        raise OSError('the atomic writer could not replace the answer')

    monkeypatch.setattr(os, 'makedirs', watch_makedirs)
    monkeypatch.setattr(config, 'write_json_atomic', failing_writer)
    with pytest.raises(OSError):
        LocalNode.respond(eid, 1, body, 'allow', 'yes')
    assert [what for what, _ in calls] == ['makedirs', 'write']   # the directory first, then the write
    assert calls[1][1] == os.path.join(p.res, '1.res.json')       # the one answer name, no other sink
    assert '1.res.json' not in os.listdir(p.res)                  # nothing answers under that name
    assert LocalNode.pending_requests(eid) == [(1, body)]         # still due: Core will judge it again
    assert memo[eid] == {}
