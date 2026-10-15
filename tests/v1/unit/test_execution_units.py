"""P11, the pure half (p11-design-gate §11, §8.2, §10, §19, D16): the action
canonicaliser, the execution state table, the hook's protocol, redaction, and
the branch/host slot P9 left for the action stage."""

import contextlib
import errno
import json
import os
import stat
import threading
import time

import pytest

from archeus.core.application import executions as X
from archeus.core.domain import actions, entities, ids, states
from archeus.core.domain.actions import Action
from archeus.core.execution import canonical as C
from archeus.core.execution.manager import redact
from archeus.core.policy import rules
from archeus.harnesses import hook

WD = os.path.abspath('workspace-root')
CTX = {'workdir': WD, 'branch': 'archeus/m/t', 'remotes': {'origin': 'github.com'}}


def one(tool, inp, ctx=CTX):
    got, unclassified = C.canonicalise(tool, inp, ctx)
    return [a.canonical_dict() for a in got], unclassified


# ── U-C canonicalisation: every row of §11 ──────────────────────────────────

@pytest.mark.parametrize('tool,inp,cls', [
    ('Read', {'file_path': 'src/a.py'}, 'read'),
    ('Glob', {'path': 'src'}, 'read'),
    ('Grep', {'path': '.'}, 'read'),
    ('Write', {'file_path': 'src/a.py'}, 'write_repo'),
    ('Edit', {'file_path': 'src/a.py'}, 'write_repo'),
    ('MultiEdit', {'file_path': 'src/a.py'}, 'write_repo'),
    ('NotebookEdit', {'notebook_path': 'n.ipynb'}, 'write_repo'),
    ('WebFetch', {'url': 'https://example.com/a'}, 'web'),
    ('WebSearch', {'query': 'x'}, 'web'),
])
def test_the_file_and_web_tools(tool, inp, cls):
    (a,), u = one(tool, inp)
    assert a['class'] == cls and u is False


@pytest.mark.parametrize('cmd,cls', [
    ('git status', 'read'), ('git log --oneline', 'read'), ('git diff', 'read'),
    ('git add -A', 'write_repo'), ('git checkout -b x', 'write_repo'),
    ('git commit -m "a; b"', 'git_commit'), ('git push origin main', 'git_push'),
    ('git reset --hard HEAD~1', 'destructive'), ('git clean -fd', 'destructive'),
    ('git branch -D old', 'destructive'), ('git fetch origin', 'web'),
    ('rm -rf build', 'destructive'), ('rm -r build', 'destructive'), ('rm a.txt', 'write_repo'),
    ('terraform destroy -auto-approve', 'destructive'), ('kubectl delete pod x', 'destructive'),
    ('terraform apply', 'deploy'), ('npm publish', 'deploy'), ('vercel --prod', 'deploy'),
    ('docker push img', 'deploy'), ('pip install requests', 'install'),
    ('npm install left-pad', 'install'), ('curl https://example.com', 'web'),
    ('curl -X POST https://api.example.com', 'external_comm'),
    ('curl -d x=1 https://api.example.com', 'external_comm'),
    ('ssh user@host.example ls', 'external_comm'), ('ls -la', 'read'), ('cat a.txt', 'read'),
    ('find . -name x', 'read'), ('find . -delete', 'write_repo'), ('mv a b', 'write_repo'),
    ('pytest -q', 'exec'), ('make build', 'exec'), ('python tool.py', 'exec'),
])
def test_the_bash_table(cmd, cls):
    got, u = one('Bash', {'command': cmd})
    assert got[0]['class'] == cls and u is False, got
    assert got[0]['argv'][0] in cmd


@pytest.mark.parametrize('cmd', [
    'git status | cat', 'ls; rm -rf /', 'a && b', 'a || b', 'echo x > f', 'cat < f',
    'echo $(whoami)', 'echo `whoami`', 'echo "$(rm -rf /)"', 'cp a $HOME/x', 'eval x',
    'bash -c "rm -rf /"', 'sh -c ls', 'python -c "import os"', 'node -e 1', 'sudo rm x',
    'base64 -d payload', 'echo "unterminated', 'X=1 make', 'env A=1 ls', 'xargs rm', '',
    'source ./x.sh', 'nohup evil &',
])
def test_operators_payloads_and_ambiguity_are_unclassified(cmd):
    got, u = one('Bash', {'command': cmd})
    assert u is True and [a['class'] for a in got] == ['exec'], (cmd, got)


