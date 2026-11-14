"""T-1344: the highest-risk uncovered branches of `archeus/node/mxc_boundary.py` 105-149
(MXC profile identity, generation gating and residue recording), at the source tip 6b1a30b8
of round eleven.

Selected probes, ranked denial and fail-closed first, then boundaries, then error paths.
Each names the source branch whose removal or inversion its assertion catches:

  1 `create_profile`/`delete_profile` 121-122, 134   an invalid execution id is refused before
                                                    any ledger read
  2 `delete_profile` 136-137                          no ledger refuses before the reservation
                                                    is touched
  3 `_generations` 118-119                            an invalid journal after a completed
                                                    generation refuses and names that journal
  4 `create_profile` 124-127                          the first unresolved generation is the one
                                                    named, never a later one
  5 `_generations` 114-117                            the scan stops at the first absent name:
                                                    a later journal with no -p1 is not read
  6 `delete_profile` 141-145                          the residue line is appended, sorted JSON,
                                                    one line per release
  7 `delete_profile` 146                              a release drops only its own key
  8 `derive_sid` 105-106                              the identity is the marker and the name,
                                                    with no ledger read and no OS call
  9 `create_profile` 128-131 with 146                 a released name is created again with
                                                    existed False
 10 `create_profile` 128-129 (PREMISE)                recreating a live profile keeps the grants
                                                    it already holds; source resets them to []

Nothing here starts a process or reaches the OS: the job and launch seams are a recorder that
fails on any call, subprocess is replaced by a function that fails, and the ledger is the real
journal under tmp_path. Probe 10 is a strict xfail: the setup it depends on is a separate test
that must pass, so a fixture mistake cannot hide behind the xfail.
"""

import json
import os
import subprocess

import pytest

from archeus.core.domain import ids
from archeus.node import isolation as iso
from archeus.node import mxc, mxc_boundary, mxc_ledger
from archeus.node.mxc_boundary import MxcBoundary


class Recorder:
    """Stands in for the Job and handle code: any call at all is a privileged side effect."""

    def __getattr__(self, name):
        raise AssertionError('no OS call expected, got %s' % name)


class ExplodingLedger:
    """A ledger whose journals must never be read on the path under test."""

    def __init__(self, root):
        self.root = os.fspath(root)

    def journals(self):
        raise AssertionError('the ledger must not be read here')


