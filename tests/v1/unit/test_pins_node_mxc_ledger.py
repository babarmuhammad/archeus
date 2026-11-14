import os
import types

import pytest

from archeus.node import mxc_ledger as ledger

DIGEST = 'a' * 64


def intent(seq=0, **over):
    row = {'execution_id': 'e1', 'op': 'intent', 'seq': seq,
           'requested_policy_digest': DIGEST, 'planned': [], 'applied': [], 'observed': {}}
    row.update(over)
    return row


def owner(seq=1, **over):
    row = {'execution_id': 'e1', 'op': 'ownership', 'seq': seq, 'pid': 41,
           'create_time': 900, 'requested_policy_digest': DIGEST, 'applied': [],
           'observed': {}, 'owned': []}
    row.update(over)
    return row


def disposal(seq=2, **over):
    row = {'execution_id': 'e1', 'op': 'disposal', 'seq': seq, 'verified_absent': True}
    row.update(over)
    return row


def completion(seq=3, **over):
    row = {'execution_id': 'e1', 'op': 'completion', 'seq': seq, 'outcome': 0}
    row.update(over)
    return row


def q(op, seq=0, **over):
    row = {'execution_id': 'e1', 'op': op, 'seq': seq}
    row.update(over)
    return row


def lines(*rows):
    return b''.join(ledger._line(row) for row in rows)


def invalid(*rows):
    _, broken = ledger.read_records(lines(*rows), 'e1')
    return broken


@pytest.fixture
def journal(tmp_path):
    return ledger.Ledger(tmp_path / 'ledger')


def with_intent(journal):
    journal.append('e1', 'intent', requested_policy_digest=DIGEST, planned=[], applied=[],
                   observed={})
    return journal


def with_owner(journal):
    with_intent(journal)
    journal.append('e1', 'ownership', pid=41, create_time=900,
                   requested_policy_digest=DIGEST, applied=[], observed={}, owned=[])
    return journal


def ops_of(journal):
    rows, _ = ledger.read_records(journal.journals()['e1'], 'e1')
    return [row['op'] for row in rows]


def test_a_clean_journal_reads_clean():
    assert invalid(intent()) is False
    assert invalid(intent(), owner(1)) is False
    assert invalid(intent(), owner(1), disposal(2)) is False
    assert invalid(intent(), owner(1), disposal(2), completion(3)) is False
    assert invalid(q('quarantine', 0, reason='halt')) is False


def test_frame_of_equivalent_records_is_identical():
    left = intent(0, planned=['g1', 'g2'])
    right = {'observed': {}, 'applied': [], 'planned': ['g1', 'g2'], 'seq': 0,
             'requested_policy_digest': DIGEST, 'op': 'intent', 'execution_id': 'e1'}
    assert ledger._line(left) == ledger._line(right)


@pytest.mark.parametrize('bad', [float('nan'), float('inf')], ids=['nan', 'inf'])
def test_non_finite_fact_is_never_written(tmp_path, bad):
    journal = ledger.Ledger(tmp_path / 'ledger')
    with pytest.raises(ValueError, match='not JSON compliant'):
        journal.append('e1', 'intent', requested_policy_digest=DIGEST, planned=[bad],
                       applied=[], observed={})
    assert journal.journals() == {'e1': b''}


def test_sequence_must_be_a_plain_int():
    with pytest.raises(ValueError, match='invalid sequence'):
        ledger._validate({'execution_id': 'e1', 'op': 'quarantine', 'seq': True,
                          'reason': 'halt'}, [])


def test_intent_must_come_first():
    assert invalid(q('quarantine', 0, reason='halt'), intent(1)) is True
    assert invalid(intent(), owner(1), intent(2)) is True


def test_ownership_needs_only_an_intent_before_it():
    assert invalid(intent(), owner(1), owner(2)) is True
    assert invalid(intent(), q('quarantine', 1, reason='halt'), owner(2)) is True


