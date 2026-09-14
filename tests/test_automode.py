"""Auto mode: the settings block, and the denial log that feeds it.

The `"$defaults"` sentinel is the thing worth guarding hardest. Writing
`autoMode.environment` (or allow/soft_deny/hard_deny) without it REPLACES the
entire built-in list for that section — dropping it from soft_deny silently
discards the force-push, `curl | bash` and production-deploy rules. Nothing in
the file would look wrong afterwards.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox
from claude_sessions import automode, ccsettings, hooks


def _acct(tmp_path, initial=None):
    d = tmp_path / 'acct'
    d.mkdir(exist_ok=True)
    (d / 'settings.json').write_text(json.dumps(initial or {}), encoding='utf-8')
    return str(d)


def _read(cfgdir):
    return json.loads(open(os.path.join(cfgdir, 'settings.json'), encoding='utf-8').read())


# ── the settings block ───────────────────────────────────────

def test_environment_keeps_the_defaults_sentinel(tmp_path):
    """Without "$defaults" the classifier stops trusting even the working
    repo's own remotes, and every built-in trust slot is gone."""
    cfg = _acct(tmp_path)
    ok, _m = automode.set_environment(
        ['Source control: github.example.com/acme', 'Trusted buckets: s3://acme'], cfg)
    assert ok
    env = _read(cfg)['autoMode']['environment']
    assert env[0] == '$defaults', env
    assert env[1:] == ['Source control: github.example.com/acme',
                       'Trusted buckets: s3://acme']
    assert automode.environment(cfg) == env


def test_a_caller_cannot_drop_the_sentinel_by_passing_it_itself(tmp_path):
    """It is added, never echoed — otherwise a UI that round-trips the list
    would end up with it twice, or (worse) reorder it away from the front."""
    cfg = _acct(tmp_path)
    automode.set_environment(['$defaults', 'a', '$defaults', 'a', 'b'], cfg)
    assert _read(cfg)['autoMode']['environment'] == ['$defaults', 'a', 'b']


def test_clearing_the_environment_removes_the_block(tmp_path):
    cfg = _acct(tmp_path, {'model': 'opus'})
    automode.set_environment(['x'], cfg)
    automode.set_environment([], cfg)
    got = _read(cfg)
    assert 'autoMode' not in got          # no empty husk left behind
    assert got['model'] == 'opus'         # and nothing else was touched


def test_the_environment_never_disturbs_other_automode_keys(tmp_path):
    """`allow`/`soft_deny`/`hard_deny` live in the same block and are read by
    the classifier independently."""
    cfg = _acct(tmp_path, {'autoMode': {'classifyAllShell': True,
                                        'soft_deny': ['$defaults', 'no migrations']}})
    automode.set_environment(['Org: acme'], cfg)
    am = _read(cfg)['autoMode']
    assert am['classifyAllShell'] is True
    assert am['soft_deny'] == ['$defaults', 'no migrations']
    assert am['environment'] == ['$defaults', 'Org: acme']


def test_default_mode_round_trips_through_the_typed_editor(tmp_path):
    cfg = _acct(tmp_path, {'permissions': {'allow': ['Bash(ls:*)']}})
    assert automode.default_mode(cfg) == ''
    ok, _m = automode.set_default_mode('auto', cfg)
    assert ok
    assert automode.default_mode(cfg) == 'auto'
    assert _read(cfg)['permissions']['allow'] == ['Bash(ls:*)']
    # validated, because this file is parsed by Claude Code at startup
    assert not automode.set_default_mode('turbo', cfg)[0]


# ── denials ──────────────────────────────────────────────────

