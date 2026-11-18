"""T-1425: claude_sessions/clientstate.py:306-340 disk report at 026ea58e.

Selected candidates, not measured coverage.
Closest existing assertions: tests/test_clientstate.py:151 (bytes and files of
growing stores only, no age, no vanished file). No existing test asserts oldest_days.
"""

import os

from claude_sessions import clientstate, config


def _write(path, n, mtime=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(b'x' * n)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def _stores(report):
    return [[s['name'] for s in a['stores']] for a in report['accounts']]


def test_explicit_cfgdir_has_blank_account_name(tmp_path):
    _write(str(tmp_path / 'projects' / 'a.jsonl'), 10)
    report = clientstate.disk_report(str(tmp_path))
    assert report['accounts'][0]['account'] == ''
    assert report['accounts'][0]['dir'] == str(tmp_path)


def test_totals_are_sums_of_rows_and_accounts(monkeypatch, tmp_path):
    one, two = tmp_path / 'one', tmp_path / 'two'
    _write(str(one / 'projects' / 'a.jsonl'), 100)
    _write(str(one / 'plans' / 'p.md'), 50)
    _write(str(two / 'projects' / 'b.jsonl'), 30)
    monkeypatch.setattr(config, 'all_config_dirs',
                        lambda: [('one', str(one)), ('two', str(two))])
    report = clientstate.disk_report()
    assert [a['bytes'] for a in report['accounts']] == [150, 30]
    assert report['bytes'] == 180
    assert [(s['name'], s['bytes'], s['files']) for s in report['accounts'][0]['stores']] \
        == [('projects', 100, 1), ('plans', 50, 1)]


def test_missing_config_dir_reports_zero_not_error(tmp_path):
    report = clientstate.disk_report(str(tmp_path / 'absent'))
    assert report['accounts'][0]['stores'] == []
    assert report['accounts'][0]['bytes'] == 0
    assert report['bytes'] == 0


def test_only_declared_stores_are_measured(tmp_path):
    _write(str(tmp_path / 'cache' / 'x.bin'), 500)
    _write(str(tmp_path / 'projects' / 'y.jsonl'), 10)
    assert _stores(clientstate.disk_report(str(tmp_path))) == [['projects']]


def test_empty_store_is_omitted(tmp_path):
    os.makedirs(str(tmp_path / 'projects' / 'empty'))
    assert _stores(clientstate.disk_report(str(tmp_path))) == [[]]


def test_rows_sorted_by_size_then_declared_order(tmp_path):
    _write(str(tmp_path / 'projects' / 'a.jsonl'), 100)
    _write(str(tmp_path / 'backups' / 'b.json'), 50)
    _write(str(tmp_path / 'plans' / 'p.md'), 50)
    assert _stores(clientstate.disk_report(str(tmp_path))) == \
        [['projects', 'plans', 'backups']]


def test_vanished_files_are_not_counted(monkeypatch, tmp_path):
    _write(str(tmp_path / 'projects' / 'gone.jsonl'), 500)
    _write(str(tmp_path / 'projects' / 'kept.jsonl'), 40)
    real_stat = os.stat

    def stat(path, *a, **k):
        if str(path).endswith('gone.jsonl'):
            raise FileNotFoundError(path)
        return real_stat(path, *a, **k)

    monkeypatch.setattr(clientstate.os, 'stat', stat)
    store = clientstate.disk_report(str(tmp_path))['accounts'][0]['stores'][0]
    assert (store['name'], store['bytes'], store['files']) == ('projects', 40, 1)


def test_oldest_days_counts_whole_days_from_the_oldest_file(monkeypatch, tmp_path):
    now = 1_700_000_000.0
    monkeypatch.setattr(clientstate.time, 'time', lambda: now)
    _write(str(tmp_path / 'projects' / 'old.jsonl'), 5, now - 3 * 86400 - 100)
    _write(str(tmp_path / 'projects' / 'new.jsonl'), 5, now - 86400)
    store = clientstate.disk_report(str(tmp_path))['accounts'][0]['stores'][0]
    assert store['oldest_days'] == 3