@pytest.mark.parametrize('bad', [('pid', 0), ('pid', True), ('pid', 41.0), ('pid', '41'),
                                 ('create_time', 0), ('create_time', True),
                                 ('create_time', 900.0), ('create_time', '900')],
                         ids=['pid0', 'pidbool', 'pidfloat', 'pidstr',
                              'time0', 'timebool', 'timefloat', 'timestr'])
def test_launcher_identity_is_strict(bad):
    key, value = bad
    assert invalid(intent(), owner(1, **{key: value})) is True


@pytest.mark.parametrize('bad', [('applied', 'g1'), ('applied', {'g': 1}), ('applied', None),
                                 ('observed', 'obs'), ('observed', []),
                                 ('owned', 'r1'), ('owned', {'r': 1}), ('owned', None)],
                         ids=['astr', 'adict', 'anone', 'oestr', 'olist',
                              'wstr', 'wdict', 'wnone'])
def test_ownership_fact_containers_are_strict(bad):
    key, value = bad
    assert invalid(intent(), owner(1, **{key: value})) is True


def test_disposal_needs_intent_and_ownership():
    assert invalid(disposal(0)) is True
    assert invalid(intent(), disposal(1)) is True
    assert invalid(intent(), owner(1), disposal(2), disposal(3)) is True


@pytest.mark.parametrize('bad', [1, 'true'], ids=['one', 'str'])
def test_disposal_requires_the_true_constant(bad):
    assert invalid(intent(), owner(1), disposal(2, verified_absent=bad)) is True


def test_completion_needs_the_full_history():
    assert invalid(completion(0)) is True
    assert invalid(intent(), completion(1)) is True
    assert invalid(intent(), owner(1), completion(2)) is True
    assert invalid(intent(), owner(1), disposal(2), completion(3), completion(4)) is True


@pytest.mark.parametrize('bad', [True, '0', None, 0.0], ids=['bool', 'str', 'none', 'float'])
def test_completion_outcome_must_be_a_plain_int(bad):
    assert invalid(intent(), owner(1), disposal(2), completion(3, outcome=bad)) is True


@pytest.mark.parametrize('bad', ['', None, 42, ['x']], ids=['empty', 'none', 'int', 'list'])
def test_quarantine_reason_must_be_a_real_string(bad):
    assert invalid(q('quarantine', 0, reason=bad)) is True


@pytest.mark.parametrize('bad', ['a' * 63, 'A' * 64, 'z' * 64, 'a' * 64 + 'z',
                                 'a' * 64 + '\n', 42, ['a' * 64]],
                         ids=['short', 'upper', 'nonhex', 'tail', 'newline', 'int', 'list'])
def test_requested_policy_digest_shape(bad):
    assert invalid(intent(0, requested_policy_digest=bad)) is True
    assert invalid(intent(), owner(1, requested_policy_digest=bad)) is True


def test_ownership_digest_is_bound_to_the_intent():
    assert invalid(intent(), owner(1, requested_policy_digest='b' * 64)) is True


@pytest.mark.parametrize('op', ['advance', 'Intent', 'intent ', ''],
                         ids=['advance', 'upper', 'space', 'empty'])
def test_unknown_op_never_parses(op):
    assert invalid(q(op)) is True


def test_sequence_must_be_contiguous():
    assert invalid(intent(1)) is True
    assert invalid(intent(), owner(2)) is True
    assert invalid(intent(), owner(1), disposal(3)) is True
    assert invalid(intent(), owner(1), disposal(2), completion(4)) is True


def test_quarantine_stops_every_reader():
    calls = []

    def process(pid):
        calls.append(('pid', pid))
        return 900

    def resources(execution_id, row):
        calls.append(('resources', execution_id))
        return True

    data = lines(intent(), owner(1), q('quarantine', 2, reason='halt'))
    assert ledger.reconcile({'e1': data}, process, resources) == {'e1': ledger.DEAD_UNVERIFIED}
    assert calls == []