def test_an_unknown_tool_is_unclassified():
    got, u = one('SomeNewTool', {'x': 1})
    assert u is True and got[0]['class'] == 'exec'


def test_paths_inside_are_workspace_relative_and_outside_stay_absolute():
    assert one('Write', {'file_path': 'src/a.py'})[0][0]['paths'] == ['src/a.py']
    for escape in ('../x', os.path.abspath(os.sep + 'etc'), '~/x', 'src/../../x'):
        p = one('Write', {'file_path': escape})[0][0]['paths'][0]
        assert not rules.inside(p, '@workspace/**'), (escape, p)
    assert rules.inside(one('Write', {'file_path': 'src/a.py'})[0][0]['paths'][0],
                        '@workspace/**')


def test_git_names_its_branch_and_host_and_a_forced_push_is_also_destructive():
    (push,), _ = one('Bash', {'command': 'git push origin feature'})
    assert (push['branch'], push['host']) == ('feature', 'github.com')
    (commit,), _ = one('Bash', {'command': 'git commit -m x'})
    assert commit['branch'] == 'archeus/m/t'
    got, _ = one('Bash', {'command': 'git push --force origin main'})
    assert [a['class'] for a in got] == ['git_push', 'destructive']
    got, _ = one('Bash', {'command': 'git push origin :main'})
    assert [a['class'] for a in got] == ['git_push', 'destructive']


def test_an_environment_is_named_only_where_the_command_names_it():
    assert one('Bash', {'command': 'vercel --prod'})[0][0]['environment'] == 'prod'
    assert 'environment' not in one('Bash', {'command': 'terraform destroy'})[0][0]


def test_quoted_operators_are_text():
    got, u = one('Bash', {'command': "git commit -m 'a | b; c > d'"})
    assert u is False and got[0]['class'] == 'git_commit'


def test_the_canonicaliser_reads_nothing_but_its_arguments():
    before = json.dumps(CTX, sort_keys=True)
    one('Bash', {'command': 'git push origin main'})
    assert json.dumps(CTX, sort_keys=True) == before


# ── D16: branch and host in the action, its hash, and P9's matching ─────────

def _bind():
    return actions.binding(mission_id=ids.new_id('mission'), plan_id=ids.new_id('plan'),
                           plan_version=1, plan_digest='d' * 64, task_id=ids.new_id('task'),
                           task_key='t', execution_id=ids.new_id('execution'))


def test_branch_and_host_are_part_of_what_an_approval_covers():
    b = _bind()
    base = Action(action_class='git_push', target='origin', branch='main', host='github.com')
    h = actions.action_hash('action', b, [actions.item('t', base)])
    for other in (Action(action_class='git_push', target='origin', branch='dev',
                         host='github.com'),
                  Action(action_class='git_push', target='origin', branch='main',
                         host='evil.example')):
        assert actions.action_hash('action', b, [actions.item('t', other)]) != h


def test_p9_matches_branch_and_host_rules_at_the_action_stage():
    allow = rules.rule(id='r', scope_level='USER', action_class='git_push', decision='ALLOW',
                       match={'branch_glob': 'archeus/*', 'host_glob': 'github.com'})
    # the task branch P11 names is one segment under archeus/ (§17), which is what
    # the profiles' `archeus/*` boundary reaches
    ok = Action(action_class='git_push', target='o', branch='archeus/msn_x.t1',
                host='github.com')
    assert rules.matches(allow, ok)
    assert not rules.matches(allow, Action(action_class='git_push', target='o',
                                           branch='main', host='github.com'))
    # an action that names no branch never meets a permissive branch rule (P9 D3)
    assert not rules.matches(allow, Action(action_class='git_push', target='o'))
    box = rules.check_boundary({'branches': ['archeus/*']}, ok, 'action')
    assert box['checked'] == ['branches'] and not box['outside']


# ── §8.2: the execution machine is P1's plus exactly six edges ──────────────

