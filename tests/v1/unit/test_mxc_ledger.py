from types import SimpleNamespace

import pytest

from archeus.node import mxc_ledger as ledger


@pytest.fixture
def journal(tmp_path):
    return ledger.Ledger(tmp_path / 'ledger')


def create(journal, advance=lambda child: None):
    return journal.create('e1', {'request': 'only'},
                          lambda: (SimpleNamespace(pid=41, create_time=900),
                                   {'applied': [], 'observed': {}, 'owned': []}), advance,
                          planned=['requested-grant'])


def records(journal):
    result, invalid = ledger.read_records(journal.journals()['e1'], 'e1')
    assert not invalid
    return result


def test_before_intent(journal):
    assert journal.reconcile(lambda pid: None, lambda eid, owner: True) == {}


def test_intent_before_create(journal):
    def native_create():
        assert records(journal)[0]['op'] == 'intent'
        raise RuntimeError('lost reply')

    with pytest.raises(RuntimeError, match='lost reply'):
        journal.create('e1', {}, native_create, lambda child: pytest.fail('advanced'))
    assert journal.reconcile(lambda pid: None, lambda eid, owner: True) == {
        'e1': ledger.DEAD_UNVERIFIED}


def test_crash_after_intent(journal):
    journal.append('e1', 'intent', requested_policy_digest='a' * 64,
                   planned=[], applied=[], observed={})
    calls = []
    assert journal.reconcile(lambda pid: calls.append(pid),
                             lambda *args: calls.append(args)) == {
                                 'e1': ledger.DEAD_UNVERIFIED}
    assert calls == []


def test_lost_create_reply(journal):
    created = []

    def native_create():
        created.append(SimpleNamespace(pid=41, create_time=900))
        raise OSError('reply lost after create')

    with pytest.raises(OSError):
        journal.create('e1', {}, native_create, lambda child: pytest.fail('advanced'))
    assert created
    assert records(journal)[-1]['op'] == 'intent'
    assert journal.reconcile(lambda pid: 900, lambda *args: True)['e1'] == ledger.DEAD_UNVERIFIED


def test_flush_before_advance(journal, monkeypatch):
    synced = []
    monkeypatch.setattr(ledger.os, 'fsync', lambda fd: synced.append(fd))

    def advance(child):
        assert len(synced) >= 2
        owner = records(journal)[-1]
        assert owner['op'] == 'ownership'
        assert (owner['pid'], owner['create_time']) == (41, 900)
        assert owner['requested_policy_digest'] == records(journal)[0]['requested_policy_digest']
        assert owner['observed'] == {}
        assert owner['applied'] == []
        assert records(journal)[0]['planned'] == ['requested-grant']
        raise RuntimeError('crash after ownership')

    with pytest.raises(RuntimeError, match='crash after ownership'):
        create(journal, advance)
    assert journal.reconcile(lambda pid: 900, lambda *args: False)['e1'] == ledger.STILL_RUNNING


@pytest.mark.parametrize('boundary', ['intent', 'ownership'])
def test_write_failure_blocks_next_boundary(journal, monkeypatch, boundary):
    original = journal.append
    calls = []

    def append(execution_id, op, **facts):
        if op == boundary:
            raise OSError('disk failed')
        return original(execution_id, op, **facts)

    monkeypatch.setattr(journal, 'append', append)

    def native_create():
        calls.append('create')
        return SimpleNamespace(pid=41, create_time=900), {
            'applied': [], 'observed': {}, 'owned': []}

    with pytest.raises(OSError):
        journal.create('e1', {}, native_create, lambda child: calls.append('advance'))
    assert calls == ([] if boundary == 'intent' else ['create'])


@pytest.mark.parametrize('current,absent,expected', [
    (None, True, ledger.DEAD_CLEAN),
    (None, False, ledger.DEAD_UNVERIFIED),
    (None, None, ledger.DEAD_UNVERIFIED),
    (900, False, ledger.STILL_RUNNING),
    (901, True, ledger.UNKNOWN_OWNER),
    (True, True, ledger.DEAD_UNVERIFIED),
])
def test_restart_states(journal, current, absent, expected):
    create(journal)
    calls = []

    def resources(execution_id, owner):
        calls.append(execution_id)
        assert 'planned' not in owner
        return absent

    assert journal.reconcile(lambda pid: current, resources)['e1'] == expected
    assert calls == (['e1'] if current is None else [])


