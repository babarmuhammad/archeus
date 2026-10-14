"""P11, the pure half (p11-design-gate §11, §8.2, §10, §19, D16): the action
canonicaliser, the execution state table, the hook's protocol, redaction, and
the branch/host slot P9 left for the action stage."""

import contextlib
import errno
import io
import json
import os
import stat
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from claude_sessions import config, proc

from archeus.core.application import executions as X
from archeus.core.application import queries
from archeus.core.domain import actions, entities, ids, states
from archeus.core.domain.actions import Action
from archeus.core.execution import canonical as C
from archeus.core.execution.manager import ExecutionManager, redact
from archeus.core.policy import rules
from archeus.harnesses import base, hook
from archeus.infra import paths
from archeus.node.local import LocalNode

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
    d = os.path.join(str(tmp_path), 'run', 'exec', eid)
    box, answers = os.path.join(d, 'req'), os.path.join(d, 'res')
    os.makedirs(answers)

    def core():
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if os.path.exists(os.path.join(box, '1.req.json')):
                req = json.load(open(os.path.join(box, '1.req.json')))
                assert (req['token'], req['tool'], req['seq']) == ('hook_t', 'Read', 1)
                with open(os.path.join(answers, '1.res.json'), 'w') as f:
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
    os.makedirs(os.path.join(d, 'ctl'))
    open(os.path.join(d, 'ctl', 'PAUSE'), 'w').close()
    assert hook.run({'tool_name': 'Read'}, env)[0] == 'halt'
    assert os.listdir(os.path.join(d, 'req')) == ['halted.json']     # reported, never asked


# ── PV-20 §7.4 Gap A: a sentinel is present, absent or indeterminate ────────

PRESENT = {'estop': 'emergency stop', 'STOP': 'stopped by Archeus',
           'PAUSE': 'paused by Archeus', 'HANDOFF': 'handing off to a fresh session',
           'estop-wait': 'emergency stop'}


def _allow(answers):
    with open(os.path.join(answers, '1.res.json'), 'w', encoding='utf-8') as f:
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
    box, answers, flags = (os.path.join(d, n) for n in ('req', 'res', 'ctl'))
    os.makedirs(answers)
    os.makedirs(flags)
    estop = os.path.join(home, 'run', 'STOP')
    target = estop if read.startswith('estop') else os.path.join(flags, read)
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

    def on_request():
        if outcome == 'present' and read == 'estop-wait':
            open(estop, 'w').close()        # the estop appears while the hook waits
        else:
            _allow(answers)
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
    asked = os.path.exists(os.path.join(d, 'req', '1.req.json'))
    halted = os.path.join(d, 'req', 'halted.json')
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
    class-1 directory beside it can be written. The two-state read called that
    absent, and only a mailbox write failing next to it ever halted; the halt now
    comes from the determination."""
    eid = ids.new_id('execution')
    home = str(tmp_path)
    env = {'ARCHEUS_HOME': home, 'ARCHEUS_EXECUTION_ID': eid, 'ARCHEUS_HOOK_TOKEN': 'hook_t'}
    d = os.path.join(home, 'run', 'exec', eid)
    box, answers = os.path.join(d, 'req'), os.path.join(d, 'res')
    os.makedirs(box)
    os.makedirs(answers)
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
    with _core(box, lambda: _allow(answers)):
        kind, why = hook.run({'tool_name': 'Read'}, env)
    assert (kind, why) == ('halt', "cannot determine the emergency stop's state; halted "
                                   "(fail closed)")
    assert os.listdir(box) == ['halted.json']                       # nothing asked
    with open(os.path.join(box, 'halted.json'), encoding='utf-8') as f:
        assert json.load(f)['reason'] == why


def test_concurrent_hooks_take_distinct_sequence_numbers(tmp_path):
    box = str(tmp_path)
    seqs = []
    ts = [threading.Thread(target=lambda: seqs.append(hook._reserve(box, {'x': 1})))
          for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(seqs) == list(range(1, 9))


# ── PV-20 §7.5: one directory per resource class (S2-L) ──────────────────────

def _hook_env(tmp_path, eid):
    return {'ARCHEUS_HOME': str(tmp_path), 'ARCHEUS_EXECUTION_ID': eid,
            'ARCHEUS_HOOK_TOKEN': 'hook_t'}


def test_the_hook_mirrors_the_class_directories_of_the_layout():
    assert (hook.REQUEST_DIR, hook.RESPONSE_DIR, hook.SENTINEL_DIR) == (
        paths.REQUEST_DIR, paths.RESPONSE_DIR, paths.SENTINEL_DIR)


def test_an_answer_beside_the_request_is_never_the_answer(tmp_path, monkeypatch):
    """An answer in class 1 is one the execution could have written itself: the hook
    waits for Core's in class 2, and with none there it halts at its deadline."""
    eid = ids.new_id('execution')
    d = os.path.join(str(tmp_path), 'run', 'exec', eid)
    box = os.path.join(d, 'req')
    os.makedirs(os.path.join(d, 'res'))
    monkeypatch.setattr(hook, 'WAIT_S', 1.0)
    with _core(box, lambda: _allow(box)):
        kind, why = hook.run({'tool_name': 'Read'}, _hook_env(tmp_path, eid))
    assert (kind, why) == ('halt', 'Archeus did not answer; denied and halted (fail closed)')
    with open(os.path.join(box, 'halted.json'), encoding='utf-8') as f:
        assert json.load(f)['seq'] == 1


def test_an_unreadable_class_2_answer_is_never_accepted(tmp_path, monkeypatch):
    """Core's answer is in class 2 and says allow, and the hook cannot read it: no
    answer is accepted, and the hook halts at its deadline with class 1 writable."""
    eid = ids.new_id('execution')
    d = os.path.join(str(tmp_path), 'run', 'exec', eid)
    box, answers = os.path.join(d, 'req'), os.path.join(d, 'res')
    os.makedirs(answers)
    answer = os.path.join(answers, '1.res.json')
    real = open

    def denied(path, *a, **kw):
        if os.fspath(path) == answer:
            raise PermissionError(errno.EACCES, 'Access is denied', path)
        return real(path, *a, **kw)
    monkeypatch.setattr(hook, 'open', denied, raising=False)    # the hook's reads only
    monkeypatch.setattr(hook, 'WAIT_S', 1.0)
    with _core(box, lambda: _allow(answers)):
        kind, why = hook.run({'tool_name': 'Read'}, _hook_env(tmp_path, eid))
    assert (kind, why) == ('halt', 'Archeus did not answer; denied and halted (fail closed)')
    assert os.path.exists(answer)                               # there, and not accepted
    assert os.path.exists(os.path.join(box, '1.req.json'))      # class 1 took the request
    with open(os.path.join(box, 'halted.json'), encoding='utf-8') as f:
        assert json.load(f)['seq'] == 1


def test_an_unwritable_class_1_halts_and_asks_nothing(tmp_path, monkeypatch, capsys):
    eid = ids.new_id('execution')
    d = os.path.join(str(tmp_path), 'run', 'exec', eid)
    os.makedirs(d)
    open(os.path.join(d, 'req'), 'w').close()        # class 1 cannot be a directory
    for k, v in _hook_env(tmp_path, eid).items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv('ARCHEUS_HOOK_ACTIVE', '')     # main() sets it; restored after
    monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps({'tool_name': 'Read'})))
    assert hook.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out['continue'] is False
    assert out['hookSpecificOutput']['permissionDecision'] == 'deny'
    assert sorted(os.listdir(d)) == ['req']


# ── U-4: a mailbox that is there is used without looking at its parent ──────