def test_a_denial_records_the_tool_not_only_the_command(tmp_path):
    """The old hook wrote `tool_input.command` into the bash log, so a denied
    Read or WebFetch left no trace at all and a denied Bash was
    indistinguishable from one that ran."""
    p = str(tmp_path)
    assert automode.record(p, 'Bash', 'git push --force', 'Blocked by classifier')
    assert automode.record(p, 'Read', '/home/x/.env', '')
    got = automode.denials(p)
    assert [d['tool'] for d in got] == ['Read', 'Bash']       # newest first
    assert got[1]['command'] == 'git push --force'
    assert got[1]['reason'] == 'Blocked by classifier'
    assert isinstance(got[0]['ts'], (int, float))


def test_denials_group_by_what_was_blocked(tmp_path):
    """The question is "what keeps getting blocked", which a raw log does not
    answer. Bash groups by the command's first word; every other tool groups by
    itself, because for those the target IS the story."""
    p = str(tmp_path)
    for cmd in ('git push --force a', 'git push --force b', 'git commit --amend'):
        automode.record(p, 'Bash', cmd, 'Blocked by classifier')
    automode.record(p, 'Read', '/x/.env', '')
    groups = {g['key']: g for g in automode.summarise(p)}
    assert groups['Bash:git']['count'] == 3
    assert groups['Read']['count'] == 1
    assert automode.summarise(p)[0]['key'] == 'Bash:git'      # commonest first
    assert len(groups['Bash:git']['samples']) == 3            # capped at 3


def test_no_denial_log_is_an_empty_list_not_an_error(tmp_path):
    assert automode.denials(str(tmp_path)) == []
    assert automode.summarise(str(tmp_path)) == []


def test_the_denial_log_is_bounded(tmp_path):
    """It sits on the turn's critical path and grows forever otherwise — the
    same lesson the bash log already learned at 90 KB."""
    p = str(tmp_path)
    for i in range(4000):
        automode.record(p, 'Bash', 'some fairly long command number %d' % i, 'why')
    assert os.path.getsize(automode.denials_path(p)) <= automode._MAX_BYTES
    # and what survives is still parseable, i.e. the trim landed on a line break
    assert automode.denials(p)


def test_the_hook_records_a_non_bash_denial(tmp_path, monkeypatch):
    """End to end through the hook's own entry point: `--denied` must reach
    automode.record with the tool name, and pick a target field that is not
    `command` when the tool has none."""
    import io
    from claude_sessions import logbash_hook
    payload = {'cwd': str(tmp_path), 'tool_name': 'Read',
               'tool_input': {'file_path': 'C:/secrets/.env'},
               'permission_decision_reason': 'Blocked by classifier'}
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(payload)))
    assert logbash_hook.main(['--denied']) == 0
    got = automode.denials(str(tmp_path))
    assert len(got) == 1
    assert got[0]['tool'] == 'Read'
    assert got[0]['command'] == 'C:/secrets/.env'
    assert got[0]['reason'] == 'Blocked by classifier'
    # and it did NOT go in the bash log, which answers a different question
    assert not os.path.exists(os.path.join(str(tmp_path), '.archeus', 'bash-log.txt'))


def test_the_hook_without_the_flag_is_still_the_bash_log(tmp_path, monkeypatch):
    import io
    from claude_sessions import logbash_hook
    payload = {'cwd': str(tmp_path), 'tool_name': 'Bash',
               'tool_input': {'command': 'pytest -x'}}
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(payload)))
    assert logbash_hook.main([]) == 0
    log = os.path.join(str(tmp_path), '.archeus', 'bash-log.txt')
    assert open(log, encoding='utf-8').read().strip() == 'pytest -x'
    assert automode.denials(str(tmp_path)) == []


def test_the_installed_hook_passes_the_flag():
    """The template and the script have to agree — without --denied the
    PermissionDenied binding silently writes the bash log again."""
    tpl = hooks.TEMPLATES['log-permission-denials']
    cmd = tpl['entry']['hooks'][0]['command']
    assert tpl['event'] == 'PermissionDenied'
    assert cmd.endswith(' --denied'), cmd
    assert 'logbash_hook.py' in cmd
