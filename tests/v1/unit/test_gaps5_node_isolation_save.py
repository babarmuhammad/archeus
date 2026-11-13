"""T-1239 — the highest-risk uncovered branches of `archeus/node/isolation.py`
lines 780-804 inclusive at tip 6bbd3b44: `Isolation._save`, the generation-compare /
write-under-one-lock protocol (the round-8 slice). Denial and fail-closed first, then
boundaries, then error paths. No source file is edited; these are Linux seam tests —
no Win32, no AppContainer, no Job, no process, no subprocess, no real lock daemon, no
sleep over 0.2 s, everything under `tmp_path` (the v1 conftest's `ARCHEUS_HOME`), the
record lock faked through `discovery._try_lock` / `CoreLock.release`, and the atomic
writer and the clocks intercepted before every call.

Selected branches (each test names its own in its docstring; these are candidate
branches chosen against the existing assertions, not measured coverage):
  1. 791  an unparseable stored record answers the parser sentinel and refuses even
      a caller reading gen 0, with the writer never reached.
  2. 793  a stale save whose caller asserts owned=True is refused when a newer write
      lands after the caller's read but before the lock is taken (ownership included).
  3. 793  a caller that read a nonzero gen cannot resurrect a record the store does
      not have: the missing-record default answers 0, not the caller's gen.
  4. 781  `state == 'invalid'` or a nonempty `applied` refuses before the directory,
      the lock file, the timestamp or the writer see any side effect at all.
  5. 790  a lock this Core can never take fails the save without publishing the
      record, without touching the writer and without moving the generation.
  6. 790-797 the stored read, the generation compare, the increment and the writer
      all run inside one and the same lock lifetime.
  7. 795  the writer is handed the already-incremented generation, exactly once per
      save, and a second caller observes the stored gen before incrementing again.
  8. 798  a writer that raises after the increment restores the prior generation
      (a nonzero prior) and the release still runs.
  9. 801  a writer that answers False restores the prior generation so the very same
      caller can retry from the same gen.
 10. 804  a successful save returns that same record object, and a release that
      fails after a successful write is an error, never a reported success.

The seams (`FakeNode`, `authority`, `new_execution_id`, the `no_real_win32`
tripwire) are the ones of tests/v1/unit/test_gaps3_node_isolation_a.py, imported
exactly as tests/v1/unit/test_fx32_isolation_stop.py imports them; this file starts
no threads and relies on no queue order.
"""

import json
import os
import types

import pytest

from archeus.infra.paths import isolation_state
from archeus.node import isolation as iso

from .test_gaps3_node_isolation_a import (FakeNode, authority,  # noqa: F401
                                          new_execution_id, no_real_win32)


# ── the seams this file adds on top of the gaps3 ones ─────────────────────────

class LockSeam:
    """`discovery._try_lock` and `CoreLock.release`, faked (RULES: never the real
    lock primitive, never msvcrt on the reviewing box): the lifetime of every
    acquire/release is recorded, and the test decides whether the take succeeds,
    is permanently busy, or whether the release fails after a good write."""

    def __init__(self):
        self.events = []            # 'acquire'/'read'/'write' in order
        self.held = 0               # acquires not yet released
        self.busy = False           # answer every _try_lock with OSError
        self.fail_release = None    # an error release() raises after closing

    def _try_lock(self, fd):
        if self.busy:
            raise OSError(16, 'synthetic: the record is busy')
        self.events.append('acquire')
        self.held += 1

    def _release(self, fd):
        assert self.held >= 1, 'released a lock never acquired'
        self.held -= 1
        self.events.append('release')
        try:
            os.close(fd)
        except OSError:             # the fd is real; a double release is still a bug
            pass
        if self.fail_release is not None:
            raise self.fail_release

    def install(self, monkeypatch):
        seam = self

        class FakeCoreLock:
            def __init__(self, fd):
                self._fd = fd

            def release(self):
                seam._release(self._fd)

        monkeypatch.setattr(iso.discovery, '_try_lock', self._try_lock)
        monkeypatch.setattr(iso.discovery, 'CoreLock', FakeCoreLock)


