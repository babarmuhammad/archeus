"""P21 slice D (p21-design-gate D2, D8): metrics_daily, `archeus doctor`, core.log rotation."""

import datetime as dt
import hashlib
import json
import logging.handlers
import os

import pytest

from archeus.cli import main as cli
from archeus.core import doctor as doc
from archeus.core import metrics, runtime
from archeus.infra import paths
from archeus.infra.db import Database, connection

DAY = '2026-10-17'
T = DAY + 'T10:00:00.000Z'
META = {'version': 1, 'created_at': T, 'updated_at': T, 'created_by': 'p', 'updated_by': 'p'}


def _put(tx, *, rows):
    for table, cols in rows:
        tx.execute('INSERT INTO %s (%s) VALUES (%s)' % (table, ','.join(cols),
                                                        ','.join('?' * len(cols))),
                   list(cols.values()))


def put(db, *rows):
    db.writer.execute(_put, {'rows': list(rows)})


def mission(mid, state='RUNNING', at=T):
    return 'missions', dict(META, id=mid, workspace_id='wsp', state=state, body='{}',
                            created_at=at)


_SEQ = iter(range(1, 10 ** 6))


def event(etype, kind, sid, to, at=T):
    return 'events', {'id': 'evt%d' % next(_SEQ), 'type': etype, 'at': at, 'actor_kind': 'system',
                      'actor_id': 'p', 'cause_chain': '[]', 'subject_kind': kind,
                      'subject_id': sid, 'workspace_id': 'wsp', 'visibility': 'user',
                      'payload': json.dumps({'to': to})}


def seed_day(db):
    put(db, mission('m1', 'COMPLETED', at=DAY + 'T08:00:00.000Z'),
        mission('m2', 'FAILED'),
        ('plans', dict(META, id='p1', mission_id='m1', plan_version=1, state='APPROVED',
                       body=json.dumps({'estimated_cost': 'low'}))),
        ('tasks', dict(META, id='t1', plan_id='p1', mission_id='m1', key='a', state='DONE',
                       body=json.dumps({'kind': 'code'}))),
        ('context_packages', dict(META, id='c1', workspace_id='wsp', subject_kind='mission',
                                  subject_id='m1', body=json.dumps(
                                      {'budget': {'used_tokens': 1200}}))),
        ('route_decisions', dict(META, id='r1', mission_id='m1', task_id='t1', body=json.dumps(
            {'result': 'selected', 'task_id': 't1', 'context_package_id': 'c1'}))),
        ('route_decisions', dict(META, id='r2', body=json.dumps({'result': 'fallback'}))),
        ('usage_ledger', dict(META, id='u1', route_decision_id='r1',
                              body=json.dumps({'cost_usd': 0.5}))),
        ('approvals', dict(META, id='a1', kind='plan', mission_id='m1', plan_id='p1',
                           action_hash='h', state='APPROVED', expires_at=T, body='{}')),
        event('mission.state_changed', 'mission', 'm1', 'COMPLETED', at=DAY + 'T10:00:00.000Z'),
        event('mission.state_changed', 'mission', 'm2', 'FAILED'),
        event('verification.state_changed', 'verification', 'v1', 'PASSED'),
        event('verification.state_changed', 'verification', 'v2', 'FAILED'),
        event('mission.state_changed', 'mission', 'm3', 'COMPLETED',
              at='2026-10-18T01:00:00.000Z'))


def test_a_finished_day_gets_its_figures_once(db):
    seed_day(db)
    w = metrics.Metrics(db, today=lambda: dt.date(2026, 10, 18))
    assert w.pending() == 1
    assert w.pass_once() == {'changed': True}
    assert w.pass_once() == {'changed': False}          # written once; today never
    with db.read() as r:
        rows = r.execute('SELECT day, metrics FROM metrics_daily').fetchall()
    assert [d for d, _m in rows] == [DAY]
    assert json.loads(rows[0][1]) == {
        'missions_completed': 1, 'missions_failed': 1,
        'median_time_to_complete_s': 7200.0,
        'approvals_per_mission': 0.5,
        'fallback_rate': 0.5,
        'verification_failure_rate': 0.5,
        'cost_per_mission_band': {'low': {'missions': 1, 'cost_usd_mean': 0.5},
                                  'unknown': {'missions': 1, 'cost_usd_mean': None}},
        'context_tokens_per_task_kind': {'code': 1200}}
    db.writer.execute(metrics.record, {'day': DAY, 'metrics': {'other': 1}})
    with db.read() as r:
        assert r.execute('SELECT metrics FROM metrics_daily').fetchone()[0] == rows[0][1]