def _mailbox_present(tmp_path, *others):
    eid = ids.new_id('execution')
    d = os.path.join(str(tmp_path), 'run', 'exec', eid)
    for name in ('req',) + others:
        os.makedirs(os.path.join(d, name))
    return eid, d


def _parent_unreadable(monkeypatch, parent):
    """*parent* refuses its metadata, its listing and its creation, as an
    execution's own directory may while its mailbox is open: every look at it is
    recorded, and so is every `os.makedirs` call."""
    touched, made = [], []
    key = os.path.normcase(os.path.normpath(parent))

    def refuse(name, real):
        def call(p, *a, **kw):
            if (not isinstance(p, int)
                    and os.path.normcase(os.path.normpath(os.fspath(p))) == key):
                touched.append(name)
                raise PermissionError(errno.EACCES, 'Access is denied', p)
            return real(p, *a, **kw)
        return call
    for name in ('stat', 'lstat', 'mkdir', 'listdir'):
        monkeypatch.setattr(os, name, refuse(name, getattr(os, name)))
    real_makedirs = os.makedirs

    def makedirs(p, *a, **kw):
        made.append(os.fspath(p))
        return real_makedirs(p, *a, **kw)
    monkeypatch.setattr(os, 'makedirs', makedirs)
    with pytest.raises(PermissionError):
        os.stat(parent)                 # the refusal is in force for this path
    touched.clear()
    return touched, made


def test_a_present_mailbox_takes_a_request_without_looking_at_its_parent(tmp_path,
                                                                         monkeypatch):
    eid, d = _mailbox_present(tmp_path, 'res')
    box, answers = os.path.join(d, 'req'), os.path.join(d, 'res')
    touched, made = _parent_unreadable(monkeypatch, d)
    with _core(box, lambda: _allow(answers)):
        assert hook.run({'tool_name': 'Read'}, _hook_env(tmp_path, eid)) == ('allow', '')
    assert sorted(os.listdir(box)) == ['1.lock', '1.req.json']
    with open(os.path.join(box, '1.req.json'), encoding='utf-8') as f:
        assert json.load(f)['seq'] == 1
    assert (touched, made) == ([], [])


def test_a_present_mailbox_takes_a_halt_without_looking_at_its_parent(tmp_path,
                                                                      monkeypatch):
    eid, d = _mailbox_present(tmp_path, 'ctl')
    open(os.path.join(d, 'ctl', 'PAUSE'), 'w').close()
    box = os.path.join(d, 'req')
    touched, made = _parent_unreadable(monkeypatch, d)
    assert hook.run({'tool_name': 'Read'}, _hook_env(tmp_path, eid)) == (
        'halt', 'paused by Archeus')
    assert os.listdir(box) == ['halted.json']                       # reported, never asked
    with open(os.path.join(box, 'halted.json'), encoding='utf-8') as f:
        assert json.load(f)['reason'] == 'paused by Archeus'
    assert (touched, made) == ([], [])


def test_a_present_mailbox_takes_a_precompact_without_looking_at_its_parent(tmp_path,
                                                                            monkeypatch):
    eid, d = _mailbox_present(tmp_path)
    box = os.path.join(d, 'req')
    touched, made = _parent_unreadable(monkeypatch, d)
    assert hook.run({'hook_event_name': 'PreCompact', 'trigger': 'auto'},
                    _hook_env(tmp_path, eid)) == ('continue', '')
    assert os.listdir(box) == ['precompact.json']
    with open(os.path.join(box, 'precompact.json'), encoding='utf-8') as f:
        assert json.load(f)['trigger'] == 'auto'
    assert (touched, made) == ([], [])


def test_a_missing_mailbox_is_still_made_for_a_precompact(tmp_path):
    eid = ids.new_id('execution')
    box = os.path.join(str(tmp_path), 'run', 'exec', eid, 'req')
    assert hook.run({'hook_event_name': 'PreCompact', 'trigger': 'manual'},
                    _hook_env(tmp_path, eid)) == ('continue', '')
    assert os.listdir(box) == ['precompact.json']


def test_only_cores_class_2_answer_answers_a_request():
    eid = ids.new_id('execution')
    p = paths.ExecPaths(eid)
    os.makedirs(p.req)
    for name, body in (('1.req.json', '{"tool": "Read"}'), ('2.req.json', 'not json'),
                       ('1.res.json', '{"decision": "allow"}')):     # the execution's own
        with open(os.path.join(p.req, name), 'w', encoding='utf-8') as f:
            f.write(body)
    assert LocalNode.pending_requests(eid) == [(1, {'tool': 'Read'}), (2, None)]
    LocalNode.respond(eid, 1, 'deny', 'no')
    assert os.listdir(p.res) == ['1.res.json']
    assert LocalNode.pending_requests(eid) == [(2, None)]


def test_core_sets_the_flags_in_class_3_only():
    eid = ids.new_id('execution')
    p = paths.ExecPaths(eid)
    LocalNode.set_flag(eid, 'PAUSE')
    assert os.listdir(p.ctl) == ['PAUSE'] and not os.path.exists(p.req)
    LocalNode.clear_flags(eid)
    assert os.listdir(p.ctl) == []


def test_the_precompact_report_is_read_from_class_1():
    eid = ids.new_id('execution')
    p = paths.ExecPaths(eid)
    os.makedirs(p.req)
    assert LocalNode.precompacted(eid) is False
    open(os.path.join(p.req, 'precompact.json'), 'w').close()
    assert LocalNode.precompacted(eid) is True


def test_a_stale_halt_report_core_cannot_remove_starts_nothing(archeus_home, monkeypatch):
    eid = ids.new_id('execution')
    p = paths.ExecPaths(eid)
    halted = base.halted_path(p.dir)
    assert os.path.dirname(halted) == p.req
    os.makedirs(p.req)
    open(halted, 'w').close()
    real = os.remove

    def remove(path, *a, **kw):
        if os.fspath(path) == halted:
            raise PermissionError(errno.EACCES, 'Access is denied', path)
        return real(path, *a, **kw)
    monkeypatch.setattr(os, 'remove', remove)
    started = []
    monkeypatch.setattr(proc, 'spawn_detached', lambda *a, **kw: started.append(a))
    spec = base.ExecutionSpec(execution_id=eid, prompt='go', workdir=str(archeus_home))
    with pytest.raises(base.SpawnFailed, match='halted.json'):
        base.spawn(spec, ['never-run'])
    assert started == []                                    # and nothing unisolated either
    assert 'halted.json' in base.read_json(p.ended)['error']


@pytest.mark.parametrize('isolated', [False, True])
def test_a_stale_report_and_its_tombstone_both_failing_still_start_nothing(
        archeus_home, monkeypatch, isolated):
    eid = ids.new_id('execution')
    p = paths.ExecPaths(eid)
    halted = base.halted_path(p.dir)
    os.makedirs(p.req)
    open(halted, 'w').close()
    real_remove, real_write = os.remove, config.write_json_atomic

    def remove(path, *a, **kw):
        if os.fspath(path) == halted:
            raise PermissionError(errno.EACCES, 'Access is denied', path)
        return real_remove(path, *a, **kw)

    def write(path, *a, **kw):
        return False if os.fspath(path) == p.ended else real_write(path, *a, **kw)
    monkeypatch.setattr(os, 'remove', remove)
    monkeypatch.setattr(config, 'write_json_atomic', write)
    launched = []
    monkeypatch.setattr(proc, 'spawn_detached', lambda *a, **kw: launched.append(a))
    isolation = SimpleNamespace(launch=lambda *a, **kw: launched.append(a)) if isolated else None
    spec = base.ExecutionSpec(execution_id=eid, prompt='go', workdir=str(archeus_home),
                              isolation=isolation)
    with pytest.raises(base.SpawnFailed) as err:
        base.spawn(spec, ['never-run'])
    assert launched == []                       # no process, isolated or otherwise
    assert 'could not remove halted.json' in str(err.value)
    assert 'the ended tombstone was not written: could not write' in str(err.value)
    assert isinstance(err.value.__cause__, PermissionError)
    assert not os.path.exists(p.ended)


