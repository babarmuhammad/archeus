import hashlib
from types import SimpleNamespace
from pathlib import Path

import pytest

from archeus.node import mxc_ledger as ledger


DIGEST = 'a' * 64


@pytest.fixture
def journal(tmp_path):
    return ledger.Ledger(tmp_path / 'ledger')


def create(journal):
    return journal.create('e1', {'request': 'only'},
                          lambda: (SimpleNamespace(pid=41, create_time=900),
                                   {'applied': [], 'observed': {}, 'owned': []}),
                          lambda child: None)


def q(what, seq, **over):
    base = {'execution_id': 'e1', 'op': what, 'seq': seq}
    base.update(over)
    return base


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


def disposal(seq=2, **over):
    base = {'execution_id': 'e1', 'op': 'disposal', 'seq': seq, 'verified_absent': True}
    base.update(over)
    return base


def framed(record, length=None, sha=None, add=None, drop=None):
    payload = ledger._json(record)
    frame = {'length': len(payload) if length is None else length,
             'sha256': hashlib.sha256(payload).hexdigest() if sha is None else sha,
             'record': record}
    frame.update(add or {})
    for key in drop or ():
        frame.pop(key, None)
    return ledger._json(frame) + b'\n'


def no_pid(pid):
    pytest.fail('process queried')


def no_resource(execution_id, owner):
    pytest.fail('resource queried')


def restart(data):
    return ledger.reconcile({'e1': data}, no_pid, no_resource)


def test_read_records_rejects_str():
    assert ledger.read_records('{"record":{}}\n', 'e1') == ([], True)
    assert ledger.read_records(None, 'e1') == ([], True)
    assert restart('not bytes')['e1'] == ledger.DEAD_UNVERIFIED


def test_record_needs_trailing_newline():
    whole = ledger._line(intent())
    assert ledger.read_records(whole, 'e1') == ([intent()], False)
    assert ledger.read_records(whole[:-1], 'e1') == ([], True)
    assert restart(whole[:-1])['e1'] == ledger.DEAD_UNVERIFIED


@pytest.mark.parametrize('which', ['extra', 'missing', 'length', 'digest'], ids=str)
def test_envelope_framing(which):
    row = intent()
    if which == 'extra':
        data = framed(row, add={'extra': 1})
    elif which == 'missing':
        data = framed(row, drop=['sha256'])
    elif which == 'length':
        data = framed(row, length=len(ledger._json(row)) + 1)
    else:
        data = framed(row, sha='0' * 64)
    assert ledger.read_records(data, 'e1') == ([], True)
    assert restart(data)['e1'] == ledger.DEAD_UNVERIFIED


def test_foreign_execution_id():
    data = ledger._line(intent(0, execution_id='e2'))
    assert ledger.read_records(data, 'e1') == ([], True)
    assert restart(data)['e1'] == ledger.DEAD_UNVERIFIED


@pytest.mark.parametrize('op', ['advance', 'Intent', ''], ids=str)
def test_unknown_op(op):
    assert restart(ledger._line(intent(0, op=op)))['e1'] == ledger.DEAD_UNVERIFIED


def test_bad_seq_type():
    assert restart(ledger._line(intent(seq='0')))['e1'] == ledger.DEAD_UNVERIFIED
    with pytest.raises(ValueError, match='invalid sequence'):
        ledger._validate({'execution_id': 'e1', 'op': 'quarantine', 'seq': '0',
                          'reason': 'halt'}, [])


@pytest.mark.parametrize('which', ['second-intent', 'late-intent', 'second-owner',
                                   'owner-first'], ids=str)
def test_out_of_order_and_duplicate_ops(which):
    if which == 'second-intent':
        data = ledger._line(intent(0)) + ledger._line(intent(1))
    elif which == 'late-intent':
        data = ledger._line(intent(0)) + ledger._line(q('quarantine', 1, reason='halt')) \
            + ledger._line(intent(2))
    elif which == 'second-owner':
        data = ledger._line(intent(0)) + ledger._line(owner(1)) + ledger._line(owner(2))
    else:
        data = ledger._line(owner(0))
    assert restart(data)['e1'] == ledger.DEAD_UNVERIFIED


@pytest.mark.parametrize('which', ['disposal-early', 'disposal-not-true', 'completion-early',
                                   'completion-bool', 'completion-str'], ids=str)
