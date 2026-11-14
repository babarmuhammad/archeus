"""T-1183: the highest-risk uncovered branches of claude_sessions/ccsettings.py
lines 1-267 inclusive (tip 56d53504). ONE new test file; no source file edited.

Existing coverage read first: tests/test_features.py and tests/test_tui_hooks.py
contain no ccsettings coverage; a tests/ search for the module path shows the
real coverage is the settings-editor section of tests/test_clientstate.py
(round-trip :269, sibling-preserving write :277, clear-not-default :290,
wrong-type refusals :307, unknown key :315, typed list :320, nested clobber
:325, prune-empty-block :352, enum refusals :364, fallback chain :375), plus
GROUP_HELP/GROUPS reads in tests/test_gui_plain_language.py. ccsettings.read_all
and gui_api.api_cc_settings_get/set have no test at all (noted, out of the ten).

The ten final branches, ranked fail-closed/denial first, then boundaries, then
error paths. The card's probes 2 (invalid enum), 5 (JSON scalar) and 6
(malformed JSON) are already covered by tests/test_clientstate.py:304-311 and
were replaced; probe 7 (permission set keeps allow/deny) is covered for the
dict path at :325 and was replaced by its uncovered fault composition:

 1. save failure on set AND clear reports ok=False        ccsettings.py:219, :225
 2. unknown key refused BEFORE any load or save           ccsettings.py:212-213
 3. clearing an unset key is a no-op that never saves     ccsettings.py:178-179, :217-218
 4. dotted set below a non-dict block replaces only it    ccsettings.py:160-162 (:146-148 read half)
 5. allow/deny survive coercion; a refusal never saves    ccsettings.py:161, :220-222
 6. int refuses '4.5'/junk/TypeError; float xfail         ccsettings.py:240-244 (defect :242)
 7. bool coercion: int 1 -> True, 2 refused, 'OFF' False  ccsettings.py:232-239
 8. json dict passthrough stores an object, env untouched ccsettings.py:256-258
 9. str kind stringifies non-str values                   ccsettings.py:267
10. _del_path prunes ONLY empty ancestors, keeps siblings ccsettings.py:173-184

Isolation: ccsettings's only import is `from . import hooks` (line 19); no
credential reader, editor, pager, model, scheduler or process runner is
reachable from it, so the only seams faked are the module's two I/O functions
hooks._load/hooks._save, and the whole config root is repointed into tmp_path
by harness.Sandbox before any entrypoint can reach host state. Synthetic
credential-shaped values only; nothing here reads the real home or environment.
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
    """One fake account dir standing in for ~/.claude, with the config root,
    settings file and selected-home bindings faked by Sandbox before entry."""
    Sandbox(monkeypatch, tmp_path)
    d = tmp_path / 'cfg'
    d.mkdir(exist_ok=True)
    # the cfgdir=None fallback of hooks.settings_path_for must also never
    # reach a real ~/.claude, even though every call below passes a cfgdir
    monkeypatch.setattr(hooks, 'settings_path', str(d / 'settings.json'))
    return d


def _spy(monkeypatch):
    """Count calls to the module's two I/O seams, keeping real tmp-file
    behaviour so absence-of-write is asserted twice: by counter and by bytes."""
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


def _file(acct):
    return json.loads((acct / 'settings.json').read_text(encoding='utf-8'))


# ── 1. fail-closed: the save result is the return value ──────────────────────

def test_a_failed_save_is_reported_not_claimed(acct, monkeypatch):
    """write() returns bool(hooks._save(...)) at ccsettings.py:219 (clear) and
    :225 (set). No existing test ever fails a save: test_clientstate.py:269
    only asserts the success case, so replacing bool(_save(...)) with a
    constant True (a lie on ENOSPC/EPERM) passes the whole current suite."""
    seed = _seed(acct, {'theme': 'invented-old'})
    monkeypatch.setattr(hooks, '_save', lambda payload, cfgdir=None: False)
    ok, msg = ccsettings.write('theme', 'invented-new', str(acct))
    assert ok is False, 'a failed set must not claim success'
    assert msg == 'set theme'
    ok, msg = ccsettings.write('theme', '', str(acct))
    assert ok is False, 'a failed clear must not claim success'
    assert msg == 'cleared theme'
    assert (acct / 'settings.json').read_text(encoding='utf-8') == seed


# ── 2. denial before any privileged side effect ──────────────────────────────

def test_unknown_key_is_refused_before_io(acct, monkeypatch):
    """The unknown-key return at ccsettings.py:212-213 must fire BEFORE
    hooks._load/_save. The closest test, test_clientstate.py:315
    test_an_unknown_key_is_refused, asserts only `not ok` — it still passes if
    write() loaded and saved the account first and only then validated."""
    calls = _spy(monkeypatch)
    ok, msg = ccsettings.write('rmRfEverything', True, str(acct))
    assert ok is False
    assert 'rmRfEverything' in msg
    assert calls == {'load': 0, 'save': 0}, 'denial must not touch the file'
    assert not (acct / 'settings.json').exists()


# ── 3. no-op clearing never reaches the disk ─────────────────────────────────

def test_clearing_an_unset_key_writes_nothing(acct, monkeypatch):
    """Clearing a key that was never set takes the `_del_path` False return at
    ccsettings.py:178-179 (nested, with siblings present) or the missing-key
    False at the single-part case, then the 'already unset' return at
    :217-218 which SKIPS hooks._save. test_clientstate.py:290 always sets
    before clearing, so both False returns and the save-skipping 'already
    unset' line are unreached; inverting the guard at :217 would leave a
    save-shaped write here."""
    calls = _spy(monkeypatch)
    seed = _seed(acct, {'permissions': {'allow': ['Bash(git status:*)'],
                                       'deny': ['Read(./.env)']}})
    ok, msg = ccsettings.write('theme', '', str(acct))           # single-part miss
    assert ok is True and msg == 'already unset'
    ok, msg = ccsettings.write('permissions.defaultMode', '', str(acct))  # nested miss
    assert ok is True and msg == 'already unset'
    assert calls['save'] == 0, 'a no-op must not rewrite settings.json'
    assert (acct / 'settings.json').read_text(encoding='utf-8') == seed


# ── 4. a corrupt (non-dict) block: read fails closed, set replaces only it ───

def test_setting_below_a_scalar_block_replaces_only_it(acct):
    """_set_path's `else {}` branch at ccsettings.py:160-162 (a dotted write
    whose intermediate exists as a non-dict) and _get_path's not-a-dict
    return at :146-148. test_clientstate.py:325 only ever seeds `permissions`
    as a dict, so it exercises the dict(nxt) copy half and never the else;
    replacing the ternary with setdefault() (keep the scalar, crash inside) or
    with `dict(nxt) if not isinstance(...)` passes every current test."""
    _seed(acct, {'permissions': 'legacy-scalar', 'model': 'opus'})
    # read side first: descending through the scalar must read MISSING, not raise
    assert ccsettings.read(str(acct)) == {'model': 'opus'}
    ok, msg = ccsettings.write('permissions.defaultMode', 'plan', str(acct))
    assert ok, msg
    assert _file(acct) == {'permissions': {'defaultMode': 'plan'},
                           'model': 'opus'}


# ── 5. permission siblings across coercion; refusal stops at validation ──────

def test_deny_survives_coercion_and_refusal_saves_nothing(acct, monkeypatch):
    """Card focus: Settings coercion preserves permission siblings. The
    copy-on-write at ccsettings.py:161 keeps the deny/allow rules written by
    health.propose_allowlist and denygen, and the `if not ok` guard at
    :220-222 refuses an invalid enum BEFORE hooks._load. Closest existing:
    test_clientstate.py:325 covers the accept half against a dict block but
    never asserts the refusal left the file byte-identical, and
    test_clientstate.py:364 checks only flag and message text."""
    calls = _spy(monkeypatch)
    _seed(acct, {'permissions': {'allow': ['Bash(git log:*)'],
                                 'deny': ['Read(./.env)']}})
    ok, msg = ccsettings.write('permissions.defaultMode', 'auto', str(acct))
    assert ok, msg
    assert _file(acct)['permissions'] == {'allow': ['Bash(git log:*)'],
                                         'deny': ['Read(./.env)'],
                                         'defaultMode': 'auto'}
    mid = (acct / 'settings.json').read_text(encoding='utf-8')
    saves = calls['save']
    ok, msg = ccsettings.write('permissions.defaultMode', 'yolo', str(acct))
    assert not ok and 'expected one of' in msg
    assert calls['save'] == saves, 'a refused write must never reach the disk'
    assert calls['load'] == 1, 'refusal is coerced before any load (ccsettings.py:220-223)'
    assert (acct / 'settings.json').read_text(encoding='utf-8') == mid


# ── 6. boundary: an int key wants a WHOLE number ─────────────────────────────

def test_int_key_refuses_fractions_and_non_numbers(acct):
    """The ValueError branch at ccsettings.py:243-244 covers '4.5' and 'soon',
    and the TypeError branch covers a list (test_clientstate.py:306 only ever
    passes the string 'soon'). A string fraction that truncates, or a TypeError
    that escapes as a crash instead of ('expected a whole number'), fails here."""
    ok, msg = ccsettings.write('autoCompactWindow', '4500', str(acct))
    assert ok, msg
    assert ccsettings.read(str(acct))['autoCompactWindow'] == 4500
    for bad in ('4.5', 'soon', ['7']):
        ok, msg = ccsettings.write('autoCompactWindow', bad, str(acct))
        assert not ok and 'whole number' in msg, bad
    assert ccsettings.read(str(acct))['autoCompactWindow'] == 4500


def test_int_key_refuses_a_real_float(acct):
    """Same branch as above from the float input: a fractional value must be
    refused, not truncated. Inverts only against the known defect at :242."""
    ok, _msg = ccsettings.write('autoCompactWindow', 4.5, str(acct))
    assert not ok, 'int(4.5) must not quietly become 4'


# ── 7. boundary: booleans and integers must not confuse each other ───────────

def test_integer_one_is_a_boolean_not_a_number(acct):
    """Probe 3, ccsettings.py:232-239. The string spellings ('1','OFF') hit the
    table at :235-:238 and the `is True` / `is False` identity checks pin that
    JSON stores real booleans, not 1/0/'1'; test_clientstate.py:290 writes only
    Python bools and the refusal table at :307 only 'maybe', so returning
    `value` unchanged at :236/:238 (storing the string '1') passes both."""
    ok, msg = ccsettings.write('alwaysThinkingEnabled', 1, str(acct))
    assert ok, msg
    got = _file(acct)
    assert got['alwaysThinkingEnabled'] is True          # JSON true, not number 1
    ok, msg = ccsettings.write('axScreenReader', 'OFF', str(acct))
    assert ok, msg
    assert _file(acct)['axScreenReader'] is False
    for bad in (2, 'maybe'):
        ok, msg = ccsettings.write('alwaysThinkingEnabled', bad, str(acct))
        assert not ok and 'true or false' in msg, bad
    assert _file(acct)['alwaysThinkingEnabled'] is True   # refusals changed nothing


# ── 8. boundary: JSON objects stay objects and touch no env ──────────────────

def test_json_object_is_stored_as_an_object(acct):
    """The dict/list passthrough at ccsettings.py:256-258 — no existing test
    hands write() an already-parsed dict (test_clientstate.py:304-305 only
    covers the malformed-string and JSON-scalar refusals at :262-265). Delete
    the passthrough and json.loads(dict) raises TypeError into the generic
    `except Exception` at :262: the write is refused, and this fails."""
    ok, msg = ccsettings.write('attribution', {'name': 'Invented Bot'}, str(acct))
    assert ok, msg
    assert _file(acct)['attribution'] == {'name': 'Invented Bot'}
    ok, msg = ccsettings.write('env', {'INVENTED_CRED': 'invented-token'},
                               str(acct))
    assert ok, msg
    assert _file(acct)['env'] == {'INVENTED_CRED': 'invented-token'}
    # an 'env' setting is data written to a file, never a process mutation
    assert 'INVENTED_CRED' not in os.environ


# ── 9. boundary: the str kind stringifies what a person types ────────────────

def test_str_kind_stringifies_non_str_values(acct):
    """The schema's last-resort `return True, str(value)` at ccsettings.py:267
    (kind 'str' falls through every typed branch). Nothing in
    tests/test_clientstate.py writes a 'str'-kind key at all, so dropping the
    str() (storing the number 42 for teammateMode) or flipping the fallthrough
    to a refusal passes the current suite."""
    ok, msg = ccsettings.write('model', 'invented-model-7', str(acct))
    assert ok, msg
    ok, msg = ccsettings.write('teammateMode', 42, str(acct))
    assert ok, msg
    got = _file(acct)
    assert got['model'] == 'invented-model-7'
    assert got['teammateMode'] == '42', 'stored as text, not as the number 42'


# ── 10. error-path helper: prune ONLY the ancestors this deletion emptied ────

def test_del_prunes_only_empty_ancestors():
    """_del_path's prune loop at ccsettings.py:181-183 walks the RECORDED chain
    in reverse and pops a parent only `if parent[part] == {}` (:182). The
    closest existing test, test_clientstate.py:352, prunes a one-level chain to
    an empty root, and :325 covers only the non-empty sibling case — neither
    pins (a) a non-empty GRANDPARENT kept while its emptied child is pruned,
    (b) an empty non-ancestor subtree left alone, or (c) the two False guards
    at :174-175 and :178-179 for a missing/non-dict intermediate."""
    d = {'x': {'y': {'z': 1}, 's': {}},
         'permissions': {'allow': ['Bash(git diff:*)'], 'defaultMode': 'plan'}}
    assert ccsettings._del_path(d, 'x.y.z') is True
    assert d['x'] == {'s': {}}                       # emptied child pruned...
    assert 'y' not in d['x']                          # ...only because it was empty
    assert d['permissions'] == {'allow': ['Bash(git diff:*)'],
                                'defaultMode': 'plan'}   # untouched subtree
    assert ccsettings._del_path(d, 'x.y.z') is False      # already gone (:178-179)
    assert ccsettings._del_path({'a': 'scalar'}, 'a.b') is False  # non-dict (:174-175)