P1_EXECUTION = {
    ('INTENT', 'STARTING', 'spawn'), ('INTENT', 'ABANDONED', 'spawn_failed'),
    ('INTENT', 'LOST', 'spawn_unconfirmed'), ('STARTING', 'RUNNING', 'first_output'),
    ('STARTING', 'LOST', 'start_timeout'), ('RUNNING', 'AWAITING_APPROVAL', 'hook_asked'),
    ('AWAITING_APPROVAL', 'STARTING', 'resume_approved'),
    ('AWAITING_APPROVAL', 'ENDED_REJECTED', 'rejected'),
    ('RUNNING', 'PAUSING', 'pause_requested'), ('PAUSING', 'PAUSED', 'halted_at_boundary'),
    ('PAUSING', 'STOPPING', 'pause_timeout'), ('PAUSED', 'STARTING', 'resume'),
    ('RUNNING', 'HANDING_OFF', 'pressure_or_account_change'),
    ('HANDING_OFF', 'ENDED_HANDOFF', 'checkpoint_written'), ('RUNNING', 'STOPPING', 'stop'),
    ('STOPPING', 'ENDED_KILLED', 'process_gone'), ('RUNNING', 'ENDED_OK', 'exited_success'),
    ('RUNNING', 'ENDED_ERROR', 'exited_error'), ('RUNNING', 'LOST', 'heartbeat_missing'),
    ('LOST', 'RUNNING', 'adopted'), ('LOST', 'ENDED_KILLED', 'reconciled_kill')}
D8 = {('STARTING', 'STOPPING', 'stop'), ('PAUSING', 'STOPPING', 'stop'),
      ('PAUSING', 'ENDED_OK', 'exited_success'), ('PAUSING', 'ENDED_ERROR', 'exited_error'),
      ('PAUSED', 'ENDED_KILLED', 'discarded'), ('AWAITING_APPROVAL', 'ENDED_KILLED', 'discarded')}


#: P12's hand-off edges (p12-design-gate D20): the user's request, work that
#: finished before the boundary, a stop while handing off
P12_HANDOFF = {('RUNNING', 'HANDING_OFF', 'user_handoff'),
               ('HANDING_OFF', 'ENDED_OK', 'exited_success'),
               ('HANDING_OFF', 'ENDED_ERROR', 'exited_error'),
               ('HANDING_OFF', 'STOPPING', 'stop')}


def test_the_execution_machine_is_p1s_plus_exactly_the_six_p11_edges():
    got = {(a, b, t) for a, b, t, _g in states.edges('execution') if t is not None}
    assert got == P1_EXECUTION | D8 | P12_HANDOFF
    assert set(states.states('execution')) == {s for e in P1_EXECUTION for s in e[:2]}


def test_the_task_and_mission_machines_did_not_change():
    task = {(a, b, t) for a, b, t, _g in states.edges('task') if t is not None}
    assert ('RUNNING', 'PAUSED', 'pause') in task             # kept, unused in V1 (D7)
    assert len(task) == 23


# ── §19 redaction, §12.4 breaker constants, D9 ──────────────────────────────

@pytest.mark.parametrize('secret', ['hook_' + 'a' * 30, 'dev_' + 'b' * 20, 'sk-ant-' + 'c' * 30,
                                    'ghp_' + 'd' * 30, 'github_pat_' + 'e' * 30,
                                    'AKIA' + 'F' * 16, 'Bearer ' + 'g' * 30])
def test_a_secret_never_reaches_an_event(secret):
    out = redact('before %s after' % secret)
    assert secret not in out and '[redacted]' in out


def test_the_breaker_and_the_uncharged_ends_are_the_gates():
    assert (X.STORM, X.STORM_WINDOW_S, X.PERSIST, X.BEAT_S, X.COOLDOWN_S) == (5, 600, 2, 60, 300)
    assert set(X.UNCHARGED) == {'user', 'estop', 'ceiling', 'limit', 'breaker',
                                'pause_timeout', 'cancel', 'binding', 'disarmed',
                                # P12: a hand-off spends no attempt (p12-design-gate D20)
                                'pressure', 'handoff_user'}
    # P11 §28 note 11: a workspace that cannot be made is the task's own end
    assert set(entities.STOP_REASONS) - set(X.UNCHARGED) == {'workspace'}


# ── §10 the hook's protocol, without a process ──────────────────────────────

