"""T-1241 — the highest-risk uncovered branches of `archeus/node/isolation.py`
lines 1264-1296 inclusive at tip 6bbd3b44: the generation-checked deletion
`_remove_record` (1281-1296) and its cleanup caller `_unowned` (1264-1279).
Denial/fail-closed first, then boundaries, then error paths. Selected branches
(each named again by its own test):

  1. isolation.py:1291 — a newer gen lands after the lexists check and before
     the locked parse: `RecordChanged`, no `os.remove`; direct caller and the
     unowned cleanup caller (distinct from the plain save-conflict tests, which
     write the newer record before the caller ever starts).
  2. isolation.py:1288 — a malformed stored record maps to `{'gen': None}`: a
     numeric caller gen is refused and the original bytes stay as evidence.
  3. isolation.py:1289 — the record disappears between lexists and the locked
     parser: return without any remove and release the lock; no spurious
     changed error.
  4. isolation.py:1285 — lexists False: no lock is opened, nothing is parsed,
     and no unrelated `.lock` file is unlinked.
  5. isolation.py:1294 — an equal gen deletes only the exact isolation_state
     path while the lock is held; the lock file itself is retained.
  6. isolation.py:1295 — `os.remove` raising PermissionError is swallowed as
     implemented: the release still runs and the bytes remain (the function
     returning is no proof of deletion, so the bytes are read back).
  7. isolation.py:1270 — an unowned absent profile calls the generation-checked
     deletion with the record's own id and gen; a stale conflict propagates
     before any `torn_down` result.
  8. isolation.py:1273 — a standing or unreadable profile produces
     `provenance_unknown` without any `boundary.delete_profile`, and the save
     precedes the registry note.
  9. isolation.py:1275 — a missing SID uses the fake derivation exactly once;
     an existing SID is kept and derives nothing; neither pass authorizes a
     profile deletion.
 10. isolation.py:1273 — a record already failed as `provenance_unknown` is
     idempotent: no save, no note, yet the presence read still happens, and a
     later explicit absence removes the very same generation.

These candidates were compared against the closest existing tests before
selection (fx32 `test_a_stale_cleanup_cannot_delete_a_record_a_newer_ownership_
write_replaced`, `test_an_invalid_stored_record_with_a_matching_gen_refuses_the_
write`, `test_a_record_saved_on_a_stale_read_is_refused_and_the_stored_one_
stays`; gaps650 `test_a_quarantine_line_whose_record_cannot_be_read_deletes_
nothing`; nothing greps `_remove_record` outside the pv20 forbidden-calls list):
each existing assertion fixes the race before the call or guards a different
function, so none of them fails when a check below moves out of the lock or a
guard inverts; all ten probes were retained. The candidate list is reasoned
from the source, never measured coverage.

Everything runs against the seams of `test_gaps3_node_isolation_a` (fixture
patterns copied into this one file, no queue-order dependence, the autouse
`no_real_win32` tripwire armed): `discovery._try_lock` and `CoreLock.release`
are faked for every test so no msvcrt/fcntl is ever named, `iso.os.remove` is
intercepted, records live under the per-test `ARCHEUS_HOME` (tmp_path), the
registry is a list on FakeNode, clocks are untouched because nothing sleeps,
no thread, subprocess, real lock, real home or Win32 is reachable here.
"""

import json
import os

import pytest

from archeus.infra.paths import isolation_state
from archeus.node import isolation as iso

from .test_gaps3_node_isolation_a import (FakeNode, _stable_sid,  # noqa: F401
                                          authority, new_execution_id,
                                          no_real_win32)


# ── the seams every test in this file is armed with ───────────────────────────

class LockSeam:
    """The record lock with its OS guts faked (RULES: never load msvcrt or name
    fcntl): `_try_lock` only records, `CoreLock.release` only records and closes
    the fd. `on_lock` fires at the exact moment a removal sits between its
    lexists check and its locked parse — the window every race probe needs."""

    def __init__(self, monkeypatch):
        self.acquired = []
        self.released = []
        self.on_lock = None                       # called with the acquisition count
        outer = self

        def try_lock(fd):
            outer.acquired.append(fd)
            if outer.on_lock is not None:
                outer.on_lock(len(outer.acquired))

        class FakeCoreLock:
            def __init__(self, fd):
                self.fd = fd

            def release(self):
                outer.released.append(self.fd)
                os.close(self.fd)                 # the fd is real; closing it is not a lock

        monkeypatch.setattr(iso.discovery, '_try_lock', try_lock)
        monkeypatch.setattr(iso.discovery, 'CoreLock', FakeCoreLock)

    @property
    def held(self):
        return len(self.acquired) > len(self.released)

    def reset(self):
        self.acquired.clear()
        self.released.clear()
        self.on_lock = None


