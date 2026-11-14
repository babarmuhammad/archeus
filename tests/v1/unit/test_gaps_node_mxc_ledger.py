"""T-783: highest-risk uncovered branches of archeus/node/mxc_ledger.py.

Fail-closed and denial paths first, then boundary values, then error paths.
All OS calls go through the seams the existing tests use (ledger.config.write_atomic,
ledger.os.fsync); no real processes, no network, no sleeps.
Style and fixtures follow tests/v1/unit/test_mxc_ledger_gaps.py.
"""

import hashlib
import os
import sys
from types import SimpleNamespace

import pytest

from archeus.node import mxc_ledger as ledger


DIGEST = 'a' * 64
FULL_FACTS = {'applied': [], 'observed': {}, 'owned': []}


@pytest.fixture
def journal(tmp_path):
    return ledger.Ledger(tmp_path / 'ledger')


def create(journal):
    return journal.create('e1', {'request': 'only'},
                          lambda: (SimpleNamespace(pid=41, create_time=900), dict(FULL_FACTS)),
                          lambda child: None)


def intent(seq=0, **over):
    base = {'execution_id': 'e1', 'op': 'intent', 'seq': seq,
            'requested_policy_digest': DIGEST, 'planned': [], 'applied': [], 'observed': {}}
    base.update(over)
    return base


def owner(seq=1, **over):
    base = {'execution_id': 'e1', 'op': 'ownership', 'seq': seq, 'pid': 41,
            'create_time': 900, 'requested_policy_digest': DIGEST, 'applied': [],
            'observed': {}, 'owned': []}
    base.update(over)
    return base


def no_pid(pid):
    pytest.fail('process queried')


def no_resource(execution_id, owner):
    pytest.fail('resource queried')


def restart(data):
    return ledger.reconcile({'e1': data}, no_pid, no_resource)


# --- denial paths: the ledger must refuse, not merely notice -------------------

@pytest.mark.parametrize('op', ['ownership', 'disposal', 'completion', 'quarantine'], ids=str)
def test_append_fresh_requires_intent(journal, op):
    # mxc_ledger.py:159 `if op != 'intent': raise ValueError('intent required')` —
    # without it a journal could be born at any later boundary.
    with pytest.raises(ValueError, match='intent required'):
        journal.append('e1', op)
    assert os.listdir(journal.root) == []


def test_init_file_is_owner_only(journal, monkeypatch):
    # mxc_ledger.py:161 `config.write_atomic(path, '', mode=0o600)` — weakened mode
    # or a dropped mode argument exposes the journal; asserted through the seam.
    seen = []
    real_open = open

    def fake_write_atomic(path, content, mode=None):
        seen.append((path, content, mode))
        with real_open(path, 'wb') as stream:
            stream.write(b'')
        return True

    monkeypatch.setattr(ledger.config, 'write_atomic', fake_write_atomic)
    journal.append('e1', 'intent', requested_policy_digest=DIGEST, planned=[],
                   applied=[], observed={})
    assert seen == [(journal._path('e1'), '', 0o600)]
    rows, invalid = ledger.read_records(journal.journals()['e1'], 'e1')
    assert not invalid and [r['op'] for r in rows] == ['intent']


@pytest.mark.parametrize('op', ['advance', 'Intent', 'create', ''], ids=str)
def test_append_rejects_unknown_op(journal, op):
    # mxc_ledger.py:174 `if not allowed.get(op, False)` — an unknown op must never
    # be written; inverting the .get default to True would let it through.
    with open(journal._path('e1'), 'wb') as stream:
        stream.write(b'')
    with pytest.raises(ValueError, match='invalid ledger transition'):
        journal.append('e1', op, reason='x')
    assert journal.journals()['e1'] == b''


def test_append_rejects_any_boundary_after_completion(journal):
    # mxc_ledger.py:170-175 transition table — a finished journal is closed to new
    # rounds; loosening any entry (e.g. `'completion': 'completion' in ops`) reopens it.
    create(journal)
    journal.dispose('e1', lambda owner: None, lambda owner: True)
    journal.complete('e1', 0)
    before = journal.journals()['e1']
    for op in ['intent', 'ownership', 'disposal', 'completion']:
        with pytest.raises(ValueError, match='invalid ledger transition'):
            journal.append('e1', op)
    assert journal.journals()['e1'] == before