def _launch_spec(archeus_home, monkeypatch, isolated, launcher):
    calls = []

    def launch(*a, **kw):
        calls.append(a)
        return launcher()
    monkeypatch.setattr(proc, 'spawn_detached', launch)
    monkeypatch.setattr(proc, 'process_create_time', lambda pid: 1.0)
    spec = base.ExecutionSpec(execution_id=ids.new_id('execution'), prompt='go',
                              workdir=str(archeus_home),
                              isolation=SimpleNamespace(launch=launch) if isolated else None)
    return spec, paths.ExecPaths(spec.execution_id), calls


@pytest.mark.parametrize('tombstone', ['written', 'fails'])
@pytest.mark.parametrize('isolated', [False, True])
def test_a_launch_that_starts_nothing_is_spawnfailed_even_without_its_tombstone(
        archeus_home, monkeypatch, isolated, tombstone):
    spec, p, calls = _launch_spec(archeus_home, monkeypatch, isolated,
                                  lambda: (None, 'the launcher said no'))
    if tombstone == 'fails':
        real_write = config.write_json_atomic
        monkeypatch.setattr(config, 'write_json_atomic', lambda path, *a, **kw: (
            False if os.fspath(path) == p.ended else real_write(path, *a, **kw)))
    with pytest.raises(base.SpawnFailed) as err:
        base.spawn(spec, ['never-run'])
    assert len(calls) == 1                # one launch, no retry, no fallback to the other path
    assert err.value.__cause__ is None    # the launcher's reason is a string, not an exception
    assert not os.path.exists(p.pid)
    if tombstone == 'fails':
        assert str(err.value) == ('the launcher said no; the ended tombstone was not written: '
                                  'could not write %s' % p.ended)
        assert not os.path.exists(p.ended)
    else:
        assert str(err.value) == 'the launcher said no'
        assert base.read_json(p.ended)['error'] == 'the launcher said no'


@pytest.mark.parametrize('isolated', [False, True])
def test_a_launch_that_starts_a_child_still_records_it(archeus_home, monkeypatch, isolated):
    child = SimpleNamespace(pid=4242)
    spec, p, calls = _launch_spec(archeus_home, monkeypatch, isolated, lambda: (child, None))
    handle, got = base.spawn(spec, ['run'])
    assert (handle.pid, got, len(calls)) == (4242, child, 1)
    assert base.read_json(p.pid)['pid'] == 4242 and not os.path.exists(p.ended)


def test_a_project_less_workspace_is_the_executions_own_never_its_core_directory():
    eid = ids.new_id('execution')
    p = paths.ExecPaths(eid)
    workdir, branch = ExecutionManager._workspace(None, SimpleNamespace(id=eid),
                                                  SimpleNamespace(project_id=None), None,
                                                  isolated=False)
    assert (workdir, branch) == (p.work, None) and os.path.isdir(workdir)
    assert workdir != p.dir
    assert not any(workdir == c or workdir.startswith(c + os.sep) for c in (p.req, p.res, p.ctl))


# ── PV-20 §3.3 H2 / A7: how a live end is classified (state-machines §4 guards) ──

def _seeded(state, stop_reason=None, max_attempts=2, isolated=None, process_seq=0,
            seed_revision=None, import_revision=None):
    """One execution in *state* under a RUNNING task, on a real database. No
    process ever ran (process_seq 0 by default), so only the classification is
    exercised."""
    from archeus.core.domain.events import new_event
    from archeus.core.domain.values import Ref
    from archeus.infra.db import Database
    db = Database.open()
    who = Ref('user_device', ids.new_id('principal'))
    mid, pid, tid, eid = (ids.new_id(k) for k in ('mission', 'plan', 'task', 'execution'))

    def run(tx, **_):
        for row in (
                entities.Mission(id=mid, workspace_id=ids.GLOBAL_WORKSPACE, title='M',
                                 objective='o', state='EXECUTING'),
                entities.Plan(id=pid, mission_id=mid, state='APPROVED'),
                entities.Task(id=tid, plan_id=pid, mission_id=mid, key='t', title='T',
                              kind='code_change', state='RUNNING',
                              max_attempts=max_attempts),
                entities.Execution(id=eid, task_id=tid, mission_id=mid, plan_id=pid,
                                   attempt=1, state=state, stop_reason=stop_reason,
                                   isolated=isolated, process_seq=process_seq,
                                   seed_revision=seed_revision,
                                   import_revision=import_revision)):
            tx.insert(row, actor=who)
        tx.append(new_event('mission.updated', Ref('mission', mid), who, payload={},
                            workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})
    return db, who, eid, tid


def _row(db, kind, id_):
    from archeus.infra.db import rows
    with db.read() as r:
        return rows.get(r, kind, id_)


def _prepare(db, eid, isolated, seq=2):
    from archeus.core.domain.values import Ref
    return db.writer.execute(X.prepare_process, {
        'actor': Ref('system', ids.new_id('principal')), 'execution_id': eid,
        'token_digest': '0' * 64, 'workdir': 'w',
        'branch': None, 'process_seq': seq, 'isolated': isolated})


@pytest.mark.parametrize('recorded', [True, False])
def test_a_resume_under_the_other_isolation_decision_ends_it_uncharged(recorded):
    db, who, eid, tid = _seeded('PAUSED', isolated=recorded, process_seq=1)
    try:
        out = _prepare(db, eid, not recorded)
        assert 'isolation decision changed' in out['refused']
        e = _row(db, entities.Execution, eid).entity
        assert (e.state, e.stop_reason, e.charged) == ('ENDED_KILLED', 'binding', False)
        assert (e.isolated, e.process_seq) == (recorded, 1)
        assert _row(db, entities.Task, tid).entity.state == 'READY'
    finally:
        db.close()


@pytest.mark.parametrize('recorded,decide', [(True, True), (False, False), (None, True),
                                             (None, False)])
def test_a_resume_under_the_same_or_an_unknown_decision_passes_the_comparison(recorded,
                                                                              decide):
    # the seeded row has no dispatch decision, so the binding refuses next: its
    # reason, not the isolation one, shows the comparison let it through
    db, who, eid, _ = _seeded('PAUSED', isolated=recorded, process_seq=1)
    try:
        out = _prepare(db, eid, decide)
        assert out['refused'] and 'isolation' not in out['refused']
        assert _row(db, entities.Execution, eid).entity.isolated is recorded
    finally:
        db.close()


@pytest.mark.parametrize('bad', [None, 1, 0, 'true'])
def test_preparation_needs_the_decision_as_a_bool(bad):
    db, who, eid, _ = _seeded('INTENT')
    try:
        with pytest.raises(ValueError):
            _prepare(db, eid, bad, seq=1)
        with pytest.raises(TypeError):
            db.writer.execute(X.prepare_process, {
                'actor': who, 'execution_id': eid, 'token_digest': '0' * 64, 'workdir': 'w',
                'branch': None, 'process_seq': 1})
        assert _row(db, entities.Execution, eid).entity.process_seq == 0
    finally:
        db.close()