class WriterSeam:
    """`config.write_json_atomic` intercepted before the call: every payload is
    snapshotted, and the test decides between a real write, a quiet False, a raise,
    or 'must never be reached'."""

    def __init__(self, monkeypatch):
        self.calls = []             # (path, deep copy of the payload, kwargs)
        self.mode = 'real'          # real | false | forbidden | a BaseException class
        self.hook = None            # called with (path, payload) before the decision
        self._real = iso.config.write_json_atomic
        monkeypatch.setattr(iso.config, 'write_json_atomic', self)

    def __call__(self, path, obj, **kw):
        if self.hook is not None:
            self.hook(path, obj)
        self.calls.append((path, json.loads(json.dumps(obj)), dict(kw)))
        if self.mode == 'forbidden':
            raise AssertionError('the atomic writer was reached')
        if self.mode == 'false':
            return False
        if isinstance(self.mode, type) and issubclass(self.mode, BaseException):
            raise self.mode('synthetic: the writer died')
        return self._real(path, obj, **kw)

    def payloads(self):
        return [payload for _path, payload, _kw in self.calls]


def _rec(eid, **over):
    return iso.IsolationRecord(execution_id=eid, profile=iso.profile_name(eid), **over)


def _raw(eid):
    with open(isolation_state(eid), encoding='utf-8') as f:
        return json.load(f)