@pytest.fixture(autouse=True)
def no_process(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('no process expected')
    monkeypatch.setattr(subprocess, 'Popen', refuse)
    monkeypatch.setattr(subprocess, 'run', refuse)
    monkeypatch.setattr(subprocess, 'call', refuse)


def make(tmp_path, *, clock=lambda: 12.5, ledger=None):
    if ledger is None:
        ledger = mxc_ledger.Ledger(tmp_path / 'ledger')
    return MxcBoundary(ledger=ledger, jobs=Recorder(), clock=clock, win32=None,
                       sdk_root=None, pins=None, schema_validator=None,
                       process_reader=None)


def seed(boundary, name, *ops):
    digest = '0' * 64
    facts = {'intent': dict(requested_policy_digest=digest, planned=[], applied=[],
                            observed={}),
             'ownership': dict(pid=1, create_time=1, requested_policy_digest=digest,
                               applied=[], observed={}, owned=[]),
             'disposal': dict(verified_absent=True), 'completion': dict(outcome=0),
             'quarantine': dict(reason='restart_unverified')}
    for op in ops:
        boundary.ledger.append(name, op, **facts[op])


COMPLETED = ('intent', 'ownership', 'disposal', 'completion')


def residue_lines(boundary):
    with open(os.path.join(boundary.ledger.root, mxc_boundary.RESIDUE),
              encoding='utf-8') as f:
        return f.read().splitlines()


# ── 1: an invalid id is refused before any ledger read (121-122, 134) ──

@pytest.mark.parametrize('call', ['create_profile', 'delete_profile'])
def test_an_invalid_execution_id_is_refused_before_the_ledger_is_read(tmp_path, call):
    b = make(tmp_path, ledger=ExplodingLedger(tmp_path / 'ledger'))
    with pytest.raises(iso.IsolationUnavailable, match='profile_name'):
        getattr(b, call)('exe_not-an-id')
    assert b._reserved == {}


# ── 2: delete without a ledger leaves the reservation alone (136-137) ──

def test_a_delete_without_a_ledger_keeps_the_reservation(tmp_path):
    b = make(tmp_path)
    eid = ids.new_id('execution')
    b.create_profile(eid)
    b.ledger = None
    with pytest.raises(iso.IsolationUnavailable, match='mxc_ledger'):
        b.delete_profile(eid)
    assert b.profile_exists(eid) is True
    assert b._reserved[iso.principal(eid).key] == []


# ── 3: an invalid journal after a completed generation is the one named (118-119) ──

def test_an_invalid_journal_after_a_completed_generation_refuses_and_is_named(tmp_path):
    b = make(tmp_path)
    eid = ids.new_id('execution')
    seed(b, mxc_ledger.journal_name(eid, 1), *COMPLETED)
    damaged = mxc_ledger.journal_name(eid, 2)
    with open(os.path.join(b.ledger.root, damaged + '.jsonl'), 'wb') as f:
        f.write(b'not a journal\n')
    with pytest.raises(iso.IsolationUnavailable, match='generation_unresolved') as err:
        b.create_profile(eid)
    assert damaged in str(err.value)
    assert b.profile_exists(eid) is False


# ── 4: the first unresolved generation is the one named (124-127) ──

def test_the_first_unresolved_generation_is_the_one_named(tmp_path):
    b = make(tmp_path)
    eid = ids.new_id('execution')
    seed(b, mxc_ledger.journal_name(eid, 1), 'intent')
    seed(b, mxc_ledger.journal_name(eid, 2), 'intent')
    with pytest.raises(iso.IsolationUnavailable, match='generation_unresolved') as err:
        b.create_profile(eid)
    text = str(err.value)
    assert mxc_ledger.journal_name(eid, 1) in text
    assert mxc_ledger.journal_name(eid, 2) not in text
    assert b.profile_exists(eid) is False


# ── 5: the scan stops at the first absent name (114-117) ──

def test_a_later_generation_with_no_first_one_is_never_read(tmp_path):
    b = make(tmp_path)
    eid = ids.new_id('execution')
    seed(b, mxc_ledger.journal_name(eid, 2), 'intent')
    assert b.create_profile(eid)['created'] is True
    assert b.profile_exists(eid) is True


# ── 6: the residue line is appended, as sorted JSON, once per release (141-145) ──

def test_each_release_appends_one_sorted_residue_line(tmp_path):
    b = make(tmp_path)
    first, second = ids.new_id('execution'), ids.new_id('execution')
    b.create_profile(first)
    b.delete_profile(first)
    b.create_profile(second)
    b.delete_profile(second)
    lines = residue_lines(b)
    assert len(lines) == 2
    for line in lines:
        assert line == json.dumps(json.loads(line), sort_keys=True)
    assert [json.loads(x)['execution_id'] for x in lines] == [
        iso.principal(first).key, iso.principal(second).key]


# ── 7: a release drops only its own key (146) ──

def test_releasing_one_execution_leaves_another_reserved(tmp_path):
    b = make(tmp_path)
    kept, gone = ids.new_id('execution'), ids.new_id('execution')
    b.create_profile(kept)
    b.create_profile(gone)
    b.delete_profile(gone)
    assert b.profile_exists(gone) is False
    assert b.profile_exists(kept) is True
    assert list(b._reserved) == [iso.principal(kept).key]


# ── 8: the identity is a marker and a name, with no read and no OS call (105-106) ──

def test_the_identity_is_the_marker_and_the_name_with_no_ledger_read(tmp_path):
    b = make(tmp_path, ledger=ExplodingLedger(tmp_path / 'ledger'))
    eid = ids.new_id('execution')
    assert b.derive_sid(eid) == mxc_boundary.MARKER + iso.validated_profile(eid)
    assert b.derive_sid(eid).startswith(mxc_boundary.MARKER)
    assert iso.registry_sid(b.derive_sid(eid)) == ''


# ── 9: a released name is created again as new (128, 146, 131) ──

def test_a_released_name_is_created_again_and_says_it_did_not_exist(tmp_path):
    b = make(tmp_path)
    eid = ids.new_id('execution')
    b.create_profile(eid)
    b.delete_profile(eid)
    again = b.create_profile(eid)
    assert again == {'profile': iso.profile_name(eid), 'sid': b.derive_sid(eid),
                     'created': True, 'existed': False, 'package_dir': ''}
    assert b.profile_exists(eid) is True


# ── 10: PREMISE, recreating a live profile keeps its grants (128-129) ──

def test_recreating_a_live_profile_keeps_the_grant_it_holds_setup(tmp_path, monkeypatch):
    monkeypatch.setattr(mxc, 'scan_grant', lambda path: None)
    b = make(tmp_path)
    eid = ids.new_id('execution')
    b.create_profile(eid)
    path = str(tmp_path / 'granted')
    os.mkdir(path)
    sid = b.derive_sid(eid)
    assert b.grant_established(path, sid, 'rw') is True
    assert b.granted_to(path, sid) is True
    again = b.create_profile(eid)
    assert again['existed'] is True


@pytest.mark.xfail(strict=True, reason='mxc_boundary.py:129 resets the grants of a live '
                   'profile to [] on re-create, while create reports existed=True')
def test_recreating_a_live_profile_keeps_the_grant_it_holds(tmp_path, monkeypatch):
    monkeypatch.setattr(mxc, 'scan_grant', lambda path: None)
    b = make(tmp_path)
    eid = ids.new_id('execution')
    b.create_profile(eid)
    path = str(tmp_path / 'granted')
    os.mkdir(path)
    sid = b.derive_sid(eid)
    assert b.grant_established(path, sid, 'rw') is True
    b.create_profile(eid)
    assert b.granted_to(path, sid) is True