def test_never_terminate_unknown(journal):
    create(journal)

    class ProcessTable:
        def __call__(self, pid):
            assert pid == 41
            return 901

        def terminate(self, pid):
            pytest.fail('reused PID terminated')

    assert journal.reconcile(ProcessTable(), lambda *args: pytest.fail('resource touched')) == {
        'e1': ledger.UNKNOWN_OWNER}
    assert records(journal)[-1]['op'] == 'ownership'


@pytest.mark.parametrize('which', ['process', 'resource'])
def test_reader_raises(journal, which):
    create(journal)

    def broken(*args):
        raise OSError('reader failed')

    assert journal.reconcile(broken if which == 'process' else lambda pid: None,
                             broken)['e1'] == ledger.DEAD_UNVERIFIED
    assert records(journal)[-1]['op'] == 'quarantine'


def test_quarantine_second_restart(journal):
    create(journal)
    assert journal.reconcile(lambda pid: None, lambda *args: False)['e1'] == ledger.DEAD_UNVERIFIED
    again = ledger.Ledger(journal.root)
    before = again.journals()
    assert again.reconcile(lambda pid: pytest.fail('quarantine re-adopted'),
                           lambda *args: True)['e1'] == ledger.DEAD_UNVERIFIED
    assert again.journals() == before
    assert records(again)[-1]['op'] == 'quarantine'


@pytest.mark.parametrize('damage', ['truncate', 'digest', 'length', 'garbage', 'utf8'])
def test_corrupt_record(journal, damage):
    create(journal)
    path = journal._path('e1')
    data = journal.journals()['e1']
    if damage == 'truncate':
        data = data[:-15]
    elif damage == 'digest':
        data = data.replace(b'"pid":41', b'"pid":42')
    elif damage == 'length':
        data = data.replace(b'"length":', b'"length":1', 1)
    elif damage == 'garbage':
        data += b'{}\n'
    else:
        data += b'\xff\n'
    with open(path, 'wb') as stream:
        stream.write(data)
    assert journal.reconcile(lambda pid: 900, lambda *args: True)['e1'] == ledger.DEAD_UNVERIFIED
    assert ledger.Ledger(journal.root).reconcile(lambda pid: None, lambda *args: True)[
        'e1'] == ledger.DEAD_UNVERIFIED


def test_completion_and_disposal(journal):
    create(journal)
    with pytest.raises(ValueError):
        journal.complete('e1', 0)
    calls = []
    journal.dispose('e1', lambda owner: calls.append('dispose'),
                    lambda owner: calls.append('readback') or True)
    assert calls == ['dispose', 'readback']
    assert records(journal)[-1] == {
        'execution_id': 'e1', 'op': 'disposal', 'seq': 2, 'verified_absent': True}
    assert journal.reconcile(lambda pid: None, lambda *args: True) == {'e1': ledger.DEAD_CLEAN}
    journal.complete('e1', 0)
    assert journal.reconcile(lambda pid: pytest.fail('completed process queried'),
                             lambda *args: pytest.fail('completed resources queried')) == {}
    with pytest.raises(ValueError):
        create(journal)


@pytest.mark.parametrize('failure', ['dispose', 'readback', 'present'])
def test_disposal_uncertainty_quarantines(journal, failure):
    create(journal)

    def dispose(owner):
        if failure == 'dispose':
            raise OSError('dispose failed')

    def absent(owner):
        if failure == 'readback':
            raise OSError('query failed')
        return False

    with pytest.raises((OSError, ValueError)):
        journal.dispose('e1', dispose, absent)
    assert records(journal)[-1]['op'] == 'quarantine'
    with pytest.raises(ValueError):
        journal.complete('e1', 0)


def test_read_failure_is_scoped(journal, monkeypatch):
    create(journal)
    original = ledger.read_records
    assert original(b'[]\nnull\n42\n', 'e1') == ([], True)
    assert ledger.reconcile({'bad': b'broken\n', 'e1': journal.journals()['e1']},
                            lambda pid: 900, lambda *args: True) == {
                                'bad': ledger.DEAD_UNVERIFIED, 'e1': ledger.STILL_RUNNING}