@pytest.mark.parametrize('bad', [1, 0, 'true'])
def test_the_isolated_field_is_a_bool_or_unknown(bad):
    kw = dict(id=ids.new_id('execution'), task_id=ids.new_id('task'),
              mission_id=ids.new_id('mission'))
    with pytest.raises(ValueError):
        entities.Execution(**kw, isolated=bad)
    body = entities.Execution(**kw).to_dict()
    del body['isolated']
    assert entities.Execution.from_dict(body).isolated is None


#: (isolated, state, exit code, killed, the execution's halt report) -> end state
LIVE_ENDS = [
    # isolated: Core's state and observed exit decide; the report never does
    (True, 'PAUSING', 0, False, False, 'PAUSED'),
    (True, 'PAUSING', 0, False, True, 'PAUSED'),
    (True, 'PAUSING', 1, False, False, 'ENDED_ERROR'),
    (True, 'PAUSING', 1, False, True, 'ENDED_ERROR'),
    (True, 'PAUSING', None, False, True, 'ENDED_ERROR'),
    (True, 'PAUSING', 0, True, True, 'ENDED_ERROR'),
    (True, 'HANDING_OFF', 1, False, False, 'ENDED_ERROR'),
    (True, 'HANDING_OFF', 1, False, True, 'ENDED_ERROR'),
    (True, 'HANDING_OFF', None, False, False, 'ENDED_ERROR'),
    (True, 'HANDING_OFF', 0, True, False, 'ENDED_ERROR'),
    (True, 'RUNNING', 0, False, False, 'ENDED_OK'),
    (True, 'RUNNING', 0, False, True, 'ENDED_ERROR'),
    (True, 'RUNNING', 1, False, False, 'ENDED_ERROR'),
    (True, 'STARTING', 0, False, False, 'ENDED_OK'),
    (True, 'STOPPING', 0, False, True, 'ENDED_KILLED'),
    (True, 'AWAITING_APPROVAL', 0, False, True, 'AWAITING_APPROVAL'),
    # ordinary executions keep p11 §240 / p12 §317 exactly
    (False, 'PAUSING', 0, False, False, 'ENDED_OK'),
    (False, 'PAUSING', 1, False, True, 'PAUSED'),
    (False, 'PAUSING', 1, False, False, 'ENDED_ERROR'),
    (False, 'HANDING_OFF', 0, False, False, 'ENDED_OK'),
    (False, 'HANDING_OFF', 1, False, False, 'ENDED_ERROR'),
    (False, 'RUNNING', 0, False, False, 'ENDED_OK'),
    (False, 'RUNNING', 0, False, True, 'ENDED_ERROR'),
    (False, 'STARTING', 0, False, False, 'ENDED_OK'),
    (False, 'STOPPING', 0, False, True, 'ENDED_KILLED'),
    (False, 'AWAITING_APPROVAL', 0, False, True, 'AWAITING_APPROVAL'),
]


@pytest.mark.parametrize('isolated,state,code,killed,halted,want', LIVE_ENDS)
def test_a_live_end_is_classified_by_cores_state_and_observed_exit(isolated, state, code,
                                                                     killed, halted, want):
    db, who, eid, tid = _seeded(state)
    try:
        db.writer.execute(X.record_end, {'actor': who, 'execution_id': eid, 'exit_code': code,
                                         'killed': killed, 'halted': halted,
                                         'isolated': isolated})
        assert _row(db, entities.Execution, eid).entity.state == want
        if want == 'ENDED_OK':
            # an execution-level fact, not success: the task only reaches VERIFYING
            assert _row(db, entities.Task, tid).entity.state == 'VERIFYING'
    finally:
        db.close()


@pytest.mark.parametrize('halted', [False, True])
def test_a_misrouted_isolated_handoff_is_refused_before_any_write(halted):
    db, who, eid, _ = _seeded('HANDING_OFF')
    try:
        before = _row(db, entities.Execution, eid)
        with pytest.raises(X.lifecycle.IllegalTrigger):
            db.writer.execute(X.record_end, {'actor': who, 'execution_id': eid, 'exit_code': 0,
                                             'halted': halted, 'final_offset': 99,
                                             'isolated': True})
        after = _row(db, entities.Execution, eid)
        assert (after.entity.state, after.version, after.entity.stream_offset) == \
            (before.entity.state, before.version, before.entity.stream_offset)
    finally:
        db.close()


def test_cores_own_restart_halt_pauses_an_isolated_execution_without_an_exit():
    db, who, eid, _ = _seeded('PAUSING')
    try:
        db.writer.execute(X.record_end, {'actor': who, 'execution_id': eid, 'exit_code': None,
                                         'core_halt': True, 'isolated': True})
        assert _row(db, entities.Execution, eid).entity.state == 'PAUSED'
    finally:
        db.close()


#: T-026 (T-025 C1): (isolated, the hand-off's stop reason, exit code, killed, charged)
#: of an end observed in HANDING_OFF that is not a clean isolated hand-off
HANDOFF_ACCOUNTING = [
    (True, cause, code, killed, False)
    for cause in X.HANDOFF_CAUSES + ('handoff_user',)
    for code, killed in ((1, False), (None, False), (0, True), (None, True))
] + [
    # a stop reason outside UNCHARGED is charged as before
    (True, 'workspace', 1, False, True),
    (True, None, None, True, True),
    # ordinary direct callers keep the charge rule they had
    (False, 'pressure', 1, False, True),
    (False, 'handoff_user', None, True, True),
]


@pytest.mark.parametrize('isolated,cause,code,killed,charged', HANDOFF_ACCOUNTING)
def test_an_isolated_end_of_a_handoff_core_asked_for_spends_no_attempt(isolated, cause, code,
                                                                       killed, charged):
    db, who, eid, tid = _seeded('HANDING_OFF', stop_reason=cause, max_attempts=1)
    try:
        db.writer.execute(X.record_end, {'actor': who, 'execution_id': eid, 'exit_code': code,
                                         'killed': killed, 'isolated': isolated})
        e = _row(db, entities.Execution, eid).entity
        assert (e.state, e.charged, e.stop_reason) == ('ENDED_ERROR', charged, cause)
        # one attempt in the budget: a charged end spends it, an uncharged one retries
        assert _row(db, entities.Task, tid).entity.state == ('FAILED' if charged else 'READY')
        from archeus.infra.db import rows
        with db.read() as r:                    # never a continuation from record_end
            assert [x.entity.id for x in rows.where(r, entities.Execution, task_id=tid)] == [eid]
    finally:
        db.close()


@pytest.mark.parametrize('state,code', [('RUNNING', 1), ('PAUSING', 1), ('PAUSING', None)])
def test_an_isolated_end_outside_a_handoff_keeps_its_charge(state, code):
    db, who, eid, tid = _seeded(state, stop_reason='pressure', max_attempts=1)
    try:
        db.writer.execute(X.record_end, {'actor': who, 'execution_id': eid, 'exit_code': code,
                                         'isolated': True})
        e = _row(db, entities.Execution, eid).entity
        assert (e.state, e.charged) == ('ENDED_ERROR', True)
        assert _row(db, entities.Task, tid).entity.state == 'FAILED'
    finally:
        db.close()


# ── T-021 D1: one isolation decision, before the workspace and the inventory ──