def test_a_day_with_nothing_to_measure_says_none_not_zero(db):
    put(db, event('session.observed', 'session', 's1', None))
    with db.read() as r:
        figures = metrics.compute(r, DAY)
    assert figures['missions_completed'] == 0
    assert figures['median_time_to_complete_s'] is None
    assert figures['approvals_per_mission'] is None
    assert figures['fallback_rate'] is None
    assert figures['verification_failure_rate'] is None


def test_core_log_rotates(archeus_home):
    core = runtime.Core()
    core._open_log()
    try:
        h = core._log_handler
        assert isinstance(h, logging.handlers.RotatingFileHandler)
        assert (h.maxBytes, h.backupCount) == (runtime.LOG_BYTES, runtime.LOG_BACKUPS)
    finally:
        runtime.log.removeHandler(core._log_handler)
        core._log_handler.close()


def _tree(root):
    out = {}
    for d, _s, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            out[os.path.relpath(p, root)] = hashlib.sha256(open(p, 'rb').read()).hexdigest()
    return out


def test_doctor_without_a_database_creates_nothing(archeus_home, capsys):
    before = _tree(paths.archeus_home())
    assert cli.main(['doctor']) == doc.DOCTOR_DB
    assert _tree(paths.archeus_home()) == before
    assert not os.path.exists(connection.db_path())
    assert 'no database' in capsys.readouterr().out


def test_doctor_on_a_healthy_home_finds_nothing_and_writes_nothing(archeus_home, capsys):
    Database.open().close()
    secrets = ['tok_local_SECRETVALUE', 'hook_SECRETHOOKTOKEN', 'sk-mcp-SECRETKEY']
    run = paths.run_dir()
    os.makedirs(os.path.join(run, 'exec', 'exe1', 'req'), exist_ok=True)
    os.makedirs(os.path.join(run, 'exec', 'exe1', 'res'), exist_ok=True)
    open(os.path.join(run, 'local-token'), 'w').write(secrets[0])
    open(os.path.join(run, 'exec', 'exe1', 'req', '1.req.json'), 'w').write(
        json.dumps({'token': secrets[1]}))
    open(os.path.join(run, 'exec', 'exe1', 'res', 'mcp.json'), 'w').write(
        json.dumps({'env': {'KEY': secrets[2]}}))
    before = _tree(paths.archeus_home())
    assert cli.main(['doctor']) == 0
    out = capsys.readouterr().out
    after = _tree(paths.archeus_home())
    # a mode=ro reader may leave SQLite's own sidecars; the WAL it leaves is empty
    sidecars = {k for k in after if k.endswith(('-wal', '-shm'))} - set(before)
    assert {k: v for k, v in after.items() if k not in sidecars} == before
    assert all(after[k] == hashlib.sha256(b'').hexdigest() for k in sidecars if k.endswith('-wal'))
    assert 'nothing found' in out
    assert not any(s in out for s in secrets)


def test_doctor_reports_stuck_executions_and_lagging_consumers(db, capsys):
    old = '2026-10-01T00:00:00.000Z'
    put(db, mission('m1'),
        ('plans', dict(META, id='p1', mission_id='m1', plan_version=1, state='APPROVED', body='{}')),
        ('tasks', dict(META, id='t1', plan_id='p1', mission_id='m1', key='a', state='RUNNING',
                       body='{}')),
        ('executions', dict(META, id='exe_stuck', task_id='t1', mission_id='m1', attempt=1,
                            state='RUNNING', body='{}', updated_at=old)),
        ('executions', dict(META, id='exe_fresh', task_id='t1', mission_id='m1', attempt=2,
                            state='RUNNING', body='{}', updated_at='2026-10-18T23:00:00.000Z')),
        *[event('session.observed', 'session', 's', None) for _ in range(doc.LAG_WARN + 1)],
        ('consumer_cursors', {'name': 'knowledge', 'last_seq': 0, 'updated_at': T}))
    code = doc.doctor(now=dt.datetime(2026, 10, 19, tzinfo=dt.timezone.utc))
    out = capsys.readouterr().out
    assert code == doc.DOCTOR_STUCK | doc.DOCTOR_LAG
    assert 'execution exe_stuck RUNNING since %s' % old in out
    assert 'consumer knowledge is %d events behind' % (doc.LAG_WARN + 1) in out
    assert 'exe_fresh' not in out


