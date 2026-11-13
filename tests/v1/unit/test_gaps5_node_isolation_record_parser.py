"""T-1238 — the highest-risk uncovered branches of `archeus/node/isolation.py`
lines 125-135 and 581-628 inclusive (tip 6bbd3b44): whether a persisted isolation
record can be trusted is what decides whether a record WRITE or a record DELETE may
trust its generation. Denial and fail-closed first, then boundaries, then error paths.

What the slice says:

  125-135 `_stored_record(path, execution_id, api)` — the only reader a record write
          (`_save`, line 791) or a record delete (`_remove_record`, line 1288) decides
          from:
    129-130   FileNotFoundError            -> `{}`            (no record: the very
                first write is allowed, its missing gen reads as generation 0)
    131-132   OSError | ValueError | RecursionError -> `{'gen': None}` (a record
                nobody could read is never read as a new generation zero)
    133       `isinstance(d, dict) and not _record_problem(d, execution_id, api)`
    134           -> the WHOLE mapping as stored (its generation is trusted)
    135           -> the `{'gen': None}` sentinel: a shape that cannot be trusted may
                not lend its generation to a write or to a delete
  581-588 `_shape_problem`, 591-605 `_identity_problem`, 608-628 `_record_problem` —
          the validator line 133 consults.

Selected branches, ranked (denial/fail-closed, then boundaries, then error paths).
Each test's docstring names the branch whose removal or inversion it catches and the
closest existing test whose assertion misses it. These are candidate branches reasoned
out of the source, not measured coverage:

 1. 133/135 + 613-614  a valid-looking gen from a record naming ANOTHER execution is
    refused (`execution_id_mismatch`) and cannot authorize a write.
 2. 624-627             `owned` and `preexisting` together, in state `failed`, are
    refused (`ownership_conflict`); the sentinel cannot authorize the cleanup delete.
 3. 617-620             non-empty `applied` / non-empty `capabilities` are refused
    despite a correct identity and generation, each against its empty control.
 4. 594-598, 602-603    a profile that is not the derived name, an SID the fake boundary
    does not derive and a malformed `planned` row are refused; nothing of the original
    record escapes the sentinel.
 5. 584-586, 621-623    an unknown key or a condition pair that is not `[bool, str]` is
    refused; a FALSE condition boolean is a valid shape, an integer pretending to be
    one is not.
 6. 133/135 (+582-583)  a top-level list, scalar, null or empty object is the sentinel —
    no crash out of the reader and no borrowed generation (133's isinstance gate and
    582-583 are each other's backstop, so they are asserted as the pair they are).
 7. 129-132             FileNotFoundError alone is `{}`; PermissionError and any other
    OSError are `{'gen': None}`, never a new generation zero.
 8. 133-134, 615-616,   a trusted SID-less permitted state and a trusted owned
    600-601              matching-SID state come back as the whole original mapping,
                        gen and evidence kept; an invented state (`state_unknown`)
                        and an established record that left its SID out do not.
 9. 131-132             malformed UTF-8 and malformed JSON (the ValueError family) are
    the sentinel, the bytes exactly as found.
10. 131-132             a JSON decoder `RecursionError` is the sentinel, not a crash
    (the decoder is made to raise, so no real recursion limit is relied on).

Nothing here reaches the OS: the boundary is a fake that only answers, the record lock
and its file descriptor are faked, every path is under `tmp_path`, nothing sleeps, no
thread is started, no Win32 primitive is loaded, no environment value is read, no real
subprocess or network is used, and no real `json` recursion limit is assumed. The
autouse tripwire below fails any test that reaches a real Win32 entry point.
"""

import builtins
import hashlib
import json
import os

import pytest

from archeus.core.domain import ids
from archeus.infra import discovery
from archeus.infra.paths import isolation_state
from archeus.node import isolation as iso

#: the sentinel `_stored_record` answers with when a record cannot be trusted
SENTINEL = {'gen': None}
#: the generation every fixture plants: a writer believes it, so a sentinel that
#: leaked the stored generation would be obvious next to one that refused it
PLANT_GEN = 4


# ── the seams: nothing below this line may reach the OS ──────────────────────

@pytest.fixture(autouse=True)
def no_real_win32(monkeypatch):
    """The synthetic boundary is the reason none of this is reachable; the guard is
    the belt (RULES: written on Linux, reviewed on Windows, never a real DLL)."""
    hits = []
    for name in ('_CreateAppContainerProfile', '_DeleteAppContainerProfile',
                 '_GetSecurityInfoByNameW', '_CreateProcessW', '_CreateJobObjectW',
                 '_AssignProcessToJobObject', '_TerminateProcess', '_CloseHandle',
                 '_SetInformationJobObject', '_ResumeThread', '_OpenProcess'):
        def trip(*a, _name=name):
            hits.append(_name)
            raise AssertionError('the real %s was reached' % _name)
        monkeypatch.setattr(iso, name, trip, raising=False)
    yield hits
    assert hits == [], 'a real mutation primitive was reached: %r' % (hits,)