def _spawn_rig(monkeypatch, tmp_path, decide=False, authority='present', opt_ins=None,
               scenario=None, project=None, mode='worktree', git=None, staged=None):
    """manager._spawn (and _resume) on fakes, every step landing in one ordered log.
    *decide* is what the node's isolation authority answers, or an exception it raises.
    The real `_workspace` runs; *project* is the project's root, *git* what the node's
    git probes of it answer. The stager is faked, so no installed runtime is read:
    *staged* is the error it raises, or None for a stage under tmp_path."""
    from archeus.core.execution import manager as M
    log = []
    stage_dir = str(tmp_path / 'home' / 'runtime' / ('a' * 64))

    def stage(source_root, hook_path):
        log.append(('stage', source_root, hook_path))
        if staged is not None:
            raise staged
        return stage_dir
    monkeypatch.setattr(M.staging, 'stage', stage)

    class Authority:
        def requested(self, execution_id, adapter):
            log.append(('requested', execution_id, adapter))
            if isinstance(decide, Exception):
                raise decide
            return decide

    class Node:
        def disarmed(self):
            return False

        def spawn(self, adapter, spec, **kw):
            log.append(('spawn', spec, kw))
            return SimpleNamespace(pid=1, create_time=1.0)

        def git_branch(self, root):
            log.append(('git_branch', root))
            return (git or {}).get('branch')

        def branch_exists(self, root, branch):
            log.append(('branch_exists', root, branch))
            return (git or {}).get('exists', False)

        def add_worktree(self, root, path, branch, base='HEAD'):
            log.append(('add_worktree', root, branch, base))
            return path

    class Adapter:
        id = 'fake'

        def discover(self):
            return SimpleNamespace(installed=True)

        def capabilities(self, _):
            return SimpleNamespace(capabilities=('resume',))

        def inventory(self, spec, **kw):
            log.append(('inventory', kw))

    def workspace(e, mission, t, **kw):
        log.append(('workspace', kw))
        return ExecutionManager._workspace(m, e, mission, t, **kw)

    def get(r, kind, id_):
        if kind is entities.Project:
            return SimpleNamespace(entity=SimpleNamespace(root_paths=[project]))
        return SimpleNamespace(entity=task)

    def do(command, **kw):
        log.append((command.__name__, kw))
        return {'refused': False}

    node, adapter = Node(), Adapter()
    if authority == 'present':
        node.isolation = Authority()
    elif authority == 'None':
        node.isolation = None
    m = ExecutionManager.__new__(ExecutionManager)
    m.registry = SimpleNamespace(get=lambda hid: adapter)
    m.db = SimpleNamespace(read=contextlib.nullcontext)
    m.node, m._procs, m._do, m._workspace = node, {}, do, workspace
    m.scenarios = {'t1': scenario} if scenario else {}
    m.policy = m.missions = m.router = None
    m._reload = lambda e: e
    task = SimpleNamespace(title='T', key='t1', kind='code', estimate=None, action_classes=(),
                           workspace_mode=mode)
    monkeypatch.setattr(M.resources, 'terms_permit', lambda r, a: True)
    monkeypatch.setattr(M.rows, 'get', get)
    monkeypatch.setattr(M.optins, 'effective', lambda r, **kw: dict(opt_ins or {}))
    e = SimpleNamespace(id=ids.new_id('execution'), harness_id='fake', task_id='t',
                        account_id=None, route_decision_id=None, process_seq=0,
                        handoff_from=None, attempt=1, model=None, effort=None,
                        adapter_state={'session': 's1'}, isolated=None)
    mission = SimpleNamespace(objective='o', id='mission-1',
                              project_id='project-1' if project else None)
    return m, e, mission, adapter, log


@pytest.mark.parametrize('field', [True, False, None])
@pytest.mark.parametrize('record', [True, False])
def test_a_resume_without_its_isolation_record_is_refused_before_the_decision(
        monkeypatch, tmp_path, field, record):
    # T-037 rule 4: recorded isolated, record gone -> refused before anything is decided,
    # made or inventoried; every other combination keeps the T-023 order
    m, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path, decide=bool(field))
    m.node.isolation_record = lambda eid: object() if record else None
    e.process_seq, e.isolated = 1, field
    assert m._resume(e, mission) is True
    if field is True and not record:
        assert _steps(log) == ['resume_checked', 'refuse']
        assert log[1][1]['stop_reason'] == 'binding'
        assert 'isolation record is gone' in log[1][1]['reason']
    else:
        assert _steps(log)[:2] == ['resume_checked', 'requested'] and 'workspace' in _steps(log)
        assert 'refuse' not in _steps(log)


def _steps(log):
    return [x[0] for x in log]


@pytest.mark.parametrize('decide', [False, True])
def test_isolation_is_decided_once_before_the_workspace_and_the_inventory(
        monkeypatch, tmp_path, decide):
    m, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path, decide)
    assert m._spawn(e, mission) is True
    assert _steps(log) == ['requested'] + ['stage'] * decide + [
        'workspace', 'inventory', 'prepare_process', 'spawn', 'record_process']
    assert log[0][1:] == (e.id, adapter)
    (_, spec, kw), = [x for x in log if x[0] == 'spawn']
    assert kw == {'resume_state': None, 'isolated': decide}
    assert [x[1] for x in log if x[0] == 'inventory'] == [{'isolated': decide}]
    assert [x[1]['isolated'] for x in log if x[0] == 'prepare_process'] == [decide]
    assert spec.isolation is None               # the node, not the manager, isolates the spec


@pytest.mark.parametrize('decide', [False, True])
def test_a_resume_takes_the_same_single_decision(monkeypatch, tmp_path, decide):
    m, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path, decide)
    e.process_seq = 1
    assert m._resume(e, mission) is True
    assert _steps(log).count('requested') == 1
    assert _steps(log).index('requested') < _steps(log).index('workspace')
    (_, spec, kw), = [x for x in log if x[0] == 'spawn']
    assert kw == {'resume_state': {'session': 's1'}, 'isolated': decide}
    assert [x[1]['isolated'] for x in log if x[0] == 'prepare_process'] == [decide]
    assert spec.process_seq == 2


@pytest.mark.parametrize('err', [OSError('unreadable'), ValueError('malformed id')])
def test_an_isolation_decision_that_raises_starts_nothing(monkeypatch, tmp_path, err):
    m, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path, err)
    assert m._spawn(e, mission) is True
    assert _steps(log) == ['requested', 'refuse']
    assert log[1][1]['stop_reason'] == 'binding'
    assert type(err).__name__ in log[1][1]['reason']


@pytest.mark.parametrize('authority', ['absent', 'None'])
def test_a_node_without_an_isolation_authority_spawns_unisolated_as_today(
        monkeypatch, tmp_path, authority):
    m, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path, authority=authority)
    assert m._spawn(e, mission) is True
    assert _steps(log) == ['workspace', 'inventory', 'prepare_process', 'spawn',
                           'record_process']
    (_, spec, kw), = [x for x in log if x[0] == 'spawn']
    assert kw == {'resume_state': None, 'isolated': False}
    assert [x[1] for x in log if x[0] == 'inventory'] == [{'isolated': False}]
    assert [x[1]['isolated'] for x in log if x[0] == 'prepare_process'] == [False]
    assert (spec.workdir, spec.isolation) == (paths.ExecPaths(e.id).work, None)


@pytest.mark.parametrize('decide', [False, True])
def test_no_spec_or_environment_value_decides_isolation(monkeypatch, tmp_path, decide):
    claim = 'unisolated' if decide else '1'
    for k in ('ARCHEUS_ISOLATED', 'ARCHEUS_ISOLATION', 'ISOLATED'):
        monkeypatch.setenv(k, claim)
    shaped = {'isolated': not decide, 'isolation': claim}
    m, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path, decide, opt_ins=shaped,
                                             scenario=shaped)
    assert m._spawn(e, mission) is True
    (_, spec, kw), = [x for x in log if x[0] == 'spawn']
    assert kw['isolated'] is decide
    assert (spec.task_contract['fake_scenario'], spec.opt_ins) == (shaped, shaped)  # it got in