def test_completed_journal_touches_no_reader():
    calls = []

    def process(pid):
        calls.append(('pid', pid))
        return 900

    def resources(execution_id, row):
        calls.append(('resources', execution_id))
        return True

    data = lines(intent(), owner(1), disposal(2), completion(3))
    assert ledger.reconcile({'e1': data}, process, resources) == {}
    assert calls == []


def test_resource_reader_sees_the_returned_ownership():
    calls = []

    def resources(execution_id, row):
        calls.append((execution_id, row['op'], 'planned' in row, sorted(row)))
        return True

    assert ledger.reconcile({'e1': lines(intent(), owner(1))},
                            lambda pid: None, resources) == {'e1': ledger.DEAD_CLEAN}
    assert calls == [('e1', 'ownership', False, sorted(owner()))]


@pytest.mark.parametrize('op', ['ownership', 'disposal', 'completion', 'quarantine'],
                         ids=str)
def test_fresh_journal_refuses_anything_but_intent(journal, op):
    facts = {'ownership': {'pid': 41, 'create_time': 900, 'requested_policy_digest': DIGEST,
                           'applied': [], 'observed': {}, 'owned': []},
             'disposal': {'verified_absent': True},
             'completion': {'outcome': 0},
             'quarantine': {'reason': 'halt'}}[op]
    with pytest.raises(ValueError, match='intent required'):
        journal.append('e1', op, **facts)
    assert journal.journals() == {}


def test_journal_is_created_private(tmp_path, monkeypatch):
    real = ledger.config.write_atomic
    seen = []

    def fake(path, text, **kwargs):
        if not str(path).endswith('.anchor'):
            seen.append((os.path.basename(str(path)), text, kwargs.get('mode')))
        return real(path, text, **kwargs)

    monkeypatch.setattr(ledger.config, 'write_atomic', fake)
    journal = ledger.Ledger(tmp_path / 'ledger')
    journal.append('e1', 'intent', requested_policy_digest=DIGEST, planned=[], applied=[],
                   observed={})
    assert seen == [('e1.jsonl', '', 0o600)]


def test_uncreated_journal_is_not_used(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger.config, 'write_atomic', lambda *args, **kwargs: False)
    journal = ledger.Ledger(tmp_path / 'ledger')
    with pytest.raises(OSError, match='initialization failed'):
        journal.append('e1', 'intent', requested_policy_digest=DIGEST, planned=[], applied=[],
                       observed={})
    assert journal.journals() == {}


def test_intent_is_written_once(journal):
    with_intent(journal)
    with pytest.raises(ValueError, match='invalid ledger transition'):
        journal.append('e1', 'intent', requested_policy_digest=DIGEST, planned=[], applied=[],
                       observed={})
    assert ops_of(journal) == ['intent']


def test_append_rejects_an_unknown_op(journal):
    with_intent(journal)
    with pytest.raises(ValueError, match='invalid ledger transition'):
        journal.append('e1', 'advance')
    assert ops_of(journal) == ['intent']


@pytest.mark.parametrize('stage', ['empty', 'intent', 'disposed', 'quarantined'], ids=str)
def test_dispose_refuses_a_journal_it_cannot_verify(journal, stage):
    rows = {'empty': [], 'intent': [intent()],
            'disposed': [intent(), owner(1), disposal(2)],
            'quarantined': [intent(), owner(1), q('quarantine', 2, reason='halt')]}[stage]
    with open(journal._path('e1'), 'wb') as stream:
        stream.write(lines(*rows))
    calls = []
    with pytest.raises(ValueError, match='verified ownership required'):
        journal.dispose('e1', lambda row: calls.append('dispose'),
                        lambda row: calls.append('readback') or True)
    assert calls == []