def test_quarantine_after_completion_never_resurrects(journal):
    # mxc_ledger.py:102 (`'quarantine' in ops` -> pass) and :106-108 (completed
    # journals get NO verdict) — doubt recorded after a clean disposal must keep the
    # execution DEAD_UNVERIFIED; a completed journal must not appear at all.
    create(journal)
    journal.dispose('e1', lambda owner: None, lambda owner: True)
    journal.complete('e1', 0)
    clean = journal.journals()['e1']
    assert ledger.reconcile({'e1': clean}, no_pid, no_resource) == {}
    journal.append('e1', 'quarantine', reason='manual doubt')
    poisoned = journal.journals()['e1']
    assert ledger.reconcile({'e1': poisoned}, no_pid, no_resource) == {
        'e1': ledger.DEAD_UNVERIFIED}


def test_append_rejects_non_finite_floats(journal):
    # mxc_ledger.py:15-17 `allow_nan=False` — NaN/Infinity have no JSON round trip
    # (read_records would poison the journal forever); the write must die at once.
    for value in (float('nan'), float('inf'), float('-inf')):
        with pytest.raises(ValueError):
            journal.append('e1', 'intent', requested_policy_digest=DIGEST,
                           planned=[value], applied=[], observed={})
        assert journal.journals()['e1'] == b''


@pytest.mark.parametrize('change', [
    {'pid': 0}, {'pid': -7}, {'pid': True},
    {'create_time': 0}, {'create_time': -2}, {'create_time': None}], ids=str)
def test_create_refuses_hostile_child(journal, change):
    # mxc_ledger.py:197-201 — native create already happened; an unrecordable child
    # must NEVER be advanced. Inverting _validate's identity checks would advance it.
    calls = []
    child = SimpleNamespace(**dict({'pid': 41, 'create_time': 900}, **change))
    with pytest.raises(ValueError, match='invalid ownership'):
        journal.create('e1', {'request': 'only'},
                       lambda: (child, dict(FULL_FACTS)), calls.append)
    assert calls == []
    rows, invalid = ledger.read_records(journal.journals()['e1'], 'e1')
    assert not invalid and [r['op'] for r in rows] == ['intent']


@pytest.mark.parametrize('change', [{'applied': 'grant'}, {'observed': []},
                                    {'owned': 'resource-7'}], ids=str)
def test_create_refuses_unrecordable_facts(journal, change):
    # mxc_ledger.py:42-44 (container types) via 198-200 — facts the checksum could
    # not pin down must abort create before the child is handed to advance().
    calls = []
    facts = dict(FULL_FACTS, **change)
    with pytest.raises(ValueError, match='invalid ownership'):
        journal.create('e1', {'request': 'only'},
                       lambda: (SimpleNamespace(pid=41, create_time=900), facts), calls.append)
    assert calls == []
    rows, invalid = ledger.read_records(journal.journals()['e1'], 'e1')
    assert not invalid and [r['op'] for r in rows] == ['intent']


@pytest.mark.parametrize('change', [
    {'pid': 0}, {'pid': -7}, {'create_time': 0}, {'create_time': -3},
    {'pid': 41, 'create_time': True}], ids=str)
def test_hostile_launcher_identity_is_never_polled(journal, change):
    # mxc_ledger.py:39-40 (_validate) and 114-115 (`invalid launcher identity`) —
    # deleting both checks would hand pid 0/negative to the live process table.
    journal.append('e1', 'intent', requested_policy_digest=DIGEST, planned=[],
                   applied=[], observed={})
    intent_row, _ = ledger.read_records(journal.journals()['e1'], 'e1')
    prev = hashlib.sha256(ledger._line(intent_row[0])).hexdigest()
    with open(journal._path('e1'), 'ab') as stream:
        stream.write(ledger._line(dict(owner(1, **change), version=ledger.FORMAT_VERSION,
                                       prev=prev)))
    assert journal.reconcile(no_pid, no_resource) == {'e1': ledger.DEAD_UNVERIFIED}
    rows, _ = ledger.read_records(journal.journals()['e1'], 'e1')
    assert rows[-1]['op'] == 'quarantine' and rows[-1]['reason'] == 'restart_unverified'


@pytest.mark.parametrize('which', ['second', 'quarantined', 'corrupt', 'intent-only',
                                   'empty'], ids=str)