@pytest.fixture(autouse=True)
def fake_record_lock(monkeypatch):
    """The record lock without a real file lock: `_try_lock` and `CoreLock.release` are
    the named seams (this file must never reach `msvcrt`/`fcntl`), and the fd is closed
    here so nothing leaks. The log is the order assertion — `['try', 'release']` per
    decided write — and proves that a refused decision still released what it took."""
    log = []

    def try_lock(fd):
        log.append('try')

    class FakeCoreLock:
        def __init__(self, fd):
            self.fd = fd

        def release(self):
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
                log.append('release')

    monkeypatch.setattr(discovery, '_try_lock', try_lock)
    monkeypatch.setattr(discovery, 'CoreLock', FakeCoreLock)
    return log


def _stable_sid(name):
    """A SID derived from a profile name: deterministic (no `hash` salt, no platform
    order), so the fake boundary answers the same on Windows as on Linux."""
    digest = int(hashlib.sha1(str(name).encode('utf-8')).hexdigest(), 16)
    return 'S-1-15-3-9-%012d' % (digest % (10 ** 12),)


class FakeBoundary:
    """Only the answers `_identity_problem` asks for, each one a knob. It never
    launches anything, never names the OS, and records every derivation it was asked
    for, so a test can tell the real validator from a stub answering 'invalid'."""
    id = 'fake'

    def __init__(self):
        self.available_ok = True
        self.derive_fail = ''
        self.derive_calls = []
        self.created = []
        self.deleted = []
        self.assigned = []

    def available(self):
        return self.available_ok

    def derive_sid(self, execution_id):
        if self.derive_fail:
            raise iso.IsolationUnavailable(self.derive_fail, 'synthetic')
        self.derive_calls.append(execution_id)
        return _stable_sid(iso.profile_name(execution_id))

    def mutations(self):
        """Every call that would change OS state: the profile store, a Job, a process."""
        return self.created + self.deleted + self.assigned


class FakeNode:
    """The registry instrument: a list, never a real node."""
    id = 'fake-node'

    def __init__(self):
        self.registry = []

    def _registry(self, line):
        self.registry.append(line)


def new_execution_id():
    return ids.new_id('execution')


def authority(boundary=None):
    """An `Isolation` authority whose only OS is the fake boundary."""
    b = boundary or FakeBoundary()
    node = FakeNode()
    return iso.Isolation(node, boundary=b), b, node


def _row(execution_id):
    return {'path': iso.profile_name(execution_id), 'access': 'rx', 'row': 'runtime'}


def good(api, execution_id, **over):
    """A record in every way the validator accepts: the derived profile, the SID the
    fake boundary derives, a permitted state, the empty `applied`/`capabilities`, a well
    formed condition pair, and a non-default generation and evidence."""
    d = {'execution_id': execution_id, 'profile': iso.profile_name(execution_id),
         'sid': api.derive_sid(execution_id), 'state': 'established', 'reason': '',
         'failure': '', 'conditions': {'identity': [True, '']},
         'planned': [_row(execution_id)], 'applied': [], 'pid': 4242,
         'create_time': 1.5, 'capabilities': [], 'owned': True, 'preexisting': False,
         'attempts': 0, 'at': 11.0, 'updated': 22.0, 'gen': PLANT_GEN}
    d.update(over)
    return d


