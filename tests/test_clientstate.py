"""Phase 5: reading Claude Code's own state, and editing its settings.

Every format read here is undocumented, so the discipline from `checkpoints.py`
applies throughout — an unrecognised shape must report that it is unreadable
rather than guessing, and an empty store must read as empty rather than broken.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from harness import Sandbox
from claude_sessions import ccsettings, clientstate, diskgc, hooks


@pytest.fixture
def acct(monkeypatch, tmp_path):
    """One account directory, standing in for ~/.claude."""
    Sandbox(monkeypatch, tmp_path)
    d = tmp_path / 'cfg'
    d.mkdir(exist_ok=True)
    monkeypatch.setattr(hooks, 'settings_path', str(d / 'settings.json'))
    return d


# ── .claude.json ─────────────────────────────────────────────

def _client_json(d, payload):
    (d / '.claude.json').write_text(json.dumps(payload), encoding='utf-8')


@pytest.mark.skipif(os.name != 'nt',
                    reason='the backslash/forward-slash mismatch this guards '
                           'only exists on Windows; POSIX paths already match')
def test_a_project_is_found_by_its_real_path(acct):
    """The keys use forward slashes even on Windows, so a plain os.path
    comparison misses every project."""
    _client_json(acct, {'projects': {'D:/Claude': {'lastCost': 51.14}}})
    got = clientstate.project_state('D:\\Claude', str(acct))
    assert got['lastCost'] == 51.14


def test_an_unknown_project_is_empty_not_an_error(acct):
    _client_json(acct, {'projects': {}})
    assert clientstate.project_state('D:\\Nope', str(acct)) == {}


def test_usage_reports_what_is_actually_used(acct):
    """The only record of which skills, plugins and agents are live rather than
    dead weight — a question archeus could not answer at all."""
    now_ms = int(time.time() * 1000)
    _client_json(acct, {
        'skillUsage': {'rare': {'usageCount': 1, 'lastUsedAt': now_ms},
                       'common': {'usageCount': 99, 'lastUsedAt': now_ms}},
        'pluginUsage': {'p@p': {'usageCount': 7, 'lastUsedAt': now_ms}},
        'agentLastUsed': {'bg': now_ms}})
    u = clientstate.usage_rollup(str(acct))
    assert [r['name'] for r in u['skills']] == ['common', 'rare']
    assert u['skills'][0]['count'] == 99
    assert u['plugins'][0]['name'] == 'p@p'
    assert u['agents'][0]['name'] == 'bg'


def test_the_timestamps_are_milliseconds_not_seconds(acct):
    """Claude Code stores epoch MILLISECONDS. Read as seconds the value is a
    thousand-fold too small, the age comes out hugely negative, and EVERYTHING
    reads as 'now' — which looks plausible, so the check has to use a stamp
    that is definitely old."""
    three_days = int((time.time() - 3 * 86400) * 1000)
    _client_json(acct, {'skillUsage': {'s': {'usageCount': 1,
                                             'lastUsedAt': three_days}}})
    assert clientstate.usage_rollup(str(acct))['skills'][0]['last_used'] == '3d'


def test_a_corrupt_client_json_does_not_crash_the_page(acct):
    (acct / '.claude.json').write_text('{"projects": ', encoding='utf-8')
    assert clientstate.usage_rollup(str(acct)) == {'skills': [], 'plugins': [],
                                                   'agents': []}


# ── history.jsonl ────────────────────────────────────────────

def test_prompt_history_searches_what_the_user_actually_typed(acct):
    lines = [{'display': 'fix the parser', 'project': 'P', 'sessionId': 's1',
              'timestamp': 1},
             {'display': 'write the tests', 'project': 'P', 'sessionId': 's2',
              'timestamp': 2}]
    (acct / 'history.jsonl').write_text(
        '\n'.join(json.dumps(x) for x in lines), encoding='utf-8')
    got = clientstate.prompt_history('tests', cfgdir=str(acct))
    assert [g['text'] for g in got] == ['write the tests']


def test_prompt_history_is_newest_first(acct):
    lines = [{'display': 'older'}, {'display': 'newer'}]
    (acct / 'history.jsonl').write_text(
        '\n'.join(json.dumps(x) for x in lines), encoding='utf-8')
    assert clientstate.prompt_history(cfgdir=str(acct))[0]['text'] == 'newer'


def test_every_search_term_must_match(acct):
    (acct / 'history.jsonl').write_text(
        json.dumps({'display': 'fix the parser'}), encoding='utf-8')
    assert clientstate.prompt_history('fix parser', cfgdir=str(acct))
    assert not clientstate.prompt_history('fix compiler', cfgdir=str(acct))


# ── daemon and teams ─────────────────────────────────────────

def test_an_empty_worker_roster_is_not_an_error(acct):
    """The common case on every machine that has not opted in."""
    (acct / 'daemon').mkdir()
    (acct / 'daemon' / 'roster.json').write_text(
        json.dumps({'proto': 1, 'supervisorPid': 1, 'workers': {}}), encoding='utf-8')
    got = clientstate.daemon_roster(str(acct))
    assert got['recognised'] is True and got['workers'] == []


def test_a_missing_daemon_reports_unrecognised(acct):
    got = clientstate.daemon_roster(str(acct))
    assert got['recognised'] is False and got['workers'] == []


def test_teams_reports_not_in_use_rather_than_guessing(acct):
    """The docs say a team is named `session-` plus the first 8 characters of
    the session id. On the machine this was written for teams/ is EMPTY and
    tasks/ is keyed by the FULL session uuid — the documented derivation and
    the observed layout already disagree, so nothing is built on it."""
    got = clientstate.teams(str(acct))
    assert got['recognised'] is False
    assert got['teams'] == [] and got['tasks'] == []


def test_task_dirs_are_reported_as_themselves_not_joined_to_a_team(acct):
    sid = '00739a27-d462-4412-8dfb-eaeb3d4f15de'
    (acct / 'tasks' / sid).mkdir(parents=True)
    (acct / 'tasks' / sid / '.highwatermark').write_text('4', encoding='utf-8')
    got = clientstate.teams(str(acct))
    assert got['recognised'] is True
    assert got['tasks'] == [{'session': sid, 'highwater': '4'}]
    assert got['teams'] == [], 'a task dir must not invent a team'


# ── disk ─────────────────────────────────────────────────────

def test_the_disk_report_measures_the_stores_that_grow(acct, monkeypatch):
    from claude_sessions import config
    monkeypatch.setattr(config, 'all_config_dirs', lambda: [('a', str(acct))])
    (acct / 'projects' / 'D--x').mkdir(parents=True)
    (acct / 'projects' / 'D--x' / 's.jsonl').write_text('x' * 5000, encoding='utf-8')
    r = clientstate.disk_report()
    store = {s['name']: s for s in r['accounts'][0]['stores']}
    assert store['projects']['bytes'] >= 5000
    assert store['projects']['files'] == 1
    assert r['bytes'] >= 5000


# ── disk GC ──────────────────────────────────────────────────

def _old(p, days):
    t = time.time() - days * 86400
    os.utime(p, (t, t))


def test_the_gc_is_a_dry_run_by_default(acct):
    proj = acct / 'projects' / 'D--x'
    proj.mkdir(parents=True)
    f = proj / 'aaaa.jsonl'
    f.write_text('x' * 100, encoding='utf-8')
    _old(f, 400)
    r = diskgc.run(days=30, cfgdir=str(acct))
    assert r['files'] == 1 and r['applied'] is False
    assert f.exists(), 'a report must not delete anything'


def test_applying_deletes_only_what_was_reported(acct):
    proj = acct / 'projects' / 'D--x'
    proj.mkdir(parents=True)
    old, new = proj / 'aaaa.jsonl', proj / 'bbbb.jsonl'
    old.write_text('x' * 100, encoding='utf-8')
    new.write_text('y' * 100, encoding='utf-8')
    _old(old, 400)
    diskgc.run(days=30, apply=True, cfgdir=str(acct))
    assert not old.exists()
    assert new.exists()


def test_a_named_session_is_never_deleted(acct):
    """archeus's own state points at it: deleting the transcript breaks
    archeus, not just Claude Code."""
    proj = acct / 'projects' / 'D--x'
    proj.mkdir(parents=True)
    f = proj / 'aaaa.jsonl'
    f.write_text('x' * 100, encoding='utf-8')
    (proj / 'aaaa.name').write_text('the important one', encoding='utf-8')
    _old(f, 400)
    r = diskgc.run(days=30, apply=True, cfgdir=str(acct))
    assert f.exists(), 'a session the user named was deleted'
    assert r['kept'] >= 1


def test_a_tagged_session_is_never_deleted(acct):
    proj = acct / 'projects' / 'D--x'
    proj.mkdir(parents=True)
    f = proj / 'aaaa.jsonl'
    f.write_text('x' * 100, encoding='utf-8')
    (proj / 'tags.json').write_text(json.dumps({'aaaa': ['keep']}), encoding='utf-8')
    _old(f, 400)
    diskgc.run(days=30, apply=True, cfgdir=str(acct))
    assert f.exists()


def test_the_sidecars_are_not_swept_with_the_transcripts(acct):
    """projects/ is pruned per FILE: the same folders hold the names, tags,
    extra paths and system prompts archeus writes."""
    proj = acct / 'projects' / 'D--x'
    proj.mkdir(parents=True)
    sp = proj / 'system-prompt.txt'
    sp.write_text('prompt', encoding='utf-8')
    _old(sp, 400)
    diskgc.run(days=30, apply=True, cfgdir=str(acct))
    assert sp.exists()


def test_the_gc_refuses_to_delete_outside_the_account(acct, tmp_path):
    outside = tmp_path / 'not-an-account.txt'
    outside.write_text('x', encoding='utf-8')
    diskgc._remove(str(outside), str(acct))
    assert outside.exists()


def test_the_gc_follows_the_users_own_cleanup_policy(acct):
    (acct / 'settings.json').write_text(
        json.dumps({'cleanupPeriodDays': 7}), encoding='utf-8')
    assert diskgc.policy_days(str(acct)) == 7


# ── hook events ──────────────────────────────────────────────

def test_all_thirty_one_hook_events_are_modelled():
    """It knew 18, so a hook configured by hand in one of the other 13 was
    invisible in a screen that claimed to list them."""
    assert len(hooks.EVENTS) == 31
    for name in ('PostToolUseFailure', 'StopFailure', 'InstructionsLoaded',
                 'ConfigChange', 'CwdChanged', 'DirectoryAdded', 'TeammateIdle',
                 'Elicitation', 'ElicitationResult', 'Setup',
                 'UserPromptExpansion', 'MessageDisplay', 'PostToolBatch'):
        assert name in hooks.EVENTS, name


def test_every_event_declares_what_its_matcher_means():
    assert set(hooks.EVENT_MATCHERS) == hooks.EVENTS
    assert hooks.EVENT_MATCHERS['PreToolUse'] == 'tool name'
    assert hooks.EVENT_MATCHERS['CwdChanged'] == '', 'this event takes no matcher'


def test_every_template_targets_a_real_event():
    for name, t in hooks.TEMPLATES.items():
        assert t['event'] in hooks.EVENTS, '%s -> %s' % (name, t['event'])


# ── settings editor ──────────────────────────────────────────

def test_a_setting_round_trips_into_the_account_it_names(acct):
    ok, _m = ccsettings.write('effortLevel', 'high', str(acct))
    assert ok
    assert ccsettings.read(str(acct))['effortLevel'] == 'high'
    assert json.loads((acct / 'settings.json').read_text(
        encoding='utf-8'))['effortLevel'] == 'high'


def test_editing_one_key_leaves_every_other_alone(acct):
    """The same file carries hooks, permissions and plugin state."""
    (acct / 'settings.json').write_text(json.dumps(
        {'hooks': {'Stop': [{'hooks': []}]}, 'permissions': {'allow': ['Bash']},
         'somethingNew': 42}), encoding='utf-8')
    ccsettings.write('alwaysThinkingEnabled', True, str(acct))
    back = json.loads((acct / 'settings.json').read_text(encoding='utf-8'))
    assert back['hooks'] == {'Stop': [{'hooks': []}]}
    assert back['permissions'] == {'allow': ['Bash']}
    assert back['somethingNew'] == 42
    assert back['alwaysThinkingEnabled'] is True


def test_clearing_removes_the_key_rather_than_writing_a_default(acct):
    """`False` and absent mean different things, and pinning a literal freezes
    behaviour against a future change in what the default means — the lesson
    outputStyle:'default' already taught this codebase."""
    ccsettings.write('alwaysThinkingEnabled', False, str(acct))
    assert 'alwaysThinkingEnabled' in ccsettings.read(str(acct))
    ccsettings.write('alwaysThinkingEnabled', '', str(acct))
    assert 'alwaysThinkingEnabled' not in ccsettings.read(str(acct))


@pytest.mark.parametrize('key,value', [
    ('effortLevel', 'turbo'),          # not in the enum
    ('cleanupPeriodDays', 'soon'),     # not a number
    ('alwaysThinkingEnabled', 'maybe'),
    ('env', '{not json'),
    ('env', '"a string"'),             # valid JSON, wrong shape
])
def test_a_wrongly_typed_value_is_refused(acct, key, value):
    """This file is parsed by Claude Code; a bad value is a startup error the
    user sees instead of their session."""
    ok, msg = ccsettings.write(key, value, str(acct))
    assert not ok and msg
    assert key not in ccsettings.read(str(acct))


def test_an_unknown_key_is_refused(acct):
    ok, _m = ccsettings.write('rmRfEverything', True, str(acct))
    assert not ok


def test_a_list_setting_accepts_what_a_person_would_type(acct):
    ccsettings.write('availableModels', 'sonnet, opus\nhaiku', str(acct))
    assert ccsettings.read(str(acct))['availableModels'] == ['sonnet', 'opus', 'haiku']


def test_a_nested_key_never_clobbers_its_siblings(tmp_path, monkeypatch):
    """`permissions.defaultMode` lives in the same block as the allow/deny/ask
    rules health.propose_allowlist and denygen write. A flat `s[key]=value`
    would replace the whole block with one key."""
    import json
    acct = tmp_path / 'acct'
    acct.mkdir()
    (acct / 'settings.json').write_text(json.dumps({
        'permissions': {'allow': ['Bash(git status:*)'], 'deny': ['Read(.env)']},
        'model': 'opus'}), encoding='utf-8')

    ok, msg = ccsettings.write('permissions.defaultMode', 'auto', str(acct))
    assert ok, msg
    got = json.loads((acct / 'settings.json').read_text(encoding='utf-8'))
    assert got['permissions'] == {'allow': ['Bash(git status:*)'],
                                  'deny': ['Read(.env)'], 'defaultMode': 'auto'}
    assert got['model'] == 'opus'
    assert ccsettings.read(str(acct))['permissions.defaultMode'] == 'auto'

    # clearing removes only that key, and leaves the block it shares
    ok, _m = ccsettings.write('permissions.defaultMode', '', str(acct))
    assert ok
    got = json.loads((acct / 'settings.json').read_text(encoding='utf-8'))
    assert got['permissions'] == {'allow': ['Bash(git status:*)'], 'deny': ['Read(.env)']}
    assert 'permissions.defaultMode' not in ccsettings.read(str(acct))


def test_clearing_a_nested_key_prunes_a_block_it_emptied(tmp_path):
    """An empty `"permissions": {}` is noise archeus put there and should
    take back — but only when archeus is what created it."""
    import json
    acct = tmp_path / 'acct'
    acct.mkdir()
    (acct / 'settings.json').write_text('{}', encoding='utf-8')
    ccsettings.write('permissions.defaultMode', 'plan', str(acct))
    ccsettings.write('permissions.defaultMode', '', str(acct))
    assert json.loads((acct / 'settings.json').read_text(encoding='utf-8')) == {}


def test_the_enum_refuses_a_mode_claude_code_does_not_have(tmp_path):
    acct = tmp_path / 'acct'
    acct.mkdir()
    ok, msg = ccsettings.write('permissions.defaultMode', 'yolo', str(acct))
    assert not ok and 'expected one of' in msg
    # and the real ones are all accepted
    for mode in ('default', 'manual', 'acceptEdits', 'plan', 'auto',
                 'dontAsk', 'bypassPermissions'):
        assert ccsettings.write('permissions.defaultMode', mode, str(acct))[0], mode


def test_fallback_model_is_a_chain_not_a_string(tmp_path):
    """The docs specify an array — declared as 'str' it could only ever hold
    one model, which is not a fallback CHAIN."""
    acct = tmp_path / 'acct'
    acct.mkdir()
    ccsettings.write('fallbackModel', 'claude-sonnet-5, claude-haiku-4-5', str(acct))
    assert ccsettings.read(str(acct))['fallbackModel'] == \
        ['claude-sonnet-5', 'claude-haiku-4-5']


def test_nothing_writes_claude_code_state():
    """`.claude.json`, the daemon roster and the teams directory belong to
    Claude Code. archeus reads them and must never write one.

    A static gate, not a runtime snapshot: the conftest fixture that used to
    watch `.claude.json` could not tell a test's write from the live Claude Code
    session's, and its remedy — restoring the pre-test bytes — would roll that
    session's own state back. Proving there is no writer is both stronger and
    immune to what else is running on the machine. Same discipline as
    `checkpoints.test_nothing_here_writes`.
    """
    import inspect
    from claude_sessions import clientstate
    src = inspect.getsource(clientstate)
    for w in ("'w'", '"w"', 'os.remove', 'os.unlink', 'os.rename',
              'shutil.copy', 'shutil.move', 'shutil.rmtree'):
        assert w not in src, f'clientstate must not write: found {w!r}'
    # the one write it IS allowed is its own cache, through the atomic helper
    assert src.count('write_json_atomic') <= 1


def test_a_corrupt_claude_json_is_not_quarantined(monkeypatch, tmp_path):
    """Moving a file aside is right for a file archeus owns — the next write
    would destroy the evidence. `.claude.json` is Claude Code's and is rewritten
    constantly, so an unparseable read most likely caught a live write in
    flight; renaming it out from under a running session is far worse than
    reading it again next tick."""
    from claude_sessions import clientstate, jsonstore
    p = tmp_path / '.claude.json'
    p.write_text('{"projects": {"a": ', encoding='utf-8')      # truncated
    monkeypatch.setattr(clientstate, '_path', lambda name, cfgdir=None: str(p))
    assert clientstate.client_json() == {}
    assert p.is_file(), 'the live file was moved aside'
    assert not list(tmp_path.glob('*.corrupt-*'))
