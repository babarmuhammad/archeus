"""T-1314 — gap tests for `claude_sessions/ccsettings.py` lines 204-269 (inclusive)
at worktree tip d429bf96 (card tip 51f4af3f; the lines still match).

Source slice: `write()` (204-225) and `_coerce()` (228-269). `write` refuses an
unknown key, clears on None or '', coerces through the schema, then does one
read-modify-write of the single chosen dotted key. `_coerce` decides what the
file Claude Code parses will contain, so every refusal here is a startup error
the user never sees.

Selected branches (denial/fail-closed first, then boundaries, then error paths):
 1. :241      fractional float (+4.5, -4.5) refused before any load or save
 2. :244      float 4.0 becomes int 4; string '4.0' is refused (type kept)
 3. :244      bool for an int key (True/False) must be refused, not stored as 1/0
              — STRICT XFAIL, see its reason
 4. :244      huge Python int is stored exactly (no float round trip, no bound)
 5. :241      NaN and +/-inf refused before int() can raise OverflowError
 6. :248      enum: exact choice accepted; case variant and prefix refused
 7. :251-257  list kind: a text value is split on commas and newlines, empty items
              dropped (replaces the unknown-key probe: test_gaps3 already pins it
              at test_unknown_key_is_refused_before_io)
 8. :215-219  None and '' clear the key; False and 0 are values, not clears
 9. :224-225  coerced write changes only the chosen nested key; a failed save is
              reported as False
10. :245      invalid integer string and object refused with the whole-number
              message; no partial mutation, no save

Every Windows path is a tmp_path file; hooks.settings_path is repointed before
any call so no real account settings file is read or written.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from harness import Sandbox  # noqa: E402
from claude_sessions import ccsettings, hooks  # noqa: E402


@pytest.fixture
def acct(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    d = tmp_path / 'cfg'
    d.mkdir(exist_ok=True)
    monkeypatch.setattr(hooks, 'settings_path', str(d / 'settings.json'))
    return d


def _spy(monkeypatch):
    calls = {'load': 0, 'save': 0}
    real_load, real_save = hooks._load, hooks._save

    def load(cfgdir=None):
        calls['load'] += 1
        return real_load(cfgdir)

    def save(payload, cfgdir=None):
        calls['save'] += 1
        return real_save(payload, cfgdir)

    monkeypatch.setattr(hooks, '_load', load)
    monkeypatch.setattr(hooks, '_save', save)
    return calls


def _seed(acct, payload):
    text = json.dumps(payload)
    (acct / 'settings.json').write_text(text, encoding='utf-8')
    return text


def _raw(acct):
    return (acct / 'settings.json').read_text(encoding='utf-8')


def _file(acct):
    return json.loads(_raw(acct))


def test_fractional_float_refused_before_any_io(acct, monkeypatch):
    """Branch :241. Removing the `not value.is_integer()` test would store
    int(4.5)=4 for a positive value and int(-4.5)=-4 for a negative one."""
    calls = _spy(monkeypatch)
    before = _seed(acct, {'alwaysThinkingEnabled': True})
    for bad in (4.5, -4.5):
        ok, msg = ccsettings.write('cleanupPeriodDays', bad, str(acct))
        assert not ok and msg == 'expected a whole number', bad
    assert calls == {'load': 0, 'save': 0}
    assert _raw(acct) == before


def test_integer_valued_float_is_stored_as_int_and_string_float_is_refused(acct):
    """Branch :244. 4.0 must become the int 4 (JSON 4, not 4.0); the string
    '4.0' must be refused because int('4.0') raises ValueError at :245."""
    ok, msg = ccsettings.write('cleanupPeriodDays', 4.0, str(acct))
    assert ok, msg
    value = _file(acct)['cleanupPeriodDays']
    assert value == 4 and type(value) is int
    before = _raw(acct)
    ok, msg = ccsettings.write('cleanupPeriodDays', '4.0', str(acct))
    assert not ok and msg == 'expected a whole number'
    assert _raw(acct) == before


def test_bool_for_an_int_key_is_refused(acct):
    """Branch :244, probe 3. The int kind only checks the float case at :241,
    so `True` and `False` fall through to int() and are accepted as 1 and 0.
    A wrongly typed value must be refused, as the module docstring requires."""
    before = _seed(acct, {'cleanupPeriodDays': 7})
    for bad in (True, False):
        ok, _msg = ccsettings.write('cleanupPeriodDays', bad, str(acct))
        assert not ok, f'{bad!r} must not be stored for an int key'
    assert _raw(acct) == before


def test_huge_python_int_is_preserved_exactly(acct):
    """Branch :244 for an int well past 2**53. A float round trip would turn it
    into 1e+30 and lose digits; an arbitrary bound would refuse it."""
    big = 10 ** 30
    ok, msg = ccsettings.write('cleanupPeriodDays', big, str(acct))
    assert ok, msg
    value = _file(acct)['cleanupPeriodDays']
    assert value == big and type(value) is int
    assert str(big) in _raw(acct)


def test_nan_and_infinity_are_refused_without_overflow(acct, monkeypatch):
    """Branch :241. float('nan').is_integer() and float('inf').is_integer() are
    False, so the guard refuses them before int(inf) can raise OverflowError at
    :244 — which would escape the (TypeError, ValueError) handler."""
    calls = _spy(monkeypatch)
    before = _seed(acct, {'cleanupPeriodDays': 7})
    for bad in (float('nan'), float('inf'), float('-inf')):
        ok, msg = ccsettings.write('cleanupPeriodDays', bad, str(acct))
        assert not ok and msg == 'expected a whole number', bad
    assert calls == {'load': 0, 'save': 0}
    assert _raw(acct) == before


def test_enum_key_accepts_exact_choice_and_refuses_variants(acct, monkeypatch):
    """Branch :248. Removing the membership test, or lower-casing the value, would
    accept 'LOW' or 'lo' and Claude Code would fail to start."""
    ok, msg = ccsettings.write('effortLevel', 'high', str(acct))
    assert ok, msg
    assert _file(acct)['effortLevel'] == 'high'
    calls = _spy(monkeypatch)
    before = _raw(acct)
    for bad in ('High', 'HIGH', 'hi', 'high '):
        ok, msg = ccsettings.write('effortLevel', bad, str(acct))
        assert not ok and msg.startswith('expected one of: low, medium'), bad
    assert calls == {'load': 0, 'save': 0}
    assert _raw(acct) == before


def test_list_key_splits_text_and_drops_empty_items(acct):
    """Branch :251-257. A comma- or newline-separated string becomes a list with
    blank items dropped, and an actual list is kept as given with its blanks
    removed. Dropping the filter would store '' entries Claude Code reads as
    model ids."""
    ok, msg = ccsettings.write('fallbackModel', 'opus, sonnet\n\n haiku,,', str(acct))
    assert ok, msg
    assert _file(acct)['fallbackModel'] == ['opus', 'sonnet', 'haiku']
    ok, msg = ccsettings.write('fallbackModel', ['a', '', 'b'], str(acct))
    assert ok, msg
    assert _file(acct)['fallbackModel'] == ['a', 'b']


def test_none_and_empty_string_clear_while_false_and_zero_are_values(acct):
    """Branch :215-219. `value is None or value == ''` must take the clear path
    only for those two values. A broader test (e.g. `not value`) would turn
    False and 0 into a removed key, which means something else to Claude Code
    (see the write() docstring)."""
    _seed(acct, {'cleanupPeriodDays': 7, 'axScreenReader': True})
    ok, msg = ccsettings.write('cleanupPeriodDays', None, str(acct))
    assert ok and msg == 'cleared cleanupPeriodDays'
    assert 'cleanupPeriodDays' not in _file(acct)
    ok, msg = ccsettings.write('cleanupPeriodDays', '', str(acct))
    assert ok and msg == 'already unset'
    ok, msg = ccsettings.write('axScreenReader', False, str(acct))
    assert ok, msg
    assert _file(acct)['axScreenReader'] is False
    ok, msg = ccsettings.write('cleanupPeriodDays', 0, str(acct))
    assert ok, msg
    assert _file(acct)['cleanupPeriodDays'] == 0


def test_coerced_nested_write_touches_only_its_key_and_reports_save_failure(acct, monkeypatch):
    """Branches :224-225. A dotted write must keep every sibling under the same
    block (permissions.allow, permissions.defaultMode and a top-level key). If the
    save returns False the result must be (False, ...), never a success claim."""
    _seed(acct, {'permissions': {'allow': ['Bash(ls)'], 'defaultMode': 'plan'},
                 'alwaysThinkingEnabled': True})
    ok, msg = ccsettings.write('permissions.disableAutoMode', 'disable', str(acct))
    assert ok and msg == 'set permissions.disableAutoMode'
    got = _file(acct)
    assert got['permissions'] == {'allow': ['Bash(ls)'], 'defaultMode': 'plan',
                                  'disableAutoMode': 'disable'}
    assert got['alwaysThinkingEnabled'] is True
    monkeypatch.setattr(hooks, '_save', lambda payload, cfgdir=None: False)
    ok, msg = ccsettings.write('alwaysThinkingEnabled', False, str(acct))
    assert ok is False and msg == 'set alwaysThinkingEnabled'


def test_invalid_integer_forms_refused_without_partial_mutation(acct, monkeypatch):
    """Branch :245. '1e3' (int() ValueError) and an object (int() TypeError) both
    return the whole-number message. Nothing is loaded, saved or changed."""
    calls = _spy(monkeypatch)
    before = _seed(acct, {'cleanupPeriodDays': 7})
    for bad in ('1e3', {}):
        ok, msg = ccsettings.write('cleanupPeriodDays', bad, str(acct))
        assert not ok and msg == 'expected a whole number', bad
    assert calls == {'load': 0, 'save': 0}
    assert _raw(acct) == before