def plant(execution_id, payload):
    """Write the record file exactly as given, bypassing Core; returns (path, bytes)."""
    path = isolation_state(execution_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode('utf-8')
    with open(path, 'wb') as f:
        f.write(data)
    return path, data


def stored_bytes(path):
    with open(path, 'rb') as f:
        return f.read()


def unreadable_on_read(monkeypatch, path, error):
    """Make reading *this* record path fail with *error* (an OSError), portably and
    without touching a permission bit: only the text-mode read `_stored_record` does is
    blocked, so the real file stays on disk and the bytes can still be read back."""
    target = os.path.normcase(os.path.abspath(path))
    real_open = builtins.open

    def opener(file, *a, **kw):
        mode = str(kw.get('mode', a[0] if a else 'r'))
        name = os.path.normcase(os.path.abspath(str(file)))
        if name == target and 'r' in mode and '+' not in mode and 'b' not in mode:
            raise error
        return real_open(file, *a, **kw)

    monkeypatch.setattr(builtins, 'open', opener)


def writer(api, execution_id, gen=PLANT_GEN):
    """What a reader that believes the stored generation would try to save."""
    return iso.IsolationRecord(execution_id=execution_id,
                               profile=iso.profile_name(execution_id),
                               sid=api.derive_sid(execution_id), gen=gen)


# ── 1. denial: another execution's record cannot lend its generation ──────────
#
# isolation.py:133 (the `_record_problem` gate) + 613-614 (`execution_id_mismatch`),
# answered by isolation.py:135; the consumer is `_save`'s generation check (line 793)

class TestAForeignRecordCannotLendItsGeneration:
    def test_a_record_naming_another_execution_never_lends_its_generation(
            self, tmp_path):
        """Catches removing or loosening isolation.py:613-614 (`if
        d.get('execution_id') != execution_id: return 'execution_id_mismatch'`) or
        making the gate at isolation.py:133 believe a record whose own file says whose it
        is. The file at THIS execution's path carries a valid gen and everything else
        derived from THIS id; only its `execution_id` field names somebody else. Without
        613-614, line 133 accepts it, line 134 hands back gen 4 and `_save` — reading a
        record it never reconciled — writes straight over it.

        Closest existing test: `test_pv20_isolation.py::TestPhaseAContainment::
        test_malformed_record_files_are_contained_and_visible` asserts
        `a.invalid[mismatched] == 'execution_id_mismatch'` — that is the DISPLAY reader,
        `Isolation.record` (lines 743-772, outside this slice), reached through reclaim
        and the sweep. It never asks what `_stored_record` hands `_save`, so a reader that
        refused while a writer still trusted the foreign record's generation would pass
        it. The validator here is the real `_record_problem` and the SID comes from the
        fake boundary's `derive_sid`, so nothing is a stub that merely answers 'invalid' —
        and the empty `derive_calls` list proves the boundary was consulted only while
        BUILDING the fixture, never while deciding."""
        a, b, node = authority()
        eid = new_execution_id()
        other = new_execution_id()
        forged = good(b, eid)
        forged['execution_id'] = other
        assert iso._record_problem(forged, eid, b) == 'execution_id_mismatch'
        assert iso._record_problem(good(b, eid), eid, b) == ''         # the control

        path, data = plant(eid, forged)
        b.derive_calls[:] = []
        assert iso._stored_record(path, eid, b) == SENTINEL
        assert b.derive_calls == []                                    # 613-614 refuses
        # the record before any identity field is consulted: the order pin
        rec = writer(b, eid)                                           # believes gen 4
        with pytest.raises(iso.RecordChanged):
            a._save(rec)
        assert rec.gen == PLANT_GEN                                    # never advanced
        assert stored_bytes(path) == data                              # evidence as found
        assert b.mutations() == [] and node.registry == []             # and it is quiet


# ── 2. denial: a profile Core did not create is Core's to keep, never to delete ─
#
# isolation.py:626-627 (`ownership_conflict`), reached behind 624-625

class TestOwnershipConflictCannotAuthorizeCleanup:
    def test_owned_and_preexisting_together_are_refused_even_in_the_failed_state(
            self, tmp_path):
        """Catches removing isolation.py:626-627 (`if d.get('preexisting') and
        d.get('owned'): return 'ownership_conflict'`) or moving it above 624-625. A
        record that says both "Core created this profile" and "this profile was already
        standing" cannot be believed about ownership, and the sentinel of 135 is the only
        thing that keeps `_remove_record` from trusting its gen and DELETING a profile
        somebody else may own. The state is `failed` — the only state `preexisting` is
        permitted in — so nothing else can refuse it. The order is asserted too: a
        preexisting ESTABLISHED profile is refused as `preexisting_state` (624-625),
        never as a bare ownership conflict, and deleting that arm would flip the word.
        The trusted control (`owned=False`) really is removed, which is what makes the
        refusal, and not the delete, the thing under test.

        Closest existing test: `test_pv20_isolation.py::TestPhaseAContainment::
        test_a_forged_record_mutates_nothing_and_is_left_as_found`, whose FORGED cases
        'ownership claimed for a refused profile' and 'a refused profile claiming to be
        established' assert the `ownership_conflict` / `preexisting_state` words and
        untouched bytes — but only through `establish`/`teardown`/`reclaim`/the sweep, i.e.
        through `Isolation.record`. None of them is `_remove_record`, whose whole decision
        is the mapping `_stored_record` returns: the delete attempt at the record's OWN
        generation, `deleted == []` afterwards, and the trusted control that really is
        removed (which is what makes the refusal, not the delete, the thing under test)
        are asserted nowhere."""
        a, b, node = authority()
        eid = new_execution_id()
        conflict = good(b, eid, state='failed', owned=True, preexisting=True)
        assert iso._record_problem(conflict, eid, b) == 'ownership_conflict'
        assert iso._record_problem(dict(conflict, state='established'),
                                   eid, b) == 'preexisting_state'
        assert iso._record_problem(dict(conflict, owned=False), eid, b) == ''

        path, data = plant(eid, conflict)
        assert iso._stored_record(path, eid, b) == SENTINEL
        with pytest.raises(iso.RecordChanged):
            a._remove_record(eid, PLANT_GEN)
        assert stored_bytes(path) == data
        assert b.deleted == [] and b.mutations() == [] and node.registry == []

        kept = new_execution_id()                                      # the trusted
        trust = good(b, kept, state='failed', owned=False, preexisting=True)
        path2, _as_found = plant(kept, trust)
        assert iso._stored_record(path2, kept, b) == trust
        a._remove_record(kept, PLANT_GEN)
        assert not os.path.lexists(path2)                              # so deletion needs
        assert b.mutations() == []                                     # a trusted record


# ── 3. denial: S1 applies no access and the identity holds no capability ───────
#
# isolation.py:617-618 (`applied_access`) and 619-620 (`capabilities`)

class TestGrantEvidenceIsRefusedDespiteAGoodIdentity:
    @pytest.mark.parametrize('over,want', [
        ({'applied': [{'path': 'x', 'access': 'rw', 'row': 'workspace'}]}, 'applied_access'),
        ({'capabilities': ['S-1-15-3-1']}, 'capabilities'),
        ({'capabilities': ['S-1-15-3-2'], 'applied': [{'path': 'y'}]}, 'applied_access'),
    ], ids=['one_applied_row', 'one_network_capability', 'applied_answers_first'])
    def test_a_record_claiming_applied_access_is_refused_where_the_empty_form_is_trusted(
            self, tmp_path, over, want):
        """Catches removing either arm of isolation.py:617-620, or reordering them (the
        third case is both at once, and `applied` must answer first): the identity, the
        generation and every other field are exactly right, so only these two arms stand
        between a forged "access was applied here / the principal holds a capability"
        record and line 134 handing its generation to a writer. S1 applies none and §4.9
        grants none, so trusting that shape would let `_save` overwrite the evidence with
        Core's own guess and `_remove_record` erase it.

        Closest existing test: the same FORGED parametrization of
        `test_pv20_isolation.py::TestPhaseAContainment::
        test_a_forged_record_mutates_nothing_and_is_left_as_found`, whose 'applied access
        on the python install' and 'a capability' cases assert the reader's `invalid` word,
        and `::test_applied_access_stays_empty_on_every_path`, which only proves Core never
        WRITES such a field. Neither puts the forged field in front of the reader a write
        decides from, nor against the empty control that must stay trusted, nor checks that
        the refused writer's generation never advanced."""
        a, b, node = authority()
        eid = new_execution_id()
        base = good(b, eid)
        assert iso._record_problem(base, eid, b) == ''                 # the control first
        forged = dict(base, **over)
        assert iso._record_problem(forged, eid, b) == want
        path, data = plant(eid, forged)
        assert iso._stored_record(path, eid, b) == SENTINEL
        rec = writer(b, eid)                                           # believes gen 4
        with pytest.raises(iso.RecordChanged):
            a._save(rec)
        assert rec.gen == PLANT_GEN
        with pytest.raises(iso.RecordChanged):
            a._remove_record(eid, PLANT_GEN)
        assert stored_bytes(path) == data
        assert b.mutations() == [] and node.registry == []


# ── 4. denial: neither the profile name nor the SID is believed ────────────────
#
# isolation.py:594-595 (`profile_mismatch`), 596-598 (`planned_malformed`),
# 602-603 (`sid_mismatch` against the boundary's own derivation)

class TestIdentityIsCheckedAgainstWhatTheIdDerives:
    @pytest.mark.parametrize('mutate,want', [
        (lambda d, api, other: d.update(profile=iso.profile_name(other)),
         'profile_mismatch'),
        (lambda d, api, other: d.update(sid='S-1-15-3-9-000000000001'), 'sid_mismatch'),
        (lambda d, api, other: d.update(planned=[{'path': 'x'}]), 'planned_malformed'),
        (lambda d, api, other: d.update(planned=['runtime']), 'planned_malformed'),
    ], ids=['borrowed_profile', 'borrowed_sid', 'planned_missing_a_key',
            'planned_as_strings'])
    def test_a_record_the_boundary_does_not_derive_is_refused_and_leaks_no_ownership(
            self, tmp_path, mutate, want):
        """Catches removing the profile comparison at isolation.py:594-595, the planned
        row check at 596-598 or the comparison against `api.derive_sid` at 602-603 (the
        `sid_underivable` arm at 604-605 is already pinned elsewhere and is not repeated
        here). The wrong SID is a well-formed one that only the fake boundary's answer
        can refuse, and the `derive_calls` log pins the ORDER as well as the fact: the
        boundary is consulted exactly once, and only for the case that gets that far —
        a profile or planned refusal must not consume a derivation. The sentinel is what
        keeps an untrusted record's OWNERSHIP out of a decision, because `_save` and
        `_remove_record` read `.get('gen')` out of precisely this mapping: `owned`,
        `preexisting`, `sid`, `profile`, `planned` and the stored gen must not survive it.

        Closest existing test: FORGED in
        `test_pv20_isolation.py::TestPhaseAContainment::
        test_a_forged_record_mutates_nothing_and_is_left_as_found` covers the words
        `profile_mismatch`, `sid_mismatch` and `planned_malformed` for the display reader,
        and `test_gaps_isolation_1.py::TestPersistedTrust::
        test_a_record_sid_that_cannot_be_derived_is_refused_as_ununderivable` — the only
        direct call of `_identity_problem` in the suite — asserts a refusal word. Nothing
        asks what `_stored_record` RETURNS, so a sentinel that leaked the record's
        generation and its `owned`/`preexisting`/`sid`/`planned` fields to a writer would
        pass every one of them unnoticed, and no existing test counts the derivations the
        boundary was asked for, so the check ORDER is unpinned."""
        a, b, node = authority()
        eid = new_execution_id()
        other = new_execution_id()
        base = good(b, eid)
        assert iso._record_problem(base, eid, b) == ''                 # the control
        mutated = dict(base)
        mutate(mutated, b, other)
        b.derive_calls[:] = []
        assert iso._record_problem(mutated, eid, b) == want
        assert b.derive_calls == ([eid] if want == 'sid_mismatch' else [])

        path, data = plant(eid, mutated)
        stored = iso._stored_record(path, eid, b)
        assert stored == SENTINEL
        for leaked in ('owned', 'preexisting', 'sid', 'profile', 'planned', 'state'):
            assert leaked not in stored
        assert stored.get('gen', 0) != PLANT_GEN                       # no borrowed gen

        rec = writer(b, eid)                                           # believes gen 4
        with pytest.raises(iso.RecordChanged):
            a._save(rec)
        assert stored_bytes(path) == data
        assert b.mutations() == [] and node.registry == []


# ── 5. denial: unknown keys and condition pairs that are not [bool, str] ───────
#
# isolation.py:584-586 (`unknown_fields:…`) and 621-623 (`conditions_malformed`)

class TestOnlyTheDeclaredShapeAndTheDeclaredConditions:
    @pytest.mark.parametrize('over,want', [
        ({'conditions': {'identity': [True, '']}}, ''),
        ({'conditions': {'identity': [False, 'no Job was created']}}, ''),
        ({'conditions': {'identity': [True]}}, 'conditions_malformed'),
        ({'conditions': {'identity': [True, '', 'extra']}}, 'conditions_malformed'),
        ({'conditions': {'identity': [True, 7]}}, 'conditions_malformed'),
        ({'conditions': {'identity': [1, '']}}, 'conditions_malformed'),
        ({'conditions': {'identity': {'ok': True}}}, 'conditions_malformed'),
        ({'conditions': {'identity': 'true'}}, 'conditions_malformed'),
        ({'conditions': {'identity': [[True, '']]}}, 'conditions_malformed'),
        ({'conditions': {}}, ''),
        ({'borrowed_from': 'another execution'}, 'unknown_fields:borrowed_from'),
        ({'gen2': 9}, 'unknown_fields:gen2'),
        ({'conditions': {'identity': [1, '']}, 'gen2': 9}, 'unknown_fields:gen2'),
    ], ids=['true_pair', 'a_false_boolean_is_a_valid_shape', 'pair_too_short',
            'pair_too_long', 'reason_not_a_string', 'integer_pretending_to_be_bool',
            'pair_is_a_mapping', 'pair_is_a_string', 'pair_is_a_nested_list',
            'no_conditions_at_all', 'one_unknown_key', 'a_second_generation_field',
            'an_unknown_key_answers_before_the_conditions'])
    def test_a_record_is_believed_only_in_its_declared_shape(self, tmp_path, over, want):
        """Catches loosening isolation.py:621-623 (`isinstance(v, list) and len(v) == 2
        and isinstance(v[0], bool) and isinstance(v[1], str)`) or 584-586 (the unknown-key
        check), and the two orderings that matter. A condition pair whose boolean is an
        INTEGER must not widen the condition evidence: a permissive `bool(v[0])` or
        `isinstance(v[0], int)` accepts 1, and a record could then claim any condition
        held, while a FALSE boolean is a valid shape and stays trusted — inverting the
        `not all(...)` refuses every valid record, and dropping `len(v) == 2` accepts a
        bare `[True]` as "the condition held, no reason needed". An unknown key answers
        before the condition check (last two cases), which is the order asserted here.

        Closest existing test: `test_gaps_isolation_1.py::TestPersistedTrust::
        test_a_quarantine_line_is_believed_only_in_its_declared_shape` parametrizes
        `_ledger_problem` over the LEDGER types (`op`, `at`, `planned`) with one extra
        `grants` key, and FORGED's 'nested conditions' case checks the display reader.
        The record's own `conditions` pair — the only field whose CONTENTS read like
        evidence rather than type — the integer-as-boolean widening, and a second
        generation-like key are asserted nowhere for the reader a write decides from."""
        a, b, node = authority()
        eid = new_execution_id()
        mutated = dict(good(b, eid), **over)
        assert iso._record_problem(mutated, eid, b) == want
        # the in-memory arm of the same test: a TUPLE is not a list, and it is the one
        # shape that never survives json, so it can only reach the validator directly
        assert iso._record_problem(dict(good(b, eid), conditions={'identity': (True, '')}),
                                   eid, b) == 'conditions_malformed'
        path, data = plant(eid, mutated)
        if want:
            assert iso._stored_record(path, eid, b) == SENTINEL
            with pytest.raises(iso.RecordChanged):
                a._remove_record(eid, PLANT_GEN)
            with pytest.raises(iso.RecordChanged):
                a._save(writer(b, eid))
            assert stored_bytes(path) == data
            assert b.deleted == [] and b.mutations() == [] and node.registry == []
        else:
            assert iso._stored_record(path, eid, b) == mutated          # trusted, whole
            assert stored_bytes(path) == data


# ── 6. denial: a record that is not an object at its top level ─────────────────
#
# isolation.py:133 (`isinstance(d, dict)` short-circuit) and 135 (the sentinel);
# isolation.py:582-583 is where the validator's own non-dict arm runs

class TestANonObjectRecordIsNeitherACrashNorAGeneration:
    @pytest.mark.parametrize('raw,want', [
        (b'[{"gen": 9, "execution_id": "exe_0000000000000000000000000"}]', 'not_an_object'),
        (b'"archeus.exec.stolen"', 'not_an_object'),
        (b'9', 'not_an_object'),
        (b'null', 'not_an_object'),
        (b'true', 'not_an_object'),
        (b'{}', 'execution_id_mismatch'),
    ], ids=['top_level_list_with_a_gen', 'top_level_string', 'top_level_number',
            'top_level_null', 'top_level_boolean', 'empty_object'])
    def test_a_record_that_is_not_a_json_object_is_the_sentinel_and_borrows_nothing(
            self, tmp_path, raw, want):
        """Catches removing the `isinstance(d, dict)` half of isolation.py:133 together
        with `_shape_problem`'s own arm at 582-583 — the two guards cover each other, so
        either alone is invisible and only both at once let a list, a str, an int, a bool
        or a None reach `set(d)`/`d.get` inside `_shape_problem`, raising a TypeError or an
        AttributeError straight out of `_stored_record`, the record lock and the sweep; the
        "fix" of `except Exception: return {}` then makes a garbage file look like no record
        at all and invites a first write over it. And it catches line 135 answering with
        `{}` instead of the sentinel: the list case carries a generation of its own (9),
        so a borrowed generation is the visible failure here. `_shape_problem`'s own
        `not_an_object` arm (582-583) is asserted on the same payloads.

        Closest existing test: `test_pv20_isolation.py::TestPhaseAContainment::
        test_malformed_record_files_are_contained_and_visible` counts
        `'not_an_object' in a.invalid.values()` (it plants `b'[1, 2]'`) for the display
        reader, and `::test_malformed_or_forged_ledger_lines_reach_no_profile_operation`
        does the same for ledger lines. Nothing asserts what the reader a WRITE sees, and
        the empty-object case — which must be the sentinel while an ABSENT file is `{}`
        (probe 7) — is separated nowhere."""
        a, b, node = authority()
        eid = new_execution_id()
        path, data = plant(eid, raw)
        assert iso._record_problem(json.loads(raw), eid, b) == want
        stored = iso._stored_record(path, eid, b)
        assert stored == SENTINEL and isinstance(stored, dict)
        assert 9 not in list(stored.values())                            # nothing borrowed
        with pytest.raises(iso.RecordChanged):
            a._remove_record(eid, PLANT_GEN)
        with pytest.raises(iso.RecordChanged):
            a._save(writer(b, eid, gen=0))
        assert stored_bytes(path) == data
        assert b.mutations() == [] and node.registry == []


# ── 7. boundary: no file is no record; an unreadable file is no trust ──────────
#
# isolation.py:129-130 (FileNotFoundError -> {}) against 131-132 (any other OSError
# -> the sentinel)

class TestAbsentIsNotUnreadable:
    def test_an_absent_record_is_no_record_while_an_unreadable_one_is_no_trust(
            self, tmp_path, monkeypatch):
        """Catches widening isolation.py:129's `except FileNotFoundError` to the whole
        OSError family, and catches 131-132 answering `{}`: a record that could not be
        read would then read as "no record yet", `.get('gen', 0)` would be 0, and `_save`
        would happily overwrite a file Core could not even open — destroying the evidence
        `_unowned`, the sweep and a restarted Core all reconcile against. The trap is
        exact: the file on disk is at generation 1 while the writer believes generation 0,
        so ONLY a sentinel (`None`, never equal to 0) refuses it — and a genuinely absent
        file must still allow that very first write, and must not make `_remove_record`
        claim a conflict for a record that was never there. A directory standing where the
        record goes is the non-FileNotFoundError OSError; no permission bit is touched
        anywhere (the read is refused by a seam, not by the OS).

        Closest existing test: `test_fx32_isolation_stop.py::
        test_an_invalid_stored_record_with_a_matching_gen_refuses_the_write` plants
        `{'gen': 0, 'junk': True}` — a READABLE file refused for its shape, at exactly the
        generation the writer already believes — and
        `test_pv20_isolation.py::TestPhaseAContainment::
        test_malformed_record_files_are_contained_and_visible` counts a directory and
        unreadable bytes among three `'unreadable'`s for the display reader. Neither
        separates 129-130 from 131-132 for the reader a write decides from, and neither
        shows that a genuinely absent file still permits its first write."""
        a, b, node = authority()
        absent = new_execution_id()
        missing = isolation_state(absent)
        assert not os.path.lexists(missing)
        assert iso._stored_record(missing, absent, b) == {}
        a._remove_record(absent, 0)                                      # nothing to delete
        assert not os.path.lexists(missing)                              # and no raise
        first = writer(b, absent, gen=0)
        assert a._save(first) is first and first.gen == 1                # the first write
        assert stored_bytes(missing) != b''                              # is allowed

        eid = new_execution_id()
        path, data = plant(eid, good(b, eid, gen=1))
        unreadable_on_read(monkeypatch, path, PermissionError(13, 'denied (synthetic)'))
        assert iso._stored_record(path, eid, b) == SENTINEL
        stale = writer(b, eid, gen=0)                                    # believes zero,
        with pytest.raises(iso.RecordChanged):                           # the file says
            a._save(stale)                                               # one: `{}` would
        assert stale.gen == 0                                            # have written
        with pytest.raises(iso.RecordChanged):
            a._remove_record(eid, 1)
        assert stored_bytes(path) == data                                # bytes as found

        blocked = new_execution_id()                                     # the other
        directory = isolation_state(blocked)                             # OSError arm
        os.makedirs(directory, exist_ok=True)
        assert iso._stored_record(directory, blocked, b) == SENTINEL
        assert b.mutations() == [] and node.registry == []


# ── 8. boundary: a trusted record comes back whole ────────────────────────────
#
# isolation.py:133 (the passing gate) and 134 (`return d`)

class TestATrustedRecordIsHandedBackWhole:
    @pytest.mark.parametrize('state,sid,owned,want', [
        ('pending', '', True, ''),                      # SIDLESS_STATES: no SID needed
        ('failed', '', False, ''),
        ('torn_down', '', True, ''),
        ('quarantined', 'DERIVED', False, ''),
        ('established', 'DERIVED', True, ''),            # an established one must carry it
        ('running', 'DERIVED', True, 'state_unknown'),   # 615-616: not a state at all
        ('established', '', True, 'sid_missing'),        # 600-601: no empty identity
    ], ids=['pending_sidless_owned', 'failed_sidless_unowned', 'torn_down_sidless',
            'quarantined_with_the_derived_sid', 'established_with_the_derived_sid',
            'an_invented_state', 'established_without_a_sid'])
    def test_a_trusted_record_returns_the_whole_mapping_with_its_generation_and_evidence(
            self, tmp_path, state, sid, owned, want):
        """Catches line 134 answering with a filtered or partial mapping (`{'gen':
        d['gen']}`), with `{}`, or with the sentinel for a state that is PERMITTED to be
        SID-less: line 628's `d['state'] in SIDLESS_STATES` is what decides the two SID
        cases below, and 615-616 / 600-601 decide the two refused ones — an invented state
        and an established record that left its SID out must not lend gen 4 to the DELETE
        of a profile Core may never have created. `_save`/`_remove_record` decide from the
        generation and nothing else, so a mapping that lost it refuses every legitimate
        write and one that invented it allows every stale one. Every non-default field is
        planted and compared (gen, pid, create_time, at, updated, attempts, the condition
        pair, the planned row) because that is the evidence the reader keeps and the writer
        must not overwrite.

        Closest existing test: `test_pins_node_isolation_1_650.py::
        test_only_a_persisted_state_is_a_state_and_a_sidless_one_is_trusted_only_in_some`
        covers a state table and the `sid_missing` word, and
        `::test_a_record_survives_the_dict_it_is_written_as` round-trips a record — both
        through `Isolation.record()`, which REBUILDS an `IsolationRecord` field by field
        and so cannot see whether the mapping itself came back, and neither reaches
        `_remove_record`; the fx32 save tests run 134 only with a generation that then
        MISMATCHES, never asserting the returned mapping is intact."""
        a, b, node = authority()
        eid = new_execution_id()
        real = b.derive_sid(eid) if sid == 'DERIVED' else sid
        payload = good(b, eid, state=state, sid=real, owned=owned)
        path, data = plant(eid, payload)
        assert iso._record_problem(payload, eid, b) == want
        stored = iso._stored_record(path, eid, b)
        if want:                                                     # the two refusals:
            assert stored == SENTINEL                                # no gen to delete on
            with pytest.raises(iso.RecordChanged):                   # and the delete does
                a._remove_record(eid, PLANT_GEN)                     # not happen
            assert stored_bytes(path) == data
            assert b.deleted == [] and b.mutations() == [] and node.registry == []
            return
        assert stored == payload and sorted(stored) == sorted(payload)
        assert stored['gen'] == PLANT_GEN and stored['pid'] == 4242
        assert stored['create_time'] == 1.5
        assert (stored['at'], stored['updated']) == (11.0, 22.0)
        assert stored['conditions'] == {'identity': [True, '']}
        assert stored['planned'] == [_row(eid)] and stored['owned'] is owned
        assert stored['state'] == state and stored['sid'] == real
        assert b.mutations() == [] and node.registry == []              # a trusted read is
        assert stored_bytes(path) == data                                # quiet, read-only

        a._remove_record(eid, PLANT_GEN)                                 # its own gen is
        assert not os.path.lexists(path)                                 # the delete's key
        again = new_execution_id()
        plant(again, good(b, again))
        with pytest.raises(iso.RecordChanged):                           # a stale decision
            a._remove_record(again, PLANT_GEN - 1)                       # erases nothing
        assert os.path.lexists(isolation_state(again))


# ── 9. error path: the bytes are not text, or not JSON ────────────────────────
#
# isolation.py:131-132, the ValueError half (UnicodeDecodeError, JSONDecodeError)

class TestUndecodableBytesAreEvidenceNotACrash:
    @pytest.mark.parametrize('raw', [
        b'{"sid": "\xff\xfe\xff", "gen": 4}',
        b'{ this is not json',
        b'',
        b'{"gen": 4, "execution_id": ',
    ], ids=['not_utf8', 'not_json', 'empty_file', 'truncated_object'])
    def test_bytes_that_neither_decode_nor_parse_are_the_sentinel_and_stay_byte_for_byte(
            self, tmp_path, raw):
        """Catches the `ValueError` member disappearing from isolation.py:131: a
        UnicodeDecodeError from `open(..., encoding='utf-8')` or a JSONDecodeError from
        `json.load` would then escape the record lock and the sweep, and the "fix" of
        `except ValueError: return {}` would make the file look absent and invite an
        overwrite of it. It also catches that clause answering `{}` rather than the
        sentinel. The hazard is proven before the call — these very bytes, read the way
        `_stored_record` reads them, raise a ValueError — so a fixture that quietly
        stopped being the hazard fails this test instead of passing it.

        Closest existing test: `test_pv20_isolation.py::TestPhaseAContainment::
        test_malformed_record_files_are_contained_and_visible` counts three `'unreadable'`s
        (bad JSON, non-UTF-8 bytes, a directory) and re-reads the planted bytes — for the
        display reader only. None of those three is the reader a write or a delete trusts,
        and none checks that the file is refused at the generation its own bytes claim."""
        a, b, node = authority()
        eid = new_execution_id()
        path, data = plant(eid, raw)
        assert data == raw and os.path.lexists(path)                    # present, not absent
        with pytest.raises(ValueError):                                  # the hazard is real
            with open(path, encoding='utf-8') as handle:
                json.load(handle)
        assert iso._stored_record(path, eid, b) == SENTINEL
        with pytest.raises(iso.RecordChanged):
            a._remove_record(eid, PLANT_GEN)
        with pytest.raises(iso.RecordChanged):
            a._save(writer(b, eid, gen=0))
        assert stored_bytes(path) == raw
        assert b.mutations() == [] and node.registry == []


# ── 10. error path: the decoder itself gives up ───────────────────────────────
#
# isolation.py:131-132, the RecursionError half

class TestADecoderThatGivesUpIsTheSentinel:
    def test_a_record_the_json_decoder_cannot_walk_is_the_sentinel_and_not_a_crash(
            self, tmp_path, monkeypatch):
        """Catches `RecursionError` disappearing from isolation.py:131: `json.load` raises
        it — neither an OSError nor a ValueError — while descending a nested file, and
        uncaught it leaves the record lock's fd behind and takes the whole sweep down with
        it; the `except Exception: return {}` refactor that "fixes" it would report no
        record and let a first write overwrite the file. The decoder is made to raise for
        THIS path through a named seam, and the fixture is a bounded 40-deep array that
        every interpreter parses, so nothing here depends on a real recursion limit and
        the same assertion holds on Windows as on Linux.

        Closest existing test: `test_pv20_isolation.py::TestCorrectivePass::
        test_a_deeply_nested_record_is_invalid_evidence_not_a_crash` drives
        `Isolation.record()`, whose own `except (OSError, ValueError, RecursionError)` at
        line 755-756 is a different statement, and relies on a genuinely deep document
        (100000 brackets) whose exact depth nothing checks. No test sends a decoder failure
        through the reader that `_save` and `_remove_record` trust, which is where an
        unreadable record that answered `{}` would actually destroy evidence."""
        a, b, node = authority()
        eid = new_execution_id()
        bounded = b'[' * 40 + b']' * 40
        path, data = plant(eid, bounded)
        calls = []
        real_load = json.load

        def giving_up(handle, *arg, **kw):
            name = os.path.normcase(os.path.abspath(str(getattr(handle, 'name', ''))))
            if name == os.path.normcase(os.path.abspath(path)):
                calls.append(handle.name)
                raise RecursionError('synthetic decoder limit')
            return real_load(handle, *arg, **kw)

        monkeypatch.setattr(iso.json, 'load', giving_up)
        assert iso._stored_record(path, eid, b) == SENTINEL
        assert calls == [path]                                           # the decoder failed
        with pytest.raises(iso.RecordChanged):
            a._remove_record(eid, PLANT_GEN)
        with pytest.raises(iso.RecordChanged):
            a._save(writer(b, eid, gen=0))
        assert stored_bytes(path) == data
        assert b.mutations() == [] and node.registry == []