def test_the_hook_speaks_claude_codes_vocabulary():
    assert hook.decision('allow') == {'hookSpecificOutput': {
        'hookEventName': 'PreToolUse', 'permissionDecision': 'allow'}}
    # a halt denies the call it answers as well: `continue: false` alone lets
    # Claude Code run it first (P20 PV-19, O4)
    assert hook.decision('halt', 'stop') == {'continue': False, 'stopReason': 'stop',
                                             'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny', 'permissionDecisionReason': 'stop'}}
    # P20 (ADR-0049 §3): a deny is exit code 2 with the reason on stderr, never JSON
    assert hook.answer('deny', 'no') == ('', 'no', 2)
    with pytest.raises(ValueError):
        hook.decision('deny', 'no')


def test_the_hook_asks_through_the_mailbox_and_honours_the_answer(tmp_path):
    eid = ids.new_id('execution')
    env = {'ARCHEUS_HOME': str(tmp_path), 'ARCHEUS_EXECUTION_ID': eid,
           'ARCHEUS_HOOK_TOKEN': 'hook_t'}
    box = os.path.join(str(tmp_path), 'run', 'exec', eid, 'hook')

    def core():
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if os.path.exists(os.path.join(box, '1.req.json')):
                req = json.load(open(os.path.join(box, '1.req.json')))
                assert (req['token'], req['tool'], req['seq']) == ('hook_t', 'Read', 1)
                with open(os.path.join(box, '1.res.json'), 'w') as f:
                    json.dump({'decision': 'deny', 'reason': 'not today'}, f)
                return
            time.sleep(0.02)
    t = threading.Thread(target=core)
    t.start()
    assert hook.run({'tool_name': 'Read', 'tool_input': {'file_path': 'a'}}, env) == (
        'deny', 'not today')
    t.join()


def test_a_flag_or_the_sentinel_halts_before_asking(tmp_path):
    eid = ids.new_id('execution')
    env = {'ARCHEUS_HOME': str(tmp_path), 'ARCHEUS_EXECUTION_ID': eid,
           'ARCHEUS_HOOK_TOKEN': 'hook_t'}
    d = os.path.join(str(tmp_path), 'run', 'exec', eid)
    os.makedirs(d)
    open(os.path.join(d, 'PAUSE'), 'w').close()
    assert hook.run({'tool_name': 'Read'}, env)[0] == 'halt'
    assert not os.path.exists(os.path.join(d, 'hook'))
    assert os.path.exists(os.path.join(d, 'halted.json'))


# ── PV-20 §7.4 Gap A: a sentinel is present, absent or indeterminate ────────

PRESENT = {'estop': 'emergency stop', 'STOP': 'stopped by Archeus',
           'PAUSE': 'paused by Archeus', 'HANDOFF': 'handing off to a fresh session',
           'estop-wait': 'emergency stop'}


def _allow(box):
    with open(os.path.join(box, '1.res.json'), 'w', encoding='utf-8') as f:
        json.dump({'decision': 'allow'}, f)


@contextlib.contextmanager
def _core(box, on_request):
    """Core doing *on_request* once the first request is in the mailbox: with
    `_allow`, a hook that ignores a sentinel visibly proceeds instead of waiting
    out WAIT_S."""
    done = threading.Event()

    def core():
        req = os.path.join(box, '1.req.json')
        while not done.wait(0.01):
            if os.path.exists(req):
                on_request()
                return
    t = threading.Thread(target=core)
    t.start()
    try:
        yield
    finally:
        done.set()
        t.join()