# ── T-027 (T-016 W2): an isolated execution never works in the user's project ──

GIT = {'on a branch': {'branch': 'main'},
       'detached HEAD or not a repository': {'branch': None},
       'mission branch and worktree exist': {'branch': 'main', 'exists': True}}


def _run(m, e, mission, resume, log):
    """A first process, or a resume; the resume's own check is taken off the log."""
    if not resume:
        return m._spawn(e, mission)
    e.process_seq = 1
    done = m._resume(e, mission)
    assert _steps(log).count('resume_checked') == 1
    log[:] = [x for x in log if x[0] != 'resume_checked']
    return done


@pytest.mark.parametrize('resume', [False, True])
@pytest.mark.parametrize('git', list(GIT))
@pytest.mark.parametrize('mode', ['in_place', 'worktree'])
def test_an_isolated_project_execution_is_refused_before_its_root_is_touched(
        monkeypatch, tmp_path, mode, git, resume):
    m, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path, True,
                                             project=str(tmp_path / 'repo'), mode=mode,
                                             git=GIT[git])
    assert _run(m, e, mission, resume, log) is True
    assert _steps(log) == ['requested', 'stage', 'workspace', 'refuse']
    assert log[2][1] == {'isolated': True}
    assert log[3][1]['stop_reason'] == 'workspace'
    assert 'isolated execution has no project workspace' in log[3][1]['reason']


@pytest.mark.parametrize('decide', [False, True])
def test_a_project_less_execution_keeps_its_own_workspace_across_a_resume(
        monkeypatch, tmp_path, decide):
    m, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path, decide)
    assert m._spawn(e, mission) is True
    work = paths.ExecPaths(e.id).work
    open(os.path.join(work, 'notes.txt'), 'w').close()
    assert _run(m, e, mission, True, log) is True
    assert [x[1].workdir for x in log if x[0] == 'spawn'] == [work, work]
    assert os.listdir(work) == ['notes.txt']
    assert 'git_branch' not in _steps(log)


@pytest.mark.parametrize('resume', [False, True])
def test_an_unisolated_in_place_execution_still_runs_in_the_project_root(
        monkeypatch, tmp_path, resume):
    root = str(tmp_path / 'repo')
    m, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path, False, project=root,
                                             mode='in_place', git={'branch': 'main'})
    assert _run(m, e, mission, resume, log) is True
    assert _steps(log) == ['requested', 'workspace', 'git_branch', 'inventory',
                           'prepare_process', 'spawn', 'record_process']
    (prep,) = [x[1] for x in log if x[0] == 'prepare_process']
    assert (prep['workdir'], prep['branch']) == (root, 'main')


@pytest.mark.parametrize('resume', [False, True])
@pytest.mark.parametrize('exists', [False, True])
def test_an_unisolated_worktree_execution_still_gets_its_linked_worktree(
        monkeypatch, tmp_path, exists, resume):
    root = str(tmp_path / 'repo')
    m, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path, False, project=root,
                                             git={'branch': 'main', 'exists': exists})
    assert _run(m, e, mission, resume, log) is True
    assert _steps(log) == ['requested', 'workspace', 'git_branch', 'branch_exists',
                           'add_worktree', 'inventory', 'prepare_process', 'spawn',
                           'record_process']
    (add,) = [x for x in log if x[0] == 'add_worktree']
    assert add[1:] == (root, 'archeus/mission-1.t1', 'archeus/mission-1' if exists else 'HEAD')
    (prep,) = [x[1] for x in log if x[0] == 'prepare_process']
    assert prep['branch'] == 'archeus/mission-1.t1' and prep['workdir'] != root


# ── T-032 (T-031 E2): an isolated execution's hook runs in isolated mode ──

@pytest.mark.parametrize('resume', [False, True])
@pytest.mark.parametrize('decide', [False, True])
def test_an_isolated_executions_hook_runs_in_isolated_mode(monkeypatch, tmp_path, decide,
                                                           resume):
    from archeus.core.execution.manager import HOOK
    from archeus.harnesses.claude_code import adapter as cc
    m, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path, decide)
    assert _run(m, e, mission, resume, log) is True
    assert _steps(log).count('requested') == 1          # the one decision, never re-asked
    (_, spec, kw), = [x for x in log if x[0] == 'spawn']
    stage = str(tmp_path / 'home' / 'runtime' / ('a' * 64))
    want = ((os.path.join(stage, 'python.exe'), '-I', os.path.join(stage, 'hook.py'))
            if decide else (sys.executable, HOOK))
    assert spec.hook_settings == want
    # the Claude Code settings file carries it as it carries the rest: each part quoted
    with open(cc.ClaudeCodeAdapter(exe='claude')._settings(spec), encoding='utf-8') as f:
        hooks = json.load(f)['hooks']
    cmd = ' '.join('"%s"' % part for part in want)
    assert {h['hooks'][0]['command'] for h in hooks['PreToolUse'] + hooks['PreCompact']} == {cmd}


# ── T-040 (C4b): the isolated hook runs from Core's verified stage ──

@pytest.mark.parametrize('resume', [False, True])
def test_every_isolated_process_stages_from_the_real_install_never_a_venv(
        monkeypatch, tmp_path, resume):
    from archeus.core.execution.manager import HOOK
    base_prefix, venv = str(tmp_path / 'install'), str(tmp_path / 'venv' / 'Scripts')
    monkeypatch.setattr(sys, 'base_prefix', base_prefix)
    monkeypatch.setattr(sys, 'executable', os.path.join(venv, 'python.exe'))
    m, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path, True)
    assert _run(m, e, mission, resume, log) is True
    # once per process, a resume's included: verified again, never a cached answer
    assert [x for x in log if x[0] == 'stage'] == [('stage', base_prefix, HOOK)]
    assert _steps(log).index('stage') == _steps(log).index('requested') + 1
    (_, spec, kw), = [x for x in log if x[0] == 'spawn']
    assert not [p for p in spec.hook_settings if p.startswith((venv, base_prefix))]


@pytest.mark.parametrize('resume', [False, True])
def test_an_ordinary_process_never_stages(monkeypatch, tmp_path, resume):
    m, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path, False)
    assert _run(m, e, mission, resume, log) is True
    assert 'stage' not in _steps(log)


@pytest.mark.parametrize('resume', [False, True])
@pytest.mark.parametrize('err', [OSError('copy failed'), PermissionError('denied')])
def test_a_stage_that_cannot_be_made_or_verified_starts_nothing_uncharged(
        monkeypatch, tmp_path, resume, err):
    from archeus.node.staging import StageError
    for failure in (err, StageError('the stage differs from its manifest')):
        m, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path, True, staged=failure)
        assert _run(m, e, mission, resume, log) is True
        assert _steps(log) == ['requested', 'stage', 'refuse']   # no workspace, inventory,
        assert log[2][1]['stop_reason'] == 'binding'             # preparation or spawn
        assert 'hook runtime could not be staged' in log[2][1]['reason']



# ── PV-20 K2 (T-049 §2, §7; T-030 §3.3 Q2 answered A): the recorded seed ──────

SEED, OTHER = 'a' * 40, 'b' * 40


def _prep(db, eid, seed, seq, isolated=True):
    from archeus.core.domain.values import Ref
    return db.writer.execute(X.prepare_process, {
        'actor': Ref('system', ids.new_id('principal')), 'execution_id': eid,
        'token_digest': '0' * 64, 'workdir': 'w', 'branch': None, 'process_seq': seq,
        'isolated': isolated, 'seed_revision': seed})