def test_doctor_leaves_a_wal_core_crashed_out_of_to_core(archeus_home, tmp_path, capsys,
                                                         monkeypatch):
    """A plain query_only reader that closes last checkpoints the WAL into the
    file; doctor's connection cannot, so recovery stays Core's."""
    import shutil
    live = Database.open()
    live.writer.execute(lambda tx: tx.execute("PRAGMA wal_autocheckpoint = 0") and None)
    put(live, *[event('session.observed', 'session', 's', None) for _ in range(50)])
    crashed = tmp_path / 'crashed'
    crashed.mkdir()
    for f in os.listdir(paths.archeus_home()):
        if f.startswith('archeus.db'):
            shutil.copy(os.path.join(paths.archeus_home(), f), crashed / f)
    live.close()
    monkeypatch.setenv('ARCHEUS_HOME', str(crashed))
    assert os.path.getsize(crashed / 'archeus.db-wal') > 0
    data = ('archeus.db', 'archeus.db-wal')        # -shm is SQLite's rebuilt index, not data
    before = {k: v for k, v in _tree(str(crashed)).items() if k in data}
    doc.doctor()
    assert {k: v for k, v in _tree(str(crashed)).items() if k in data} == before
    assert 'integrity ok' in capsys.readouterr().out


def test_a_filled_worker_reads_nothing_until_the_date_changes(db, monkeypatch):
    seed_day(db)
    today = [dt.date(2026, 10, 18)]
    w = metrics.Metrics(db, today=lambda: today[0])
    assert w.pass_once() == {'changed': True}
    assert w.pass_once() == {'changed': False}
    reads = []
    real = db.read
    monkeypatch.setattr(db, 'read', lambda: reads.append(1) or real())
    assert w.pass_once() == {'changed': False} and w.pending() == 0
    assert reads == []
    today[0] = dt.date(2026, 10, 19)
    assert w.pending() == 1
    assert w.pass_once() == {'changed': True}
    with db.read() as r:
        assert [d for (d,) in r.execute('SELECT day FROM metrics_daily ORDER BY day')] == [
            DAY, '2026-10-18']


def test_doctor_reports_a_broken_hook_and_a_newer_schema(archeus_home, tmp_path, monkeypatch,
                                                          capsys):
    import sqlite3
    from archeus.core.execution import manager
    from archeus.infra.db import migrate
    Database.open().close()
    c = sqlite3.connect(connection.db_path())
    c.execute('PRAGMA user_version = %d' % (migrate.migrations()[-1][0] + 1))
    c.close()
    bad = tmp_path / 'hook.py'
    bad.write_text('def (:\n', encoding='utf-8')
    monkeypatch.setattr(manager, 'HOOK', str(bad))
    assert doc.doctor() == doc.DOCTOR_SCHEMA | doc.DOCTOR_HOOK
    out = capsys.readouterr().out
    assert 'this Archeus expects' in out and 'the execution hook' in out


@pytest.mark.parametrize('damage', ['garbage', 'truncated'])
def test_doctor_reports_a_malformed_database_and_writes_nothing(archeus_home, capsys, damage):
    Database.open().close()
    path = connection.db_path()
    data = open(path, 'rb').read()
    open(path, 'wb').write(os.urandom(len(data)) if damage == 'garbage' else data[:len(data) // 2])
    before = _tree(paths.archeus_home())
    code = doc.doctor()
    out = capsys.readouterr().out
    assert code & doc.DOCTOR_DB
    assert 'FINDING database' in out and 'doctor: exit %d' % code in out
    after = _tree(paths.archeus_home())
    assert {k: v for k, v in after.items() if not k.endswith(('-wal', '-shm'))} == {
        k: v for k, v in before.items() if not k.endswith(('-wal', '-shm'))}
