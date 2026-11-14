"""T-1411 · test gaps in claude_sessions/memory.py auto_cycle orchestration
(1570-1647: gating of lesson mining, post-lesson re-sync, the stamped report).

Branches, ranked (gating and refusal first, then the re-sync condition and
partial progress, then the report fields and swallowed errors):

 1. 1619       memory_lessons 'off' never reaches pending_sids or scan_sessions.
 2. 1619       'prompt' still mines (only 'off' disables it).
 3. 1622-1626  the scan runs only with pending sids and its counts are copied.
 4. 1627-1628  a scan failure is logged and the cycle still stamps.
 5. PREMISE    a scan that persists lessons and then raises still needs a digest
               re-sync. Strict xfail.
 6. 1630       scanned > 0 with added == 0 does not re-sync.
 7. 1601-1613  report fields come from the refreshed graph, with int and '' defaults.
 8. 1601       auto_cap is passed through, with 6 as the default.
 9. 1640-1646  a failing final save is swallowed and the report is still returned.
10. 1642-1644  the stored stamp equals the returned report.

Not carried over: the card's premise that a boolean False in settings still
mines. The writers store only 'auto', 'prompt' or 'off' (web/app.js:6563, 7382)
and load_settings does not coerce, so no writer produces the case.
"""

import copy

import pytest

from claude_sessions import config, lessons, memory, memrules

NOW = '2026-11-14T00:00:00+00:00'


class _Log:
    def __init__(self):
        self.calls = []

    def exception(self, msg, *a, **k):
        self.calls.append(msg)


@pytest.fixture
def world(monkeypatch):
    w = {'graph': {'entities': []}, 'saves': [], 'refresh_kwargs': None,
         'refresh': {'last_extracted': 0}, 'settings': {'memory_lessons': 'prompt'},
         'pending': ['s1', 's2'], 'pending_calls': 0, 'scan_calls': [],
         'scan': lambda p, f, sids: (0, len(sids)), 'digest_calls': 0,
         'rules_calls': 0, 'save_fails': False, 'log': _Log()}

    def refresh(project_path, proj_folder, project_name, auto_cap=None):
        w['refresh_kwargs'] = {'auto_cap': auto_cap}
        return dict(w['refresh'])

    def save(p, f, m):
        if w['save_fails']:
            raise OSError('disk full')
        w['graph'] = copy.deepcopy(m)
        w['saves'].append(copy.deepcopy(m))

    def pending(proj_folder, mem):
        w['pending_calls'] += 1
        return list(w['pending'])

    def scan(p, f, sids):
        w['scan_calls'].append(list(sids))
        return w['scan'](p, f, sids)

    def digest(p, f, mem):
        w['digest_calls'] += 1

    def rules(p, f, mem):
        w['rules_calls'] += 1

    monkeypatch.setattr(memory, 'refresh_memory', refresh)
    monkeypatch.setattr(memory, 'load_memory', lambda p, f=None: copy.deepcopy(w['graph']))
    monkeypatch.setattr(memory, 'save_memory', save)
    monkeypatch.setattr(memory, 'sync_to_claudemd', digest)
    monkeypatch.setattr(memrules, 'sync_rules', rules)
    monkeypatch.setattr(memory, '_iso', lambda: NOW)
    monkeypatch.setattr(lessons, 'pending_sids', pending)
    monkeypatch.setattr(lessons, 'scan_sessions', scan)
    monkeypatch.setattr(config, 'load_settings', lambda: dict(w['settings']))
    monkeypatch.setattr(config, 'log', w['log'])
    return w


def _cycle(**kw):
    return memory.auto_cycle('/p', '/f', 'proj', **kw)


def test_auto_cycle_off_never_mines_lessons(world):
    """'off' skips the lesson scan entirely: no pending lookup, no scan, zero
    counts. Catches: the gate at memory.py:1619."""
    world['settings'] = {'memory_lessons': 'off'}
    out = _cycle()
    assert world['pending_calls'] == 0
    assert world['scan_calls'] == []
    assert (out['lessons'], out['scanned']) == (0, 0)


def test_auto_cycle_prompt_still_mines(world):
    """'prompt' is not 'off', so lessons are still mined and the digest is then
    re-synced. Catches: a gate that treats any non-default value as off."""
    world['scan'] = lambda p, f, sids: (1, len(sids))
    out = _cycle()
    assert world['scan_calls'] == [['s1', 's2']]
    assert (out['lessons'], out['scanned']) == (1, 2)
    assert world['digest_calls'] == 1 and world['rules_calls'] == 1