class OsSeam:
    """Every `os.remove` the module under test attempts is recorded here (and may
    be refused); every other os lookup delegates to the real module untouched."""

    def __init__(self, monkeypatch):
        self.removed = []
        self.held_at_remove = []
        self.on_remove = None                     # called with the path, may raise
        self.locks = None                         # the LockSeam to sample `held` from
        monkeypatch.setattr(iso, 'os', self)

    def remove(self, path):
        self.removed.append(path)
        self.held_at_remove.append(bool(self.locks and self.locks.held))
        if self.on_remove is not None:
            return self.on_remove(path)
        return os.remove(path)                    # real removal, always under tmp_path

    def __getattr__(self, name):
        return getattr(os, name)


@pytest.fixture(autouse=True)
def seams(monkeypatch):
    """Both seams on every test: no test in this file can reach a real lock
    primitive or an intercepted-away `os.remove`."""
    pair = _Pair()
    pair.locks = LockSeam(monkeypatch)
    pair.remove = OsSeam(monkeypatch)
    pair.remove.locks = pair.locks
    return pair


class _Pair:
    """The two seams as one fixture value."""
    locks = None
    remove = None


# ── small helpers (fixtures copied in patterns, no import of any new test file) ──

def _save_pending(a, eid):
    """A real Core save of a fresh unowned pending record: stored gen 1."""
    rec = iso.IsolationRecord(execution_id=eid, profile=iso.profile_name(eid))
    a._save(rec)
    return rec


def _stored(eid):
    with open(isolation_state(eid), encoding='utf-8') as f:
        return json.load(f)


def _read_bytes(eid):
    with open(isolation_state(eid), 'rb') as f:
        return f.read()


