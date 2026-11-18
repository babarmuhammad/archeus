"""T-1446: claude_sessions/quota.py lines 118-185 at tip 026ea58e (re-located at 44aaf17f).

Candidate gaps, not measured coverage. Ten ranked candidates, cross-process state first:

1  :129-140 test_failed_read_is_not_cached_as_clean             DROPPED: caching the {} fallback is the designed fail-open
2  :129-140 test_in_process_note_is_visible_inside_ttl
3  :143-152 test_malformed_latch_entry_reads_as_clean
4  :143-152 test_expired_entry_is_returned_for_caller_to_judge
5  :118-120 latch_file rebind: already pinned by tests/test_rotate_live.py:113; SKIP
6  :168-170 test_missing_session_id_maps_to_nosid
7  :175-180 test_future_stamp_mtime_does_not_extend_cooldown_forever
8  :175-180 test_missing_stamp_is_not_recent
9  :182-187 test_mark_offered_swallows_write_failure
10 :189-204 test_zero_ttl_falls_back_to_observed_ttl

Offer decision (rotate tests) is not re-probed. Seams: quota._c.settings_file,
quota._c.write_atomic, quota._latch, jsonstore.load, store.temp_root, time. All paths
live under tmp_path; no real config dir, no real temp root.
"""

import os
import time
from types import SimpleNamespace

import pytest

from claude_sessions import config as _c
from claude_sessions import jsonstore
from claude_sessions import quota
from claude_sessions import store


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(_c, 'settings_file', str(tmp_path / 'archeus.json'))
    monkeypatch.setattr(quota, '_latch', (0.0, {}))
    monkeypatch.setattr(store, 'temp_root', lambda: str(tmp_path))
    return tmp_path


def test_in_process_note_is_visible_inside_ttl(sandbox):
    acct = str(sandbox / 'acct')
    key = quota._key(acct)
    assert quota._latch_get(key) == (0.0, False)
    quota.note_limit(acct, window=True, ttl=300)
    until, window = quota._latch_get(key)
    assert window is True
    assert until > time.time() + 200


def test_malformed_latch_entry_reads_as_clean(sandbox, monkeypatch):
    data = {'k1': 'oops', 'k2': {'until': None}, 'k3': {'until': 'soon'}}
    monkeypatch.setattr(quota, '_latch', (time.time(), data))
    assert quota._latch_get('k1') == (0.0, False)
    assert quota._latch_get('k2') == (0.0, False)
    assert quota._latch_get('k3') == (0.0, False)


def test_expired_entry_is_returned_for_caller_to_judge(sandbox, monkeypatch):
    past = time.time() - 10
    monkeypatch.setattr(quota, '_latch', (time.time(), {'k': {'until': past, 'window': True}}))
    assert quota._latch_get('k') == (past, True)


def test_missing_session_id_maps_to_nosid(sandbox):
    assert quota._offer_stamp(None) == quota._offer_stamp('')
    assert quota._offer_stamp(None) == os.path.join(str(sandbox), 'archeus-rotate-nosid.stamp')


def test_future_stamp_mtime_does_not_extend_cooldown_forever(sandbox, monkeypatch):
    stamp = quota._offer_stamp('s1')
    open(stamp, 'w').close()
    base = time.time()
    os.utime(stamp, (base + 3600, base + 3600))
    mtime = os.path.getmtime(stamp)
    monkeypatch.setattr(quota, 'time', SimpleNamespace(time=lambda: mtime + quota.OFFER_COOLDOWN - 1))
    assert quota.offered_recently('s1') is True
    monkeypatch.setattr(quota, 'time', SimpleNamespace(time=lambda: mtime + quota.OFFER_COOLDOWN + 1))
    assert quota.offered_recently('s1') is False


def test_missing_stamp_is_not_recent(sandbox):
    assert quota.offered_recently('never-offered') is False


def test_mark_offered_swallows_write_failure(sandbox, monkeypatch):
    assert quota.mark_offered('s2') is True

    def failing(path, text, mode=None):
        raise OSError(13, 'Permission denied')

    monkeypatch.setattr(_c, 'write_atomic', failing)
    assert quota.mark_offered('s3') is False


def test_zero_ttl_falls_back_to_observed_ttl(sandbox):
    acct = str(sandbox / 'acct')
    before = time.time()
    quota.note_limit(acct, window=False, ttl=0)
    until = quota._observed[quota._key(acct)]
    assert before + quota._OBSERVED_TTL <= until <= time.time() + quota._OBSERVED_TTL