def test_the_seed_is_recorded_once_at_the_first_preparation(monkeypatch):
    monkeypatch.setattr(X, 'binding', lambda conn, e: None)
    db, who, eid, _ = _seeded('INTENT')
    try:
        assert _prep(db, eid, SEED, 1)['refused'] is None
        assert _row(db, entities.Execution, eid).entity.seed_revision == SEED
        assert _prep(db, eid, SEED, 2)['refused'] is None          # the same one: kept
        out = _prep(db, eid, OTHER, 3)
        assert 'its seed changed' in out['refused']
        e = _row(db, entities.Execution, eid).entity
        assert (e.seed_revision, e.charged, e.stop_reason) == (SEED, False, 'binding')
        with db.read() as r:
            got = [ev['payload']['seed_revision']
                   for ev in _events(r, eid, 'execution.prepared')]
        assert got == [SEED, SEED]
    finally:
        db.close()


def _events(r, eid, type_):
    from archeus.core.application import queries
    return [ev for ev in queries.events(r) if ev['type'] == type_
            and ev['subject']['id'] == eid]


@pytest.mark.parametrize('recorded,passed', [(SEED, OTHER), (SEED, None), (None, SEED)])
def test_a_resume_under_another_seed_ends_it_uncharged(recorded, passed):
    db, who, eid, tid = _seeded('PAUSED', isolated=True, process_seq=1, seed_revision=recorded)
    try:
        out = _prep(db, eid, passed, 2)
        assert 'its seed changed' in out['refused']
        e = _row(db, entities.Execution, eid).entity
        assert (e.state, e.stop_reason, e.charged) == ('ENDED_KILLED', 'binding', False)
        assert (e.seed_revision, e.process_seq) == (recorded, 1)
        assert _row(db, entities.Task, tid).entity.state == 'READY'
    finally:
        db.close()


@pytest.mark.parametrize('recorded', [SEED, None])
def test_a_resume_under_the_recorded_seed_or_a_legacy_row_passes_the_comparison(recorded):
    # no dispatch decision is seeded, so the binding refuses next: its reason, not
    # the seed's, shows the comparison let it through; a legacy None row stays None
    db, who, eid, _ = _seeded('PAUSED', isolated=True, process_seq=1, seed_revision=recorded)
    try:
        out = _prep(db, eid, recorded, 2)
        assert out['refused'] and 'seed' not in out['refused']
        assert _row(db, entities.Execution, eid).entity.seed_revision == recorded
    finally:
        db.close()


@pytest.mark.parametrize('bad', ['A' * 40, 'a' * 39, 'a' * 41, 'a' * 63, 'g' * 40, 'HEAD',
                                 'refs/heads/main', 1, b'a' * 40])
def test_the_seed_is_a_commit_id_or_unknown(bad):
    kw = dict(id=ids.new_id('execution'), task_id=ids.new_id('task'),
              mission_id=ids.new_id('mission'))
    with pytest.raises(ValueError):
        entities.Execution(**kw, seed_revision=bad)
    assert entities.Execution(**kw, seed_revision='a' * 64).seed_revision == 'a' * 64
    body = entities.Execution(**kw).to_dict()
    body.pop('seed_revision', None)
    assert entities.Execution.from_dict(body).seed_revision is None
    db, who, eid, _ = _seeded('INTENT')
    try:
        with pytest.raises(ValueError):
            _prep(db, eid, bad, 1)
        assert _row(db, entities.Execution, eid).entity.process_seq == 0
    finally:
        db.close()


def _attempts(db, eid, *rows_):
    """More executions of *eid*'s task: (attempt, seed, handoff_from)."""
    from archeus.core.domain.events import new_event
    from archeus.core.domain.values import Ref
    first, who = _row(db, entities.Execution, eid).entity, Ref('system', ids.new_id('principal'))
    made = []

    def run(tx, **_):
        for attempt, seed, handoff in rows_:
            e = entities.Execution(id=ids.new_id('execution'), task_id=first.task_id,
                                   mission_id=first.mission_id, plan_id=first.plan_id,
                                   attempt=attempt, state='INTENT', seed_revision=seed,
                                   handoff_from=handoff)
            tx.insert(e, actor=who)
            made.append(e)
        tx.append(new_event('mission.updated', Ref('mission', first.mission_id), who,
                            payload={}, workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})
    return made


def test_a_first_attempt_has_no_recorded_base_and_a_retry_takes_the_latest_earlier_seed():
    db, who, eid, _ = _seeded('ENDED_ERROR', seed_revision=SEED)
    try:
        with db.read() as r:
            assert X.seed_base(r, _row(db, entities.Execution, eid).entity) is None
        unseeded, latest, retry, after = _attempts(db, eid, (2, None, None), (3, OTHER, None),
                                                   (4, None, None), (5, None, None))
        with db.read() as r:
            assert X.seed_base(r, unseeded) == SEED     # the user's refs are not re-read
            assert X.seed_base(r, retry) == OTHER       # the latest, not the first
            assert X.seed_base(r, after) == OTHER       # one never seeded is skipped
    finally:
        db.close()


def test_a_continuation_without_its_predecessors_import_is_refused_as_class_import():
    db, who, eid, _ = _seeded('ENDED_HANDOFF', seed_revision=SEED)
    try:
        (cont,) = _attempts(db, eid, (2, None, eid))
        with db.read() as r, pytest.raises(X.SeedRefused) as err:
            X.seed_base(r, cont)
        assert err.value.failure_class == 'import' and 'no import' in str(err.value)
    finally:
        db.close()


@pytest.mark.parametrize('max_attempts,task_state,failure_class', [(1, 'FAILED', 'import'),
                                                                   (2, 'READY', None)])
def test_a_no_import_refusal_is_charged_and_fails_the_last_attempt_as_import(
        max_attempts, task_state, failure_class):
    from archeus.core.domain.values import Ref
    db, who, eid, tid = _seeded('INTENT', max_attempts=max_attempts)
    try:
        db.writer.execute(X.refuse, {'actor': Ref('system', ids.new_id('principal')),
                                     'execution_id': eid, 'stop_reason': 'workspace',
                                     'reason': 'no seed: no import', 'failure_class': 'import'})
        e, t = _row(db, entities.Execution, eid).entity, _row(db, entities.Task, tid).entity
        assert (e.state, e.charged) == ('ABANDONED', True)
        assert (t.state, t.failure_class) == (task_state, failure_class)
    finally:
        db.close()


def test_any_other_refusal_still_fails_the_last_attempt_as_execution():
    from archeus.core.domain.values import Ref
    db, who, eid, tid = _seeded('INTENT', max_attempts=1)
    try:
        db.writer.execute(X.refuse, {'actor': Ref('system', ids.new_id('principal')),
                                     'execution_id': eid, 'stop_reason': 'workspace',
                                     'reason': 'no workspace'})
        assert _row(db, entities.Task, tid).entity.failure_class == 'execution'
    finally:
        db.close()



# ── PV-20 K3 (T-051 §5, §7; T-030 §3.3 Q2 answered A): the recorded import ────

IMP = 'c' * 40


def _end(db, who, eid, **kw):
    return db.writer.execute(X.record_end, dict({'actor': who, 'execution_id': eid,
                                                 'exit_code': 0, 'isolated': True}, **kw))


@pytest.mark.parametrize('bad', ['C' * 40, 'c' * 39, 'c' * 64, 'HEAD', 1])
def test_the_import_is_a_sha1_commit_id_or_unknown(bad):
    kw = dict(id=ids.new_id('execution'), task_id=ids.new_id('task'),
              mission_id=ids.new_id('mission'))
    with pytest.raises(ValueError):
        entities.Execution(**kw, import_revision=bad)
    body = entities.Execution(**kw).to_dict()
    body.pop('import_revision', None)
    assert entities.Execution.from_dict(body).import_revision is None