def test_dispose_refuses_dirty_journals(journal, which):
    # mxc_ledger.py:206-207 `!= ['intent', 'ownership']` — dispose/absent touch the
    # real OS; calling them on a disposed, quarantined, corrupt or partial journal
    # is the worst possible failure. They must not run once.
    if which == 'second':
        create(journal)
        journal.dispose('e1', lambda owner: None, lambda owner: True)
    elif which == 'quarantined':
        create(journal)
        journal.append('e1', 'quarantine', reason='halt')
    elif which == 'corrupt':
        create(journal)
        with open(journal._path('e1'), 'ab') as stream:
            stream.write(b'garbage\n')
    elif which == 'intent-only':
        journal.append('e1', 'intent', requested_policy_digest=DIGEST, planned=[],
                       applied=[], observed={})
    else:
        with open(journal._path('e1'), 'wb') as stream:
            stream.write(b'')
    with pytest.raises(ValueError, match='verified ownership required'):
        journal.dispose('e1', no_resource, no_resource)


@pytest.mark.parametrize('failure', ['dispose', 'unverified', 'absent-none', 'absent-truthy'],
                         ids=str)
def test_dispose_failure_quarantines_with_reason(journal, failure):
    # mxc_ledger.py:211-215 — anything between touching the OS and the disposal
    # record must leave reason='disposal_unverified', the operator's only clue.
    # `is not True` (not truthiness): 1/'yes' are not proof of absence.
    create(journal)

    def dispose(owner):
        if failure == 'dispose':
            raise OSError('dispose failed')

    def absent(owner):
        if failure == 'unverified':
            return False
        if failure == 'absent-none':
            return None
        if failure == 'absent-truthy':
            return 'yes'
        return True

    with pytest.raises((OSError, ValueError)):
        journal.dispose('e1', dispose, absent)
    rows, _ = ledger.read_records(journal.journals()['e1'], 'e1')
    assert rows[-1]['op'] == 'quarantine' and rows[-1]['reason'] == 'disposal_unverified'


# --- boundary values -----------------------------------------------------------

@pytest.mark.parametrize('which', ['own-true', 'own-false', 'intent-true', 'intent-false'],
                         ids=str)
def test_bool_seq_is_rejected(which):
    # mxc_ledger.py:30 `type(record['seq']) is not int` (not isinstance) and :81 —
    # bool passes `== len(records)`; only the strict type check keeps True/False out.
    if which.startswith('own'):
        data = ledger._line(intent(0)) + ledger._line(owner(seq=(which == 'own-true')))
    else:
        data = ledger._line(intent(seq=(which == 'intent-true')))
    _, invalid = ledger.read_records(data, 'e1')
    assert invalid
    assert restart(data)['e1'] == ledger.DEAD_UNVERIFIED


@pytest.mark.parametrize('change', [{'applied': 'grant'}, {'applied': 7}, {'applied': {}},
                                    {'observed': []}, {'observed': 'x'}, {'observed': 3},
                                    {'owned': 'resource-7'}, {'owned': {}}, {'owned': 7}],
                         ids=str)
def test_ownership_container_facts_must_be_containers(change):
    # mxc_ledger.py:42-44 — after the JSON round trip a tuple is a list, so these
    # isinstance checks only fire on str/int/dict; each must poison the journal.
    data = ledger._line(intent(0)) + ledger._line(owner(1, **change))
    rows, invalid = ledger.read_records(data, 'e1')
    assert invalid
    assert rows == [intent()]
    assert restart(data)['e1'] == ledger.DEAD_UNVERIFIED


@pytest.mark.parametrize('bad', ['..', '.', 'a/b', 'a\\b', 'e1.jsonl', 'e1 ', 'e\n1',
                                 '\u00e9', 'e1;', b'e1', 42], ids=str)
def test_path_rejects_more_hostile_ids(tmp_path, bad):
    # mxc_ledger.py:139 `re.fullmatch(r'[A-Za-z0-9_-]+', ...)` plus the isinstance
    # guard — fullmatch (not match/search) is what blocks 'e1 ' and separators.
    journal = ledger.Ledger(tmp_path / 'ids')
    with pytest.raises(ValueError, match='invalid execution ID'):
        journal._path(bad)