def test_dispose_writes_disposal_when_the_readback_verifies(journal):
    with_owner(journal)
    calls = []
    journal.dispose('e1', lambda row: calls.append(('dispose', row['pid'])),
                    lambda row: calls.append('readback') or True)
    assert calls == [('dispose', 41), 'readback']
    assert ops_of(journal) == ['intent', 'ownership', 'disposal']


@pytest.mark.parametrize('verdict', [1, 'yes', None, 0], ids=['one', 'str', 'none', 'zero'])
def test_disposal_readback_must_be_the_true_constant(journal, verdict):
    with_owner(journal)
    with pytest.raises(ValueError, match='disposal unverified'):
        journal.dispose('e1', lambda row: None, lambda row: verdict)
    assert ops_of(journal) == ['intent', 'ownership', 'quarantine']


@pytest.mark.parametrize('osname,wanted', [('posix', True), ('nt', False)],
                         ids=['posix', 'nt'])
def test_directory_fsync_matches_platform(tmp_path, monkeypatch, osname, wanted):
    events = []

    def sync(fd):
        events.append(fd)

    def open_dir(path, flags):
        events.append(('dir', os.path.basename(str(path))))
        return 'dirfd'

    def close(fd):
        events.append(('close', fd))

    # a copy of os for the ledger alone: patching os.name itself breaks pathlib and pytest
    fake_os = types.SimpleNamespace(**{k: getattr(os, k) for k in dir(os)})
    fake_os.fsync, fake_os.open, fake_os.close, fake_os.name = sync, open_dir, close, osname
    monkeypatch.setattr(ledger, 'os', fake_os)
    ledger.Ledger(tmp_path / 'ledger').append('e1', 'intent', requested_policy_digest=DIGEST,
                                              planned=[], applied=[], observed={})
    assert events and isinstance(events[0], int)
    opened = ('dir', 'ledger') in events
    assert (opened and 'dirfd' in events) is wanted


@pytest.mark.parametrize('good', ['e1', 'exec-7_A', 'A', '0'], ids=str)
def test_path_accepts_the_documented_charset(tmp_path, good):
    journal = ledger.Ledger(tmp_path / 'ids')
    assert journal._path(good).endswith(good + '.jsonl')


@pytest.mark.parametrize('bad', ['e1 1', 'e1\n', '../evil', '.', 'e1.jsonl', '', 42],
                         ids=['space', 'newline', 'dots', 'dot', 'suffix', 'empty', 'int'])
def test_path_refuses_hostile_ids(tmp_path, bad):
    journal = ledger.Ledger(tmp_path / 'ids')
    with pytest.raises(ValueError, match='invalid execution ID'):
        journal._path(bad)


def test_a_non_quarantine_append_may_not_repair_a_torn_line(journal):
    with_owner(journal)
    data = ledger._line(owner(1))
    with open(journal._path('e1'), 'wb') as stream:
        stream.write(lines(intent()) + data[:-1])
    with pytest.raises(ValueError, match='corrupt ledger requires quarantine'):
        journal.append('e1', 'disposal', verified_absent=True)
    assert journal.journals()['e1'] == lines(intent()) + data[:-1]


def test_journals_reads_only_exact_journal_files(journal):
    with_intent(journal)
    for name in ('notes.jsonl.old', 'e1.jsonl2', 'xjsonl'):
        with open(os.path.join(journal.root, name), 'wb') as stream:
            stream.write(b'{}\n')
    assert set(journal.journals()) == {'e1'}


def test_unreadable_journal_is_reported_as_invalid(tmp_path, monkeypatch):
    journal = with_intent(ledger.Ledger(tmp_path / 'ledger'))
    real_open = open

    def denied(path, mode='r', *args, **kwargs):
        if mode == 'rb':
            raise OSError('read denied')
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(ledger, 'open', denied, raising=False)
    assert journal.journals() == {'e1': b'invalid\n'}
    assert ledger.reconcile(journal.journals(), lambda pid: 900,
                            lambda execution_id, row: True) == {'e1': ledger.DEAD_UNVERIFIED}