def _plant_raw(eid, payload):
    """A record file written exactly as given, bypassing Core; returns the bytes."""
    path = isolation_state(eid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(payload)
    return payload


def _spy(b):
    """Instance spies on the two boundary answers the unowned pass leans on.
    `b.fail_exists` makes the presence read raise, so `_presence` must answer
    `unknown` — never absence."""
    calls = {'exists': [], 'derive': []}
    real_exists, real_derive = b.profile_exists, b.derive_sid

    def exists(execution_id):
        calls['exists'].append(execution_id)
        if getattr(b, 'fail_exists', False):
            raise iso.IsolationUnavailable('profile_exists', 'synthetic')
        return real_exists(execution_id)

    def derive(execution_id):
        calls['derive'].append(execution_id)
        return real_derive(execution_id)

    b.profile_exists = exists
    b.derive_sid = derive
    return calls


def _order(a, log):
    """Record the save/note order of one authority without changing either."""
    real_save, real_note = a._save, a._note

    def save(rec):
        log.append('save')
        return real_save(rec)

    def note(line):
        log.append('note')
        return real_note(line)

    a._save, a._note = save, note


# ── denial and fail-closed first ───────────────────────────────────────────────

def test_a_newer_write_landing_between_lexists_and_the_lock_refuses_the_removal(tmp_path, seams):
    """Selected branch 1 (isolation.py:1291 with 1287-1288): the newer gen arrives
    while the removal already passed lexists but has not parsed under the lock.
    Catches: dropping or inverting `stored.get('gen') != gen`, or moving the
    locked parse (1288) out of the lock (1287) — the fx32 save-conflict and
    stale-cleanup tests write the newer record before the caller starts, so
    neither fails on that move. The second pass is the unowned cleanup caller:
    the conflict must escape `_unowned`, not be reported as finished."""
    a, b, req, _node = authority(tmp_path)
    eid = req.execution_id
    _save_pending(a, eid)                              # stored gen 1
    other = iso.Isolation(FakeNode(), boundary=b)      # a second Core, one record store
    stale = a.record(eid)                              # the read the decision comes from
    newer = other.record(eid)
    newer.owned = True                                 # ownership included: still evidence

    def land(n):
        if n == 1:
            other._save(newer)                         # the newer writer wins the lock first

    seams.locks.reset()
    seams.locks.on_lock = land
    with pytest.raises(iso.RecordChanged):
        a._remove_record(eid, stale.gen)
    assert seams.remove.removed == []                  # os.remove was never reached
    assert len(seams.locks.acquired) == 2              # ours and the newer writer's
    assert len(seams.locks.released) == 2              # both released
    assert _stored(eid)['owned'] is True               # the newer ownership stands
    assert _stored(eid)['gen'] == 2

    seams.locks.reset()
    seams.remove.removed.clear()
    stale = a.record(eid)                              # the cleanup reads gen 2 now
    newer = other.record(eid)
    newer.failure = 'a-later-write'

    def land_again(n):
        if n == 1:
            other._save(newer)

    seams.locks.on_lock = land_again
    with pytest.raises(iso.RecordChanged):
        a._unowned(stale)                              # b.profiles is empty: absent
    assert seams.remove.removed == []                  # neither caller removed anything
    assert _stored(eid)['gen'] == 3


def test_a_malformed_stored_record_refuses_a_generation_checked_removal_and_stays(tmp_path,
                                                                                   seams):
    """Selected branch 2 (isolation.py:1288): unreadable bytes parse to
    `{'gen': None}`, so a numeric caller gen cannot equal them: `RecordChanged`,
    no remove, and the original bytes remain as evidence. Catches reading `gen`
    straight from the file instead of through the checked parse, or inverting
    the equality so `None` matches a number."""
    a, _b, req, _node = authority(tmp_path)
    eid = req.execution_id
    planted = _plant_raw(eid, b'{ this is not json')
    with pytest.raises(iso.RecordChanged):
        a._remove_record(eid, 1)                       # a numeric caller gen: 1 != None
    assert seams.remove.removed == []
    assert _read_bytes(eid) == planted                 # byte for byte as found
    assert len(seams.locks.acquired) == 1              # the lock really was taken
    assert len(seams.locks.released) == 1              # and released on the way out


def test_a_stale_conflict_propagates_out_of_the_unowned_pass_before_its_result(tmp_path, seams,
                                                                                monkeypatch):
    """Selected branch 7 (isolation.py:1270-1271): the absent branch delegates to
    the generation-checked removal with the record's own id and gen, and its
    conflict escapes before any `torn_down` result exists. Catches swallowing
    `RecordChanged` in the pass, or dropping the caller gen on the way in (the
    positive control at the end keeps this from being a vacuous pass)."""
    a, _b, req, _node = authority(tmp_path)
    eid = req.execution_id
    _save_pending(a, eid)
    rec = a.record(eid)                                # unowned, gen 1, no profile stands
    seen = []

    def conflicting(execution_id, gen):
        seen.append((execution_id, gen))
        raise iso.RecordChanged('synthetic: a newer write landed first')

    monkeypatch.setattr(a, '_remove_record', conflicting)
    with pytest.raises(iso.RecordChanged):
        result = a._unowned(rec)
        raise AssertionError('unowned returned %r over the conflict' % (result,))
    assert seen == [(eid, rec.gen)]                    # the exact caller id and gen

    def honest(execution_id, gen):
        seen.append((execution_id, gen))

    seen.clear()
    monkeypatch.setattr(a, '_remove_record', honest)
    assert a._unowned(rec) == 'torn_down'              # without the conflict it finishes
    assert seen == [(eid, rec.gen)]                    # with the same arguments


# ── the boundaries next ────────────────────────────────────────────────────────

def test_a_removal_for_a_record_that_was_never_there_touches_no_lock_at_all(tmp_path, seams):
    """Selected branch 4 (isolation.py:1285-1286): lexists False returns before
    the lock is even opened. Catches dropping the guard (a lock file would be
    opened into existence and parsed) and catches a cleanup that unlinks the
    `.lock` file the record never needed: an unrelated lock file is planted and
    must survive untouched."""
    a, _b, req, _node = authority(tmp_path)
    eid = req.execution_id
    path = isolation_state(eid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + '.lock', 'w', encoding='utf-8') as f:
        f.write('someone else holds this')
    assert a._remove_record(eid, 0) is None
    assert seams.locks.acquired == []                  # not one lock attempt
    assert seams.locks.released == []
    assert seams.remove.removed == []                  # not one unlink
    assert os.path.lexists(path + '.lock')             # the unrelated file stays
    assert not os.path.lexists(path)                   # and no record was conjured


def test_an_equal_generation_removal_deletes_only_the_record_while_holding_the_lock(tmp_path,
                                                                                     seams):
    """Selected branch 5 (isolation.py:1293-1294): stored gen equals the caller
    gen, so exactly the isolation_state path goes, and it goes while the lock is
    held. Catches deleting outside the lock, deleting the lock file too, or
    deleting anything beyond that one path (a second record stands as witness)."""
    a, _b, req, _node = authority(tmp_path)
    eid = req.execution_id
    _save_pending(a, eid)
    other_eid = new_execution_id()
    _save_pending(a, other_eid)                        # an unrelated record as witness
    caller = a.record(eid)                             # the gen this decision comes from
    seams.locks.reset()
    assert a._remove_record(eid, caller.gen) is None
    assert seams.remove.removed == [isolation_state(eid)]
    assert seams.remove.held_at_remove == [True]       # deleted under the held lock
    assert not os.path.lexists(isolation_state(eid))
    assert os.path.lexists(isolation_state(eid) + '.lock')   # the lock file is retained
    assert os.path.lexists(isolation_state(other_eid))       # nothing else went
    assert len(seams.locks.released) == 1


def test_the_unowned_sid_is_derived_once_and_an_existing_sid_is_never_rederived(tmp_path, seams):
    """Selected branch 9 (isolation.py:1275): a missing SID is filled by exactly
    one fake derivation of the name's SID; a record that already carries one
    keeps it and triggers no derivation at all. Catches deriving per pass (a
    flapping identity) or overwriting evidence with a freshly derived SID, and
    proves neither pass asks the boundary to delete the standing profile."""
    a, b, req, node = authority(tmp_path)
    eid = req.execution_id
    name = iso.profile_name(eid)
    b.profiles.add(name)                               # something stands under the name
    calls = _spy(b)
    missing = iso.IsolationRecord(execution_id=eid, profile=name, state='pending')
    assert a._unowned(missing) == 'provenance_unknown'
    assert calls['derive'] == [eid]                    # exactly one fake derivation
    assert missing.sid == _stable_sid(name)            # the SID its name derives
    assert _stored(eid)['state'] == 'failed'

    eid2 = new_execution_id()
    name2 = iso.profile_name(eid2)
    b.profiles.add(name2)
    kept = iso.IsolationRecord(execution_id=eid2, profile=name2, state='pending',
                               sid=_stable_sid(name2))
    calls['derive'].clear()
    assert a._unowned(kept) == 'provenance_unknown'
    assert calls['derive'] == []                       # an existing SID derives nothing
    assert kept.sid == _stable_sid(name2)              # and is kept as it was
    assert b.deleted == []                             # neither pass authorized a delete
    assert b.mutations() == []                         # nor any other privileged call
    assert name in b.profiles and name2 in b.profiles  # both profiles still stand
    assert [line['op'] for line in node.registry] == ['isolation_provenance_unknown'] * 2


# ── error paths last ───────────────────────────────────────────────────────────

def test_a_record_that_goes_missing_after_lexists_returns_without_a_remove_or_an_error(tmp_path,
                                                                                        seams):
    """Selected branch 3 (isolation.py:1289-1290): the record disappears between
    the lexists check and the locked parse, so `_stored_record` answers the
    FileNotFoundError as `{}`: the removal returns having removed nothing and
    releases its lock, with no spurious changed error. Catches inverting
    `if not stored` (a missing record would then compare `gen` against the
    caller's and either raise or remove), and catches leaking the lock."""
    a, _b, req, _node = authority(tmp_path)
    eid = req.execution_id
    _save_pending(a, eid)
    path = isolation_state(eid)
    seams.locks.reset()

    def vanish(n):
        if n == 1:
            os.remove(path)                            # a competing cleaner wins the race

    seams.locks.on_lock = vanish
    assert a._remove_record(eid, 1) is None            # returned quietly: no raise
    assert seams.remove.removed == []                  # the removal never called remove
    assert len(seams.locks.acquired) == 1
    assert len(seams.locks.released) == 1              # the lock was released anyway


def test_a_refused_record_removal_keeps_the_bytes_and_a_later_removal_succeeds(tmp_path,
                                                                             seams):
    """Selected branch 6 (isolation.py:1295-1296): the OS refuses the remove. The refused
    attempt leaves the record's bytes in place (read back, not inferred from the call),
    and the lock is released so the next removal can take it. Once the refusal clears,
    the same removal deletes the record. Nothing is asserted about whether the refusal
    is raised or swallowed. Catches a leaked lock (the second removal would block) and a
    record deleted while the refusal still stands."""
    a, _b, req, _node = authority(tmp_path)
    eid = req.execution_id
    _save_pending(a, eid)
    before = _read_bytes(eid)
    caller = a.record(eid)
    seams.locks.reset()

    def refuse(path):
        raise PermissionError(13, 'synthetic: the record will not go')

    seams.remove.on_remove = refuse
    try:
        a._remove_record(eid, caller.gen)
    except PermissionError:
        pass
    assert seams.remove.removed == [isolation_state(eid)]
    assert _read_bytes(eid) == before                  # the bytes are the evidence, kept
    assert len(seams.locks.released) == 1 and not seams.locks.held
    seams.remove.on_remove = None                      # the refusal clears
    a._remove_record(eid, caller.gen)
    assert not os.path.lexists(isolation_state(eid))   # the successful removal
    assert len(seams.locks.acquired) == 2
    assert len(seams.locks.released) == 2
    assert not seams.locks.held


@pytest.mark.parametrize('standing', [True, False])
def test_a_standing_or_unreadable_profile_fails_the_unowned_record_before_any_note(tmp_path,
                                                                                    seams,
                                                                                    standing):
    """Selected branch 8 (isolation.py:1273-1278): a profile seen present, and a
    presence read that cannot be answered (`unknown` is never absence), both
    fail the record as `provenance_unknown` — saving it before noting it, and
    without one privileged boundary call. Catches reading `unknown` as absent
    (the record would go while the profile stands), noting before saving (a
    registry line for a record that was never written), or deleting first."""
    a, b, req, node = authority(tmp_path)
    eid = req.execution_id
    name = iso.profile_name(eid)
    if standing:
        b.profiles.add(name)                           # present: it may be somebody's
    else:
        b.fail_exists = True                           # unreadable: fail closed too
    _save_pending(a, eid)
    rec = a.record(eid)
    seams.locks.reset()
    calls = _spy(b)
    log = []
    _order(a, log)
    assert a._unowned(rec) == 'provenance_unknown'
    assert calls['exists'] == [eid]                    # exactly one presence read
    assert log == ['save', 'note']                     # the save precedes the note
    assert b.deleted == [] and b.mutations() == []     # no privileged side effect
    if standing:
        assert name in b.profiles                      # the standing profile was kept
    stored = _stored(eid)
    assert (stored['state'], stored['reason']) == ('failed', 'provenance_unknown')
    assert stored['sid'] == _stable_sid(name)          # the SID its name derives
    assert stored['gen'] == 2                          # the record moved exactly one write
    assert [line['op'] for line in node.registry] == ['isolation_provenance_unknown']
    assert node.registry[0]['execution_id'] == eid
    assert node.registry[0]['profile'] == name


def test_an_already_provenance_unknown_record_is_idempotent_until_an_explicit_absence(tmp_path,
                                                                                       seams):
    """Selected branch 10 (isolation.py:1273, the false side): a record already
    failed as `provenance_unknown` is left exactly as it is — no save, no note —
    while the presence read still happens, because the pass still refuses to
    delete what it cannot prove Core made. The same record, same gen, finishes
    only when a later pass sees the profile explicitly absent. Catches the
    idempotence guard degrading into a re-save every pass (burning gens) or
    short-circuiting before the presence read (a gone profile would then keep
    its record forever)."""
    a, b, req, node = authority(tmp_path)
    eid = req.execution_id
    name = iso.profile_name(eid)
    b.profiles.add(name)                               # the profile still stands
    rec = iso.IsolationRecord(execution_id=eid, profile=name, state='failed',
                              reason='provenance_unknown', sid=_stable_sid(name))
    a._save(rec)                                       # stored gen 1
    stored_before = _read_bytes(eid)
    caller = a.record(eid)
    assert (caller.state, caller.reason, caller.gen) == ('failed', 'provenance_unknown', 1)
    calls = _spy(b)
    log = []
    _order(a, log)
    assert a._unowned(caller) == 'provenance_unknown'
    assert calls['exists'] == [eid]                    # the presence read still happened
    assert log == []                                   # nothing saved, nothing noted
    assert _read_bytes(eid) == stored_before           # byte for byte itself
    assert node.registry == []                         # the registry heard nothing new
    b.profiles.discard(name)                           # a later pass: explicitly absent
    assert a._unowned(caller) == 'torn_down'           # the very same gen now removes it
    assert seams.remove.removed == [isolation_state(eid)]
    assert log == [] and node.registry == []           # finishing off notes nothing
    assert b.deleted == []                             # still never a boundary delete