def test_stage_order_and_facts(which):
    if which == 'disposal-early':
        data = ledger._line(intent(0)) + ledger._line(disposal(1))
    elif which == 'disposal-not-true':
        data = ledger._line(intent(0)) + ledger._line(owner(1)) \
            + ledger._line(q('disposal', 2, verified_absent=1))
    elif which == 'completion-early':
        data = ledger._line(intent(0)) + ledger._line(owner(1)) \
            + ledger._line(q('completion', 2, outcome=0))
    elif which == 'completion-bool':
        data = ledger._line(intent(0)) + ledger._line(owner(1)) + ledger._line(disposal(2)) \
            + ledger._line(q('completion', 3, outcome=True))
    else:
        data = ledger._line(intent(0)) + ledger._line(owner(1)) + ledger._line(disposal(2)) \
            + ledger._line(q('completion', 3, outcome='0'))
    assert restart(data)['e1'] == ledger.DEAD_UNVERIFIED


@pytest.mark.parametrize('which', ['intent-extra', 'intent-applied', 'intent-observed',
                                   'intent-planned-str', 'disposal-missing'], ids=str)
def test_record_field_sets(which):
    if which == 'intent-extra':
        data = ledger._line(dict(intent(), extra=1))
    elif which == 'intent-applied':
        data = ledger._line(intent(0, applied=['returned-grant']))
    elif which == 'intent-observed':
        data = ledger._line(intent(0, observed={'backend': 'x'}))
    elif which == 'intent-planned-str':
        data = ledger._line(intent(0, planned='requested-grant'))
    else:
        data = ledger._line(intent(0)) + ledger._line(owner(1)) \
            + ledger._line(q('disposal', 2))
    rows, invalid = ledger.read_records(data, 'e1')
    assert invalid
    expected = [] if which.startswith('intent') else [intent(), owner(1)]
    assert rows == expected


@pytest.mark.parametrize('reason', ['', 42, None], ids=['empty', 'int', 'null'])
def test_quarantine_reason(reason):
    assert restart(ledger._line(q('quarantine', 0, reason=reason)))['e1'] \
        == ledger.DEAD_UNVERIFIED


@pytest.mark.parametrize('digest', ['a' * 63, 'A' * 64, 'z' * 64, 42],
                         ids=['short', 'upper', 'nonhex', 'int'])
def test_policy_digest_format(digest):
    assert restart(ledger._line(intent(0, requested_policy_digest=digest)))['e1'] \
        == ledger.DEAD_UNVERIFIED


def test_quarantine_alone_blocks_readers():
    data = ledger._line(q('quarantine', 0, reason='halt'))
    assert ledger.read_records(data, 'e1') == ([q('quarantine', 0, reason='halt')], False)
    assert restart(data)['e1'] == ledger.DEAD_UNVERIFIED


def test_quarantine_then_new_records():
    data = ledger._line(intent(0)) + ledger._line(q('quarantine', 1, reason='halt')) \
        + ledger._line(owner(2))
    assert restart(data)['e1'] == ledger.DEAD_UNVERIFIED


def test_bad_line_keeps_valid_prefix():
    data = ledger._line(intent(0)) + b'{"length":1,"sha256":"x","record":{}}\n' \
        + ledger._line(owner(1)) + ledger._line(disposal(2))
    assert ledger.read_records(data, 'e1') == ([intent(), owner(1), disposal(2)], True)
    assert restart(data)['e1'] == ledger.DEAD_UNVERIFIED


def test_non_utf8_bytes():
    data = ledger._line(intent(0)) + b'\xff\xfe\n'
    assert ledger.read_records(data, 'e1') == ([intent()], True)
    assert restart(data)['e1'] == ledger.DEAD_UNVERIFIED


def test_huge_fields_round_trip(journal):
    journal.append('e1', 'intent', requested_policy_digest=DIGEST,
                   planned=['g' * 64] * 4000, applied=[], observed={})
    journal.append('e1', 'quarantine', reason='x' * 200000)
    rows, invalid = ledger.read_records(journal.journals()['e1'], 'e1')
    assert not invalid
    assert rows[0]['planned'] == ['g' * 64] * 4000
    assert rows[1]['reason'] == 'x' * 200000