def test_unicode_facts_stay_pure_ascii(journal):
    # mxc_ledger.py:15-17 `ensure_ascii=True ... .encode('ascii')` — dropping either
    # changes byte framing (length/sha256) or raises; frames are ascii by contract.
    reason = '\u00fcni\u00e7ode \u2713 \u4e2d\u6587'
    journal.append('e1', 'intent', requested_policy_digest=DIGEST, planned=['\u00fc'],
                   applied=[], observed={})
    journal.append('e1', 'quarantine', reason=reason)
    data = journal.journals()['e1']
    assert max(data) < 128
    rows, invalid = ledger.read_records(data, 'e1')
    assert not invalid
    assert rows[1]['reason'] == reason and rows[0]['planned'] == ['\u00fc']


@pytest.mark.skipif(sys.platform == 'win32',
                    reason='directory fsync after create is POSIX-only (os.name != nt)')
def test_first_append_fsyncs_the_directory(journal, monkeypatch):
    # mxc_ledger.py:185-190 — the intent must be durable (entry included) BEFORE the
    # native create of create(); deleting the dir fsync loses intents to a crash.
    synced = []
    real_fsync = os.fsync

    def spy(fd):
        real_fsync(fd)
        synced.append(fd)

    monkeypatch.setattr(ledger.os, 'fsync', spy)
    journal.append('e1', 'intent', requested_policy_digest=DIGEST, planned=[],
                   applied=[], observed={})
    assert len(synced) == 2
    synced.clear()
    journal.append('e1', 'quarantine', reason='halt')
    assert len(synced) == 1


# --- error paths ----------------------------------------------------------------

def test_unreadable_journal_becomes_invalid_marker(journal):
    # mxc_ledger.py:148-152 — an unreadable journal must become b'invalid\n', not
    # vanish: a missing key in journals() silently skips reconciliation entirely.
    journal.append('e1', 'intent', requested_policy_digest=DIGEST, planned=[],
                   applied=[], observed={})
    os.makedirs(os.path.join(journal.root, 'bad.jsonl'))
    journals = journal.journals()
    assert journals['bad'] == b'invalid\n'
    assert ledger.reconcile(journals, no_pid, no_resource) == {
        'e1': ledger.DEAD_UNVERIFIED, 'bad': ledger.DEAD_UNVERIFIED}


def test_validate_rejects_unknown_op():
    # mxc_ledger.py:26-59 — no elif arm and no op-membership check, so an unknown op
    # with bare fields returns quietly. Public paths guard it (read_records:79,
    # append:174), but _validate itself must fail closed for any future caller.
    with pytest.raises(ValueError, match='unknown op'):
        ledger._validate({'execution_id': 'e1', 'op': 'advance', 'seq': 0}, [])


def test_complete_rejects_bool_outcome(journal):
    # mxc_ledger.py:52 `type(record['outcome']) is not int` — bool == int would pass
    # an isinstance check; True is not an exit code. Journal bytes must not move.
    create(journal)
    journal.dispose('e1', lambda owner: None, lambda owner: True)
    before = journal.journals()['e1']
    with pytest.raises(ValueError, match='invalid completion'):
        journal.complete('e1', True)
    assert journal.journals()['e1'] == before


def test_digest_is_canonical_policy_hash(journal, monkeypatch):
    # mxc_ledger.py:194 `sha256(_json(requested_policy))` — the digest must bind the
    # exact canonical (sorted-keys, tight-separator) encoding of the policy, since
    # ownership:41 later refuses any record whose digest differs from the intent's.
    seen = []
    real_sha = hashlib.sha256

    def spy(data):
        seen.append(data)
        return real_sha(data)

    monkeypatch.setattr(ledger.hashlib, 'sha256', spy)
    policy = {'b': 1, 'a': [2, {'d': 3, 'c': None}]}
    journal.create('e1', policy,
                   lambda: (SimpleNamespace(pid=41, create_time=900), dict(FULL_FACTS)),
                   lambda child: None)
    canonical = ledger._json(policy)
    assert canonical == b'{"a":[2,{"c":null,"d":3}],"b":1}'
    assert seen[0] == canonical
    rows, _ = ledger.read_records(journal.journals()['e1'], 'e1')
    assert rows[0]['requested_policy_digest'] == real_sha(canonical).hexdigest()