def test_a_clean_end_records_its_import_in_the_same_transaction():
    db, who, eid, tid = _seeded('RUNNING', isolated=True, seed_revision=SEED)
    try:
        _end(db, who, eid, import_revision=IMP)
        e = _row(db, entities.Execution, eid).entity
        assert (e.state, e.import_revision, e.charged) == ('ENDED_OK', IMP, True)
        assert _row(db, entities.Task, tid).entity.state == 'VERIFYING'
        with db.read() as r:
            (ev,) = _events(r, eid, 'execution.ended')
        assert ev['payload']['import_revision'] == IMP
    finally:
        db.close()


@pytest.mark.parametrize('max_attempts,task_state,failure_class', [(1, 'FAILED', 'import'),
                                                                   (2, 'READY', None)])
def test_a_clean_end_without_its_import_stands_and_is_charged_as_import(
        max_attempts, task_state, failure_class):
    db, who, eid, tid = _seeded('RUNNING', isolated=True, seed_revision=SEED,
                                max_attempts=max_attempts)
    try:
        _end(db, who, eid, no_import='not quiescent: 1 process(es) still in its Job')
        e, t = _row(db, entities.Execution, eid).entity, _row(db, entities.Task, tid).entity
        assert (e.state, e.import_revision, e.charged) == ('ENDED_OK', None, True)
        assert (t.state, t.failure_class) == (task_state, failure_class)
        with db.read() as r:
            reasons = [ev['payload'].get('reason') or '' for ev in queries.events(r)
                       if ev['subject']['id'] == tid]
        assert any('no import: not quiescent' in x for x in reasons)
    finally:
        db.close()


def test_an_unseeded_clean_end_has_nothing_to_import_and_succeeds():
    db, who, eid, tid = _seeded('RUNNING', isolated=True)
    try:
        _end(db, who, eid)
        assert _row(db, entities.Task, tid).entity.state == 'VERIFYING'
        with pytest.raises(ValueError, match='never seeded'):
            db2, who2, eid2, _ = _seeded('RUNNING', isolated=True)
            try:
                _end(db2, who2, eid2, import_revision=IMP)
            finally:
                db2.close()
    finally:
        db.close()


@pytest.mark.parametrize('kw', [{'exit_code': 1}, {'killed': True}, {'halted': True}])
def test_only_a_clean_end_imports(kw):
    db, who, eid, _ = _seeded('RUNNING', isolated=True, seed_revision=SEED)
    try:
        before = _row(db, entities.Execution, eid)
        with pytest.raises(ValueError, match='only a clean end'):
            _end(db, who, eid, import_revision=IMP, **kw)
        assert _row(db, entities.Execution, eid).version == before.version
    finally:
        db.close()


@pytest.mark.parametrize('kw', [{'exit_code': 1}, {'killed': True}])
def test_an_unclean_end_needs_no_import_and_keeps_its_own_class(kw):
    db, who, eid, tid = _seeded('RUNNING', isolated=True, seed_revision=SEED, max_attempts=1)
    try:
        _end(db, who, eid, **kw)
        assert _row(db, entities.Task, tid).entity.failure_class == 'execution'
    finally:
        db.close()


def test_an_import_is_written_once():
    db, who, eid, _ = _seeded('RUNNING', isolated=True, seed_revision=SEED,
                              import_revision=IMP)
    try:
        with pytest.raises(ValueError, match='already recorded'):
            _end(db, who, eid, import_revision='d' * 40)
        with pytest.raises(ValueError, match='already recorded'):
            _end(db, who, eid)
        assert _row(db, entities.Execution, eid).entity.import_revision == IMP
    finally:
        db.close()


@pytest.mark.parametrize('state', ['STOPPING', 'PAUSING', 'ENDED_KILLED'])
def test_a_lost_race_records_no_import(state):
    """The row left RUNNING after the route was captured: a LOST_RACE, which the
    pass already handles, and nothing of the end is written."""
    db, who, eid, _ = _seeded(state, isolated=True, seed_revision=SEED)
    try:
        before = _row(db, entities.Execution, eid)
        with pytest.raises(X.lifecycle.IllegalTrigger):
            _end(db, who, eid, import_revision=IMP)
        after = _row(db, entities.Execution, eid)
        assert (after.version, after.entity.import_revision) == (before.version, None)
    finally:
        db.close()


def _handoff(db, who, eid, **kw):
    return db.writer.execute(X.record_handoff, dict(
        {'actor': who, 'execution_id': eid, 'policy': None, 'missions': None, 'router': None,
         'now': 0.0, 'exit_code': 0}, **kw))


@pytest.mark.parametrize('stop_reason', ['limit', 'pressure'])
@pytest.mark.parametrize('max_attempts,task_state', [(1, 'FAILED'), (2, 'READY')])
def test_a_handoff_without_its_import_has_no_continuation_and_is_charged_as_import(
        monkeypatch, stop_reason, max_attempts, task_state):
    from archeus.core.execution import handoff
    monkeypatch.setattr(handoff, 'continue_task', lambda tx, **kw: pytest.fail('continued'))
    db, who, eid, tid = _seeded('HANDING_OFF', stop_reason=stop_reason, isolated=True,
                                seed_revision=SEED, max_attempts=max_attempts)
    try:
        out = _handoff(db, who, eid, no_import='its isolation record is gone')
        assert out['continuation'] is None and 'no import' in out['refused']
        e, t = _row(db, entities.Execution, eid).entity, _row(db, entities.Task, tid).entity
        assert (e.state, e.charged, e.import_revision) == ('ENDED_HANDOFF', True, None)
        assert t.state == task_state
        if task_state == 'FAILED':
            assert t.failure_class == 'import'
    finally:
        db.close()


def test_a_handoff_with_its_import_records_it_and_continues(monkeypatch):
    from archeus.core.execution import handoff
    seen = []
    monkeypatch.setattr(handoff, 'continue_task', lambda tx, **kw: seen.append(
        kw['execution'].import_revision) or {'execution_id': 'next', 'refused': None})
    db, who, eid, _ = _seeded('HANDING_OFF', stop_reason='limit', isolated=True,
                              seed_revision=SEED)
    try:
        out = _handoff(db, who, eid, import_revision=IMP, facts={'end_state': 'e' * 40})
        e = _row(db, entities.Execution, eid).entity
        assert (out['continuation'], e.import_revision, e.charged) == ('next', IMP, False)
        assert seen == [IMP]
    finally:
        db.close()


def test_a_handoff_imports_once():
    db, who, eid, _ = _seeded('HANDING_OFF', stop_reason='limit', isolated=True,
                              seed_revision=SEED, import_revision=IMP)
    try:
        with pytest.raises(ValueError, match='already recorded'):
            _handoff(db, who, eid, import_revision='d' * 40)
    finally:
        db.close()


def test_a_continuation_is_seeded_from_its_predecessors_import():
    db, who, eid, _ = _seeded('ENDED_HANDOFF', seed_revision=SEED, import_revision=IMP)
    try:
        (cont,) = _attempts(db, eid, (2, None, eid))
        with db.read() as r:
            assert X.seed_base(r, cont) == IMP
    finally:
        db.close()


def test_a_retry_takes_the_latest_seeded_attempts_import_else_its_seed():
    db, who, eid, _ = _seeded('ENDED_OK', seed_revision=SEED, import_revision=IMP)
    try:
        (retry,) = _attempts(db, eid, (2, None, None))
        with db.read() as r:
            assert X.seed_base(r, retry) == IMP
    finally:
        db.close()