def test_auto_cycle_copies_scan_counts(world):
    """The pending sids go to the scan as they are, and its (added, scanned) pair
    is copied to the report. Catches: the assignment at memory.py:1626."""
    world['pending'] = ['a', 'b', 'c']
    world['scan'] = lambda p, f, sids: (2, 3)
    out = _cycle()
    assert world['scan_calls'] == [['a', 'b', 'c']]
    assert (out['lessons'], out['scanned']) == (2, 3)


def test_auto_cycle_scan_failure_is_logged_and_stamped(world):
    """A failing lesson scan is logged once and the cycle still reaches the stamp
    with the zero counts. Catches: the try and except at memory.py:1624-1628 and
    the stamp at 1640-1644."""
    def boom(p, f, sids):
        raise RuntimeError('model unavailable')
    world['scan'] = boom
    out = _cycle()
    assert world['log'].calls == ['memory: auto lesson scan failed']
    assert out['lessons'] == 0
    assert world['graph']['auto_last'] == out
    assert world['graph']['auto_updated'] == NOW


@pytest.mark.xfail(strict=True, reason=(
    "memory.py:1626 copies the scan counts only when scan_sessions returns, and the "
    "re-sync at memory.py:1630-1638 keys on out['lessons']. lessons.py:236 saves "
    "after every session, so a raise on the second session leaves the first "
    "session's lessons on disk while out['lessons'] stays 0: the CLAUDE.md count and "
    "the rules are not re-synced. Reachable when memory._claude_json raises after an "
    "earlier session saved."))
def test_auto_cycle_partial_scan_still_resyncs_digest(world):
    """Expected: a lesson persisted before the scan raised still triggers a digest
    and rules re-sync. Current: no re-sync happens."""
    def partial(p, f, sids):
        g = copy.deepcopy(world['graph'])
        g['entities'].append({'id': 'lesson:s1:0', 'name': 'kept', 'type': 'lesson',
                              'status': 'approved', 'last_used': 0})
        memory.save_memory(p, f, g)
        raise RuntimeError('second session failed')
    world['scan'] = partial
    _cycle()
    assert world['digest_calls'] == 1


def test_auto_cycle_no_resync_when_nothing_added(world):
    """Sessions were scanned but no lesson was added: the digest count did not
    change, so neither writer runs. Catches: the 'if out[lessons]' gate at
    memory.py:1630."""
    world['scan'] = lambda p, f, sids: (0, 2)
    out = _cycle()
    assert (out['lessons'], out['scanned']) == (0, 2)
    assert world['digest_calls'] == 0 and world['rules_calls'] == 0


def test_auto_cycle_report_fields_from_refresh(world):
    """graph is True only when something was re-extracted; pending, failed,
    skipped come from the refreshed graph with int defaults, and error defaults to
    ''. Catches: memory.py:1601-1613."""
    world['refresh'] = {'last_extracted': 4, 'pending_units': 2, 'last_failed': 1,
                        'last_skipped': 3, 'last_error': 'rate limited'}
    out = _cycle()
    assert out['graph'] is True and out['extracted'] == 4
    assert (out['pending'], out['failed'], out['skipped']) == (2, 1, 3)
    assert out['error'] == 'rate limited'

    world['refresh'] = {'last_extracted': 0}
    out = _cycle()
    assert out['graph'] is False and out['extracted'] == 0
    assert (out['pending'], out['failed'], out['skipped'], out['error']) == (0, 0, 0, '')


def test_auto_cycle_passes_auto_cap_through(world):
    """auto_cap reaches refresh_memory unchanged, and 6 is the default. Catches:
    the argument at memory.py:1601."""
    _cycle(auto_cap=9)
    assert world['refresh_kwargs'] == {'auto_cap': 9}
    _cycle()
    assert world['refresh_kwargs'] == {'auto_cap': 6}


def test_auto_cycle_stamps_report_and_survives_save_failure(world):
    """A failing final save is swallowed and the report is still returned. Catches:
    the bare except at memory.py:1645-1646."""
    world['save_fails'] = True
    out = _cycle()
    assert set(out) >= {'graph', 'lessons', 'scanned', 'pending'}
    assert world['saves'] == []


def test_auto_cycle_stored_report_matches_return(world):
    """The stamp written to disk is the report the cycle returns, key for key.
    Catches: the assignment at memory.py:1643 storing something other than out."""
    world['refresh'] = {'last_extracted': 2, 'last_error': 'x'}
    world['scan'] = lambda p, f, sids: (1, 2)
    out = _cycle()
    assert world['graph']['auto_last'] == out
    assert world['graph']['auto_updated'] == NOW