@pytest.mark.parametrize('op', ['intent', 'ownership', 'disposal', 'completion', 'quarantine'])
def test_partial_write_at_each_boundary(journal, op):
    create(journal)
    journal.dispose('e1', lambda owner: None, lambda owner: True)
    journal.complete('e1', 0)
    all_records = records(journal)
    if op == 'quarantine':
        data = b''.join(ledger._line(r) for r in all_records[:2])
        tail = ledger._line({'execution_id': 'e1', 'op': 'quarantine', 'seq': 2,
                             'reason': 'uncertain'})
    else:
        index = ['intent', 'ownership', 'disposal', 'completion'].index(op)
        data = b''.join(ledger._line(r) for r in all_records[:index])
        tail = ledger._line(all_records[index])
    with open(journal._path('e1'), 'wb') as stream:
        stream.write(data + tail[:len(tail) // 2])
    assert journal.reconcile(lambda pid: None, lambda *args: True) == {
        'e1': ledger.DEAD_UNVERIFIED}


@pytest.mark.parametrize('change', ['pid', 'time', 'digest', 'observed', 'completion'])
def test_self_checking_but_malformed_facts(journal, change):
    create(journal)
    rows = records(journal)
    if change == 'pid':
        rows[-1]['pid'] = True
    elif change == 'time':
        rows[-1]['create_time'] = None
    elif change == 'digest':
        rows[-1]['requested_policy_digest'] = 'b' * 64
    elif change == 'observed':
        rows[-1]['observed'] = 'requested policy is effective'
    else:
        rows.append({'execution_id': 'e1', 'op': 'completion', 'seq': 2, 'outcome': 0})
    data = b''.join(ledger._line(row) for row in rows)
    assert ledger.reconcile({'e1': data}, lambda pid: None, lambda *args: True) == {
        'e1': ledger.DEAD_UNVERIFIED}


def test_append_preserves_previous_bytes(journal):
    create(journal)
    before = journal.journals()['e1']
    journal.dispose('e1', lambda owner: None, lambda owner: True)
    assert journal.journals()['e1'].startswith(before)
    before = journal.journals()['e1']
    journal.complete('e1', 3)
    assert journal.journals()['e1'].startswith(before)


def test_fsync_failure_prevents_create(journal, monkeypatch):
    def failed(fd):
        raise OSError('flush failed')

    monkeypatch.setattr(ledger.os, 'fsync', failed)
    with pytest.raises(OSError, match='flush failed'):
        journal.create('e1', {}, lambda: pytest.fail('create before durable intent'),
                       lambda child: pytest.fail('advanced'))


def test_initialization_failure_prevents_create(journal, monkeypatch):
    monkeypatch.setattr(ledger.config, 'write_atomic', lambda *args, **kwargs: False)
    with pytest.raises(OSError, match='initialization failed'):
        journal.create('e1', {}, lambda: pytest.fail('created'), lambda child: None)


def test_observed_facts_kept_distinct(journal):
    facts = {'applied': ['returned-grant'], 'observed': {
        'backend': 'processcontainer', 'grants': ['observed-grant']}, 'owned': ['resource-7']}
    journal.create('e1', {'backend': 'requested'},
                   lambda: (SimpleNamespace(pid=41, create_time=900), facts),
                   lambda child: None, planned=['planned-grant'])
    intent, owner = records(journal)
    assert intent['planned'] == ['planned-grant']
    assert intent['observed'] == {}
    assert owner['applied'] == ['returned-grant']
    assert owner['observed'] == facts['observed']
    assert owner['owned'] == ['resource-7']


def test_unreadable_journal_reports_unverified(journal, monkeypatch):
    create(journal)
    real_open = open

    def denied(path, mode='r', *args, **kwargs):
        if mode == 'rb':
            raise OSError('read denied')
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(ledger, 'open', denied, raising=False)
    assert ledger.reconcile(journal.journals(), lambda pid: 900, lambda *args: True) == {
        'e1': ledger.DEAD_UNVERIFIED}


def test_ownership_fsync_failure_prevents_advance(journal, monkeypatch):
    def sync(fd):
        rows, _ = ledger.read_records(journal.journals()['e1'], 'e1')
        if rows and rows[-1]['op'] == 'ownership':
            raise OSError('ownership flush failed')

    monkeypatch.setattr(ledger.os, 'fsync', sync)
    with pytest.raises(OSError, match='ownership flush failed'):
        create(journal, lambda child: pytest.fail('advanced without durable ownership'))


def test_quarantine_write_failure_is_not_reported_as_persisted(journal, monkeypatch):
    create(journal)
    original = journal.append

    def failed(execution_id, op, **facts):
        if op == 'quarantine':
            raise OSError('quarantine disk failed')
        return original(execution_id, op, **facts)

    monkeypatch.setattr(journal, 'append', failed)
    with pytest.raises(OSError, match='quarantine disk failed'):
        journal.reconcile(lambda pid: None, lambda *args: False)