def _hook_with(tmp_path, monkeypatch, read, outcome):
    """The hook with *outcome* injected at one of its five sentinel reads: the
    estop before the request, the STOP / PAUSE / HANDOFF flag, or the estop in
    the wait loop. Only the lookup is injected."""
    eid = ids.new_id('execution')
    home = str(tmp_path)
    env = {'ARCHEUS_HOME': home, 'ARCHEUS_EXECUTION_ID': eid, 'ARCHEUS_HOOK_TOKEN': 'hook_t'}
    d = os.path.join(home, 'run', 'exec', eid)
    os.makedirs(d)
    estop = os.path.join(home, 'run', 'STOP')
    target = estop if read.startswith('estop') else os.path.join(d, read)
    real_lstat, real_stat = os.lstat, os.stat
    estop_reads = []

    def lstat(p, *a, **kw):
        p = os.fspath(p)
        hit = p == target
        if p == estop:
            estop_reads.append(p)
            if read.startswith('estop'):
                hit = (len(estop_reads) > 1) == (read == 'estop-wait')
        if hit:
            if outcome == 'dangling':
                return os.stat_result((stat.S_IFLNK | 0o777,) + (0,) * 9)
            elif outcome == 'denied':
                raise PermissionError(errno.EACCES, 'Access is denied', p)
            elif outcome == 'oserror':
                raise OSError(errno.EIO, 'I/O error', p)
        return real_lstat(p, *a, **kw)

    def follow(p, *a, **kw):
        # what following a dangling link gives: the name it points at is missing
        if outcome == 'dangling' and os.fspath(p) == target:
            raise FileNotFoundError(errno.ENOENT, 'the link target is missing', p)
        return real_stat(p, *a, **kw)

    box = os.path.join(d, 'hook')

    def on_request():
        if outcome == 'present' and read == 'estop-wait':
            open(estop, 'w').close()        # the estop appears while the hook waits
        else:
            _allow(box)
    if outcome == 'present' and read != 'estop-wait':
        open(target, 'w').close()
    monkeypatch.setattr(os, 'lstat', lstat)
    monkeypatch.setattr(os, 'stat', follow)
    with _core(box, on_request):
        return hook.run({'tool_name': 'Read'}, env), d


@pytest.mark.parametrize('outcome', ['absent', 'present', 'dangling', 'denied', 'oserror'])
@pytest.mark.parametrize('read', list(PRESENT))
def test_each_sentinel_read_is_present_absent_or_indeterminate(tmp_path, monkeypatch, read,
                                                               outcome):
    (kind, why), d = _hook_with(tmp_path, monkeypatch, read, outcome)
    asked = os.path.exists(os.path.join(d, 'hook', '1.req.json'))
    halted = os.path.join(d, 'halted.json')
    if outcome == 'absent':
        assert (kind, why) == ('allow', '')
        assert asked and not os.path.exists(halted)
        return
    assert kind == 'halt'
    if outcome in ('present', 'dangling'):
        assert why == PRESENT[read]
    else:
        # a distinct reason naming the sentinel, never the present one's
        name = 'emergency stop' if read.startswith('estop') else read + ' flag'
        assert why == "cannot determine the %s's state; halted (fail closed)" % name
    assert asked == (read == 'estop-wait')
    with open(halted, encoding='utf-8') as f:
        record = json.load(f)
    assert (record['seq'], record['reason']) == ((1 if read == 'estop-wait' else None), why)


def test_an_undeterminable_estop_halts_while_the_mailbox_stays_writable(tmp_path, monkeypatch):
    """PV-20 acceptance row 7's case: the sentinel cannot be read and the
    mailbox beside it can be written. The two-state read called that absent,
    and only a mailbox write failing next to it ever halted; the halt now comes
    from the determination."""
    eid = ids.new_id('execution')
    home = str(tmp_path)
    env = {'ARCHEUS_HOME': home, 'ARCHEUS_EXECUTION_ID': eid, 'ARCHEUS_HOOK_TOKEN': 'hook_t'}
    d = os.path.join(home, 'run', 'exec', eid)
    box = os.path.join(d, 'hook')
    os.makedirs(box)
    estop = os.path.join(home, 'run', 'STOP')

    def denied(real):
        def lookup(p, *a, **kw):
            if os.fspath(p) == estop:
                raise PermissionError(errno.EACCES, 'Access is denied', p)
            return real(p, *a, **kw)
        return lookup

    monkeypatch.setattr(os, 'lstat', denied(os.lstat))
    monkeypatch.setattr(os, 'stat', denied(os.stat))
    assert not os.path.exists(estop)
    probe = os.path.join(box, 'probe')
    open(probe, 'w').close()
    os.remove(probe)
    with _core(box, lambda: _allow(box)):
        kind, why = hook.run({'tool_name': 'Read'}, env)
    assert (kind, why) == ('halt', "cannot determine the emergency stop's state; halted "
                                   "(fail closed)")
    assert os.listdir(box) == []
    with open(os.path.join(d, 'halted.json'), encoding='utf-8') as f:
        assert json.load(f)['reason'] == why


def test_concurrent_hooks_take_distinct_sequence_numbers(tmp_path):
    box = str(tmp_path)
    seqs = []
    ts = [threading.Thread(target=lambda: seqs.append(hook._reserve(box, {'x': 1})))
          for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(seqs) == list(range(1, 9))