def _plant(eid, data):
    """A stored file written bypassing Core; returns the exact bytes."""
    path = isolation_state(eid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = data if isinstance(data, bytes) else json.dumps(data).encode('utf-8')
    with open(path, 'wb') as f:
        f.write(data)
    return data


def busy_clock(monkeypatch):
    """The lock-wait clock advanced by the caller's polls, never a wall sleep: one
    failed take exhausts RECORD_LOCK_WAIT_S in one iteration (RULES: no sleep)."""
    slept = []

    def monotonic():
        now = box[0]
        box[0] += 10.0
        return now

    box = [0.0]
    monkeypatch.setattr(iso, 'time', types.SimpleNamespace(
        time=lambda: 1000.0, monotonic=monotonic, sleep=slept.append))
    return box, slept


@pytest.fixture(autouse=True)
def state_under_tmp(tmp_path, monkeypatch):
    """Every record path `_save` and `record` resolve is intercepted before the
    call and proven to sit under this test's tmp home (the conftest's ARCHEUS_HOME)."""
    home = os.path.normcase(str(tmp_path / 'archeus-home')) + os.sep
    real = iso.isolation_state
    seen = []

    def spy(key):
        path = real(key)
        assert os.path.normcase(path).startswith(home), path
        seen.append(path)
        return path

    monkeypatch.setattr(iso, 'isolation_state', spy)
    return seen


# ── 1. denial first: an unparseable stored record refuses any write ───────────
#
# isolation.py:791 `stored = _stored_record(...)` -> the parser-failure sentinel
# {'gen': None} vs a caller at gen 0; 793-794 refuse; 797 never reached.

class TestAnUnparseableRecordRefusesEveryWrite:
    def test_a_corrupt_stored_file_refuses_the_write_even_from_a_gen_zero_caller(
            self, tmp_path, monkeypatch):
        """`isolation.py:791`: the file exists but is not JSON, so the parser's
        `except (OSError, ValueError, RecursionError)` answers the gen-None sentinel
        and `isolation.py:793` (`None != 0`) must refuse a plain `pending` caller
        that read gen 0 — exactly the case a fresh first save would answer. Inverting
        the parser fallback to answer `{}` (or the caller's own dict) would let this
        save overwrite corrupt evidence that no reader has vetted. The closest
        existing tests — test_fx32_isolation_stop.py::
        test_an_invalid_stored_record_with_a_matching_gen_refuses_the_write (which
        plants a *parseable* dict that only the *validator* refuses) and
        test_gaps3_node_isolation_a.py::
        test_an_invalid_record_refuses_to_be_saved_and_stays_exactly_as_found
        (which refuses at 781 on the invalid-state guard, before 791 is even reached)
        — never drive `_save` with a file `json.load` itself cannot read, so neither
        sees the parser branch."""
        a, _b, _req, node = authority(tmp_path)
        eid = new_execution_id()
        planted = _plant(eid, b'{"gen": 0, this is not json')
        seam = LockSeam()
        seam.install(monkeypatch)
        writer = WriterSeam(monkeypatch)
        writer.mode = 'forbidden'
        with pytest.raises(iso.RecordChanged):
            a._save(_rec(eid))                      # a fresh caller at gen 0
        assert writer.calls == []                   # the writer was never reached
        assert _read_bytes(eid) == planted          # the corrupt evidence is as found
        assert seam.events == ['acquire', 'release']    # refused inside the lock
        assert node.registry == []                  # and the refusal is quiet


def _read_bytes(eid):
    with open(isolation_state(eid), 'rb') as f:
        return f.read()


# ── 2. a stale save that claims ownership is refused like any other ───────────
#
# isolation.py:793 with the newer write landing between the caller's read and the
# lock take (790), composed with owned=True on the caller's record.

class TestOwnershipGrantsNoWritePrivilege:
    def test_a_stale_owned_save_is_refused_when_a_newer_write_lands_before_the_lock(
            self, tmp_path, monkeypatch):
        """`isolation.py:793`, composed the way a real race composes it: the caller
        read the record while it was unowned at gen 1, then claims `owned=True`;
        a *newer* save lands after that read but before this save takes its lock
        (the `_record_lock` seam fires it, the fx32 pattern). The compare must see
        stored gen 2 against the caller's stale 1 and raise `RecordChanged` —
        ownership buys no privilege, exactly as 792's comment claims ("ownership
        included"). The closest existing tests each miss one half:
        test_fx32_isolation_stop.py::
        test_a_stale_read_is_refused_when_a_newer_write_lands_before_the_lock uses
        plain (never owned) records, and
        test_fx32_isolation_stop.py::
        test_ownership_is_never_turned_back_to_unowned_by_a_write_from_an_older_read
        has no write landing between the read and the lock. Dropping `owned` from
        the compared trust (e.g. `if stored.gen != rec.gen and not rec.owned`)
        passes both of those and fails this one."""
        a, b, req, _node = authority(tmp_path)
        eid = req.execution_id
        writer = WriterSeam(monkeypatch)
        a._save(_rec(eid))                                   # gen 0 -> 1, unowned
        stale = _rec(eid, gen=1, owned=True, sid=b.derive_sid(eid), state='pending')
        newer = a.record(eid)                                # the fresher read (gen 1)
        newer.reason = 'newer-writer'
        real_lock, landed = iso._record_lock, []

        def lock_after_a_newer_write(path):
            if not landed:
                landed.append(True)
                a._save(newer)                               # gen 1 -> 2 lands first
            return real_lock(path)

        monkeypatch.setattr(iso, '_record_lock', lock_after_a_newer_write)
        with pytest.raises(iso.RecordChanged):
            a._save(stale)
        stored = _raw(eid)
        assert stored['gen'] == 2 and stored['reason'] == 'newer-writer'
        assert stored['owned'] is False        # the stale claim of ownership never landed
        assert stale.gen == 1                  # refused before the increment: untouched
        assert len(writer.calls) == 2          # only the first and the newer write ran
        assert all(payload['owned'] is not True for _p, payload, _k in writer.calls[1:])


# ── 3. a record the store does not have answers gen 0, never the caller's ─────
#
# isolation.py:791 (FileNotFoundError -> {} read at 793 by `stored.get('gen', 0)`)
# with a caller whose read said gen > 0.

class TestAMissingStoreCannotBeResurrected:
    def test_a_save_from_a_nonzero_read_refuses_when_the_store_has_no_record(
            self, tmp_path, monkeypatch):
        """`isolation.py:793` over the missing-file answer of 791: a caller that
        read gen 5 against a store with *no file at all* must see the default 0
        and refuse — the compare is `stored.get('gen', 0) != rec.gen`, so `5 != 0`
        raises `RecordChanged` and nothing is published. Weakening the default to
        the caller's own gen (or skipping the compare when the file is absent)
        would let a stale reader publish a whole record — with its own gen chain —
        as if nothing had been deleted since it read. No existing test combines a
        missing file with a nonzero caller: every fx32 stale test reads back a file
        that exists (gen >= 1 on both sides), and
        test_gaps_isolation_650.py::test_a_quiet_write_failure_is_an_error_and_not_a_
        saved_record saves a gen-0 caller into a missing file, where both defaults
        agree and the compare cannot tell the difference."""
        a, _b, _req, _node = authority(tmp_path)
        eid = new_execution_id()
        seam = LockSeam()
        seam.install(monkeypatch)
        writer = WriterSeam(monkeypatch)
        writer.mode = 'forbidden'
        assert not os.path.lexists(isolation_state(eid))
        with pytest.raises(iso.RecordChanged):
            a._save(_rec(eid, gen=5))           # what a stale read of a since-gone file says
        assert writer.calls == []
        assert not os.path.lexists(isolation_state(eid))     # nothing was published
        assert seam.events == ['acquire', 'release']


# ── 4. the 781 guard refuses before any side effect exists ────────────────────
#
# isolation.py:781-785, both halves, ahead of 786 (timestamp), 788-789
# (path and makedirs) and 790-797 (lock and writer).

class TestTheUntrustedGuardRunsBeforeEverySideEffect:
    def test_an_invalid_or_applied_record_refuses_before_dir_lock_or_timestamp(
            self, tmp_path, monkeypatch):
        """`isolation.py:781` in both halves: an `invalid`-state record (the shape
        `record()` hands back for untrustworthy evidence) and a record claiming any
        `applied` access (S1 applies none) must raise `ValueError` while 786-797
        have not run at all: `updated`/`at` still 0.0 (no timestamp taken), the
        state directory never created, no `.lock` file opened, the writer never
        reached, nothing noted. The closest existing tests check the *outcome*, not
        the *position*: test_pv20_isolation.py::test_applied_access_stays_empty_on_
        every_path only asserts `not os.path.exists(isolation_state(...))` — which
        stays true even if the guard moved below the makedirs of 789 and the lock of
        790, silently creating the directory, the lock file and a wall-clock stamp
        for a record Core refuses to have written — and
        test_gaps3_node_isolation_a.py::test_an_invalid_record_refuses_to_be_saved_
        and_stays_exactly_as_found plants a file, so it can prove the bytes survive
        but never that no dir, lock or stamp appeared alongside."""
        a, _b, _req, node = authority(tmp_path)
        seam = LockSeam()
        seam.install(monkeypatch)
        writer = WriterSeam(monkeypatch)
        writer.mode = 'forbidden'
        grant = iso.Grant(str(tmp_path / 'granted'), 'rx', 'runtime')
        bad = (
            _rec(new_execution_id(), state='invalid', reason='unreadable'),
            _rec(new_execution_id(), applied=(grant,)),
        )
        for rec in bad:
            with pytest.raises(ValueError):
                a._save(rec)
            assert rec.updated == 0.0 and rec.at == 0.0     # 786-787 never ran
        assert writer.calls == [] and seam.events == []      # 790-797 never ran
        for rec in bad:
            path = isolation_state(rec.execution_id)
            assert not os.path.lexists(path)
            assert not os.path.lexists(path + '.lock')
            assert not os.path.isdir(os.path.dirname(path))  # 789 never ran
        assert node.registry == []                           # and the refusal is quiet


# ── 5. a lock that can never be taken publishes nothing ───────────────────────
#
# isolation.py:790 `with _record_lock(path)` when discovery._try_lock always
# answers OSError, on the very first save of an execution.

class TestABusyRecordStaysUnwritten:
    def test_a_failed_lock_take_writes_no_record_and_moves_no_generation(
            self, tmp_path, monkeypatch):
        """`isolation.py:790`: `os.makedirs` (789) has run, but every take of the
        record lock is refused, so `_record_lock` closes its fd and raises `OSError`
        before the body runs. The first save of an execution must therefore leave
        the record file absent (no unowned, never-validated record published), the
        writer uncalled, the caller's gen exactly as it came, and the clock never
        slept past the bounded wait. The closest existing test —
        test_fx32_isolation_stop.py::test_a_record_write_that_cannot_take_its_lock_
        fails_and_leaves_the_record — holds a real second lock over an *already
        saved* record and asserts the old bytes stay: it cannot express "nothing
        was ever published", never counts writer calls, and never checks that the
        refused caller's generation was not moved."""
        a, _b, _req, node = authority(tmp_path)
        eid = new_execution_id()
        seam = LockSeam()
        seam.busy = True
        seam.install(monkeypatch)
        writer = WriterSeam(monkeypatch)
        writer.mode = 'forbidden'
        _box, slept = busy_clock(monkeypatch)                # no wall sleep at all
        rec = _rec(eid)
        with pytest.raises(OSError):
            a._save(rec)
        assert writer.calls == []
        assert not os.path.lexists(isolation_state(eid))     # no record published
        assert os.path.isdir(os.path.dirname(isolation_state(eid)))   # 789 did run
        assert rec.gen == 0 and rec.updated == 1000.0        # stamp only; the gen did not move
        assert seam.events == []                             # a take never succeeded
        assert slept == []                                   # the wait bounded by the fake clock
        assert node.registry == []


# ── 6. read, compare, increment and write share one lock lifetime ─────────────
#
# isolation.py:790-797: one acquire ... one release, with 791, 793, 795 and 797
# all inside it, in that order.

class TestTheWholeDecisionSitsInsideOneLockLifetime:
    def test_parse_compare_increment_and_write_all_run_under_one_acquire(
            self, tmp_path, monkeypatch):
        """`isolation.py:790-797`: the stored read of 791, the compare of 793, the
        increment of 795 and the writer of 797 must all fall between one `_try_lock`
        and its matching `CoreLock.release`, in that order. Hoisting the stored read
        above the `with` (so the compare decides on a pre-lock snapshot — the exact
        race 792's comment is about) reorders the events; moving the writer out of
        the body lets it run with the lock already released. The closest existing
        test — test_fx32_isolation_stop.py::
        test_a_writer_stalled_after_its_generation_check_keeps_the_record_lock —
        proves only that a *stalled writer* blocks a second writer; its own name
        concedes it says nothing about where the read and compare sit relative to
        the take, and it asserts no order at all."""
        a, _b, req, _node = authority(tmp_path)
        eid = req.execution_id
        seam = LockSeam()
        seam.install(monkeypatch)
        real_stored = iso._stored_record

        def read_then(path, execution_id, api):
            seam.events.append('read')
            return real_stored(path, execution_id, api)

        monkeypatch.setattr(iso, '_stored_record', read_then)
        writer = WriterSeam(monkeypatch)

        def seen_under_the_lock(path, payload):
            seam.events.append('write')
            assert seam.held == 1, 'the writer ran outside the record lock'
            assert payload['gen'] == 1        # 795 already incremented before 797 wrote it

        writer.hook = seen_under_the_lock
        a._save(_rec(eid))
        assert seam.events == ['acquire', 'read', 'write', 'release']
        assert seam.held == 0
        assert _raw(eid)['gen'] == 1


# ── 7. the writer is handed the incremented gen, exactly once per save ────────
#
# isolation.py:795 `prior, rec.gen = rec.gen, rec.gen + 1` before 797's
# `rec.as_dict()`, and a second caller reading the stored gen before its own
# increment.

class TestTheGenerationTheWriterSees:
    def test_each_save_hands_the_writer_the_incremented_gen_and_adds_exactly_one(
            self, tmp_path, monkeypatch):
        """`isolation.py:795`: the payload 797 writes must carry gen == prior + 1 at
        the moment the writer is called (so a compare-before-write can never match a
        pre-increment file), and each successful save must move the stored chain by
        exactly one: caller 1 at gen 0 writes gen 1, a *fresh second caller* read from
        the store sees that stored gen 1 and writes gen 2 — total two writer calls,
        no skipped or repeated number. Moving the increment after `as_dict()` (or
        writing the prior) leaves the file answering the old gen forever, which turns
        every later stale-check into a rubber stamp. The closest existing tests —
        test_pins_node_isolation_650_1300.py::
        test_the_first_write_of_a_record_fixes_its_time (asserts only `at`/`updated`)
        and the fx32 stale tests (assert the read-back gen but never the payload the
        writer actually received) — never look inside the dict handed to
        `write_json_atomic`, so any of those mutations keeps their assertions true."""
        a, _b, req, _node = authority(tmp_path)
        eid = req.execution_id
        writer = WriterSeam(monkeypatch)
        first = _rec(eid)
        a._save(first)
        assert writer.payloads()[0]['gen'] == 1 and first.gen == 1
        assert _raw(eid)['gen'] == 1
        second = a.record(eid)                     # a fresh caller through the store
        assert second.gen == 1                     # it must *see* the incremented gen
        a._save(second)
        assert writer.payloads()[1]['gen'] == 2 and second.gen == 2
        assert _raw(eid)['gen'] == 2
        assert len(writer.calls) == 2              # exactly one write, one step, per save


# ── 8. a writer that dies after the increment gives the gen back ──────────────
#
# isolation.py:798-800 `except BaseException: rec.gen = prior; raise`, with a
# nonzero prior, and 790's finally releasing anyway.

class TestADeadWriterLeavesNoAdvancedGeneration:
    def test_a_keyboard_interrupt_in_the_writer_restores_a_nonzero_gen_and_releases(
            self, tmp_path, monkeypatch):
        """`isolation.py:798-800`: the writer raises `KeyboardInterrupt` *after* 795
        already incremented. The caller's record must come back to the *prior* gen —
        a prior of 1, so `rec.gen = prior` replaced by `rec.gen = 0` (or by nothing)
        is visible — the exception must propagate unchanged (a Ctrl-C is not turned
        into a swallow or an OSError), and the lock's finally must still release
        exactly once per take. No timestamp rollback is asserted: the card keeps no
        such contract for `updated`. The closest existing tests only cover the
        gen-0 case at 801 (the False answer,
        test_gaps_isolation_650.py::test_a_quiet_write_failure_is_an_error_and_not_a_
        saved_record and test_pins_node_isolation_650_1300.py::
        test_a_write_that_answers_failure_is_a_failure both save a fresh gen-0
        record and never raise from inside the writer, and none checks the release)."""
        a, _b, req, _node = authority(tmp_path)
        eid = req.execution_id
        seam = LockSeam()
        seam.install(monkeypatch)
        writer = WriterSeam(monkeypatch)
        keep = _rec(eid, reason='keeper')
        a._save(keep)                                # gen 0 -> 1 lands for real
        assert seam.events == ['acquire', 'release']
        fresh = a.record(eid)                        # the caller's read: gen 1 (nonzero)
        assert fresh.gen == 1
        fresh.reason = 'interrupted'
        before = _read_bytes(eid)
        writer.mode = KeyboardInterrupt
        with pytest.raises(KeyboardInterrupt):
            a._save(fresh)
        assert fresh.gen == 1                        # the prior, not 0 and not 2
        assert seam.events.count('acquire') == seam.events.count('release') == 2
        assert seam.held == 0                        # the finally released despite the death
        assert _read_bytes(eid) == before            # the stored record never moved


# ── 9. a False answer from the writer restores the gen for a same-caller retry ─
#
# isolation.py:801-803 `if not written: rec.gen = prior; raise OSError`.

class TestAQuietlyFailedWriteCanBeRetriedFromTheSameGen:
    def test_a_false_writer_answer_restores_the_gen_so_the_same_caller_may_retry(
            self, tmp_path, monkeypatch):
        """`isolation.py:801-803`: the writer answers False, so the save must raise
        `OSError` naming the execution, restore the caller's record to its *prior*
        (nonzero) gen, leave the stored bytes untouched — and then the *very same
        record object*, unchanged, must save successfully once the writer works,
        because the restore is what keeps its gen equal to the stored one. This is
        the retry half of the contract: pinning `rec.gen = prior` to 0 (or omitting
        it) makes the retry diverge from the store and raise `RecordChanged` here.
        The closest existing tests retry with a *different*, freshly built record —
        test_pins_node_isolation_650_1300.py::
        test_a_write_that_answers_failure_is_a_failure re-saves `record_for(eid)`
        after restoring the writer, a brand-new gen-0 object the failed save never
        touched — and the 650 quiet-failure test asserts no generation at all, so
        neither can see a wrong restore on the object that actually failed."""
        a, _b, req, _node = authority(tmp_path)
        eid = req.execution_id
        seam = LockSeam()
        seam.install(monkeypatch)
        writer = WriterSeam(monkeypatch)
        keep = _rec(eid, reason='keeper')
        a._save(keep)                                # gen 0 -> 1 lands for real
        fresh = a.record(eid)                        # caller reads gen 1
        assert fresh.gen == 1
        fresh.reason = 'never-landed'
        before = _read_bytes(eid)
        writer.mode = 'false'
        with pytest.raises(OSError) as got:
            a._save(fresh)
        assert eid in str(got.value)                 # names its own execution
        assert fresh.gen == 1                        # the prior restored on this object
        assert _read_bytes(eid) == before            # nothing was written or replaced
        writer.mode = 'real'
        a._save(fresh)                               # the retry, same object, same gen
        assert fresh.gen == 2 and _raw(eid)['reason'] == 'never-landed'
        assert seam.events == ['acquire', 'release'] * 3


# ── 10. the return is the record; a failed release is never a success ─────────
#
# isolation.py:804 `return rec`, composed with the finally-release of 790
# (`discovery.CoreLock(fd).release`) failing after a completed write.

class TestTheReturnAndTheRelease:
    def test_a_saved_record_can_be_saved_again_and_a_failing_release_raises(
            self, tmp_path, monkeypatch):
        """`isolation.py:804` with 790's teardown composed behind it. First the
        success shape: the record `_save` returns carries the incremented gen, and that
        returned record can be saved again on the gen it reports, so a caller keeps
        writing from what it was handed. Then the failure:
        the write itself succeeds but `CoreLock.release` raises, so `_save` must
        raise that error rather than return — a `return rec` that swallows (or a
        `finally` turned into a pass-over) would report a saved record whose lock
        teardown nobody observed. The closest existing tests
        (test_fx32_isolation_stop.py::test_a_record_lock_is_released_when_its_
        holder_process_dies, which exercises a whole *process* death in a
        subprocess, and every success-path save in pins and fx32, which never fail
        the release) never separate "the write worked" from "the release worked",
        and none saves a returned record a second time."""
        a, _b, req, _node = authority(tmp_path)
        seam = LockSeam()
        seam.install(monkeypatch)
        writer = WriterSeam(monkeypatch)
        rec = _rec(req.execution_id, reason='identity')
        returned = a._save(rec)
        assert returned.reason == 'identity'
        assert _raw(req.execution_id)['gen'] == returned.gen == 1
        returned.reason = 'reused'
        again = a._save(returned)
        assert again.gen == 2 and _raw(req.execution_id)['gen'] == 2
        assert _raw(req.execution_id)['reason'] == 'reused'
        eid2 = new_execution_id()
        seam.fail_release = OSError(5, 'synthetic: the release failed')
        with pytest.raises(OSError) as got:
            a._save(_rec(eid2, reason='unreported'))       # no success is reported
        assert 'release failed' in str(got.value)
        assert len(writer.calls) == 3                      # the write itself did run
        assert _raw(eid2)['gen'] == 1                      # and its gen is what was written