def test_empty_journal_quarantines(journal):
    with open(journal._path('e1'), 'wb') as stream:
        stream.write(b'')
    assert journal.journals() == {'e1': b''}
    assert journal.reconcile(lambda pid: pytest.fail('polled'),
                             lambda *args: pytest.fail('resource touched')) == {
                                 'e1': ledger.DEAD_UNVERIFIED}
    rows, invalid = ledger.read_records(journal.journals()['e1'], 'e1')
    assert not invalid and [r['op'] for r in rows] == ['quarantine']


def test_only_intent_journal(journal):
    journal.append('e1', 'intent', requested_policy_digest=DIGEST, planned=[], applied=[],
                   observed={})
    assert journal.reconcile(lambda pid: pytest.fail('polled'),
                             lambda *args: pytest.fail('resource touched')) == {
                                 'e1': ledger.DEAD_UNVERIFIED}


@pytest.mark.parametrize('current', [0, -5, '900', 900.5], ids=['zero', 'neg', 'str', 'float'])
def test_process_reader_odd_types(journal, current):
    create(journal)
    assert journal.reconcile(lambda pid: current,
                             lambda *args: pytest.fail('resource touched'))['e1'] \
        == ledger.DEAD_UNVERIFIED


@pytest.mark.parametrize('observed', [1, 'yes', {}, lambda: True],
                         ids=['int', 'str', 'dict', 'callable'])
def test_resource_reader_must_return_true(journal, observed):
    create(journal)
    assert journal.reconcile(lambda pid: None, lambda *args: observed)['e1'] \
        == ledger.DEAD_UNVERIFIED


def test_corrupt_journal_requires_quarantine(journal):
    create(journal)
    data = journal.journals()['e1']
    with open(journal._path('e1'), 'wb') as stream:
        stream.write(data + b'garbage\n')
    with pytest.raises(ValueError, match='corrupt ledger requires quarantine'):
        journal.append('e1', 'disposal', verified_absent=True)
    assert journal.append('e1', 'quarantine', reason='manual')['seq'] == 2
    rows, invalid = ledger.read_records(journal.journals()['e1'], 'e1')
    assert invalid and rows[-1]['op'] == 'quarantine'


def test_quarantine_after_truncated_line(journal):
    create(journal)
    data = journal.journals()['e1']
    tail = ledger._line(owner(1))
    with open(journal._path('e1'), 'wb') as stream:
        stream.write(ledger._line(intent(0)) + tail[:len(tail) // 2])
    journal.append('e1', 'quarantine', reason='manual')
    rows, invalid = ledger.read_records(journal.journals()['e1'], 'e1')
    assert invalid and rows[-1]['op'] == 'quarantine'


def test_quarantine_after_missing_newline_is_readable(journal):
    create(journal)
    data = journal.journals()['e1']
    with open(journal._path('e1'), 'wb') as stream:
        stream.write(data[:-1])
    journal.append('e1', 'quarantine', reason='manual')
    rows, invalid = ledger.read_records(journal.journals()['e1'], 'e1')
    assert not invalid
    assert [r['op'] for r in rows] == ['intent', 'ownership', 'quarantine']


def test_quarantine_blocks_new_records(journal):
    create(journal)
    journal.append('e1', 'quarantine', reason='manual')
    with pytest.raises(ValueError, match='invalid ledger transition'):
        journal.append('e1', 'disposal', verified_absent=True)
    with pytest.raises(ValueError, match='invalid ledger transition'):
        journal.append('e1', 'quarantine', reason='again')


@pytest.mark.parametrize('bad', ['bad id', '../evil', ''], ids=['space', 'path', 'empty'])
def test_path_rejects_hostile_ids(tmp_path, bad):
    journal = ledger.Ledger(tmp_path / 'ids')
    with pytest.raises(ValueError, match='invalid execution ID'):
        journal._path(bad)
    with pytest.raises(ValueError, match='invalid execution ID'):
        journal._path(42)


def test_journals_skips_stray_files(journal):
    create(journal)
    Path(journal.root, 'notes.txt').write_bytes(b'ignore me')
    Path(journal.root, '.jsonl').write_bytes(b'{}\n')
    journals = journal.journals()
    assert set(journals) == {'e1', ''}
    assert journals[''] == b'invalid\n'
    assert ledger.reconcile(journals, lambda pid: 900, lambda *args: True) == {
        'e1': ledger.STILL_RUNNING, '': ledger.DEAD_UNVERIFIED}
