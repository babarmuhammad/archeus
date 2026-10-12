"""P11, the pure half (p11-design-gate §11, §8.2, §10, §19, D16): the action
canonicaliser, the execution state table, the hook's protocol, redaction, and
the branch/host slot P9 left for the action stage."""

import contextlib
import errno
import io
import json
import os
import stat
import threading
import time
from types import SimpleNamespace

import pytest

from claude_sessions import config, proc

from archeus.core.application import executions as X
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


def test_a_project_less_workspace_is_the_executions_own_never_its_core_directory():
    eid = ids.new_id('execution')
    p = paths.ExecPaths(eid)
    workdir, branch = ExecutionManager._workspace(None, SimpleNamespace(id=eid),
                                                  SimpleNamespace(project_id=None), None)
    assert (workdir, branch) == (p.work, None) and os.path.isdir(workdir)
    assert workdir != p.dir
    assert not any(workdir == c or workdir.startswith(c + os.sep) for c in (p.req, p.res, p.ctl))


# ── PV-20 §3.3 H2 / A7: how a live end is classified (state-machines §4 guards) ──

def _seeded(state):
    """One execution in *state* under a RUNNING task, on a real database. No
    process ever ran (process_seq 0), so only the classification is exercised."""
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
                              kind='code_change', state='RUNNING'),
                entities.Execution(id=eid, task_id=tid, mission_id=mid, plan_id=pid,
                                   attempt=1, state=state)):
            tx.insert(row, actor=who)
        tx.append(new_event('mission.updated', Ref('mission', mid), who, payload={},
                            workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})
    return db, who, eid, tid


def _row(db, kind, id_):
    from archeus.infra.db import rows
    with db.read() as r:
        return rows.get(r, kind, id_)


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


# ── T-021 D1: one isolation decision, before the workspace and the inventory ──

def _spawn_rig(monkeypatch, tmp_path, decide=False, authority='present', opt_ins=None,
               scenario=None):
    """manager._spawn (and _resume) on fakes, every step landing in one ordered log.
    *decide* is what the node's isolation authority answers, or an exception it raises."""
    from archeus.core.execution import manager as M
    log = []

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

    class Adapter:
        id = 'fake'

        def discover(self):
            return SimpleNamespace(installed=True)

        def capabilities(self, _):
            return SimpleNamespace(capabilities=('resume',))

        def inventory(self, spec):
            log.append(('inventory',))

    def workspace(e, mission, t):
        log.append(('workspace',))
        return str(tmp_path), 'b'

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
    task = SimpleNamespace(title='T', key='t1', kind='code', estimate=None, action_classes=())
    monkeypatch.setattr(M.resources, 'terms_permit', lambda r, a: True)
    monkeypatch.setattr(M.rows, 'get', lambda r, kind, id_: SimpleNamespace(entity=task))
    monkeypatch.setattr(M.optins, 'effective', lambda r, **kw: dict(opt_ins or {}))
    e = SimpleNamespace(id=ids.new_id('execution'), harness_id='fake', task_id='t',
                        account_id=None, route_decision_id=None, process_seq=0,
                        handoff_from=None, attempt=1, model=None, effort=None,
                        adapter_state={'session': 's1'})
    return m, e, SimpleNamespace(objective='o', project_id=None), adapter, log


def _steps(log):
    return [x[0] for x in log]


@pytest.mark.parametrize('decide', [False, True])
def test_isolation_is_decided_once_before_the_workspace_and_the_inventory(
        monkeypatch, tmp_path, decide):
    m, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path, decide)
    assert m._spawn(e, mission) is True
    assert _steps(log) == ['requested', 'workspace', 'inventory', 'prepare_process', 'spawn',
                           'record_process']
    assert log[0][1:] == (e.id, adapter)
    (_, spec, kw), = [x for x in log if x[0] == 'spawn']
    assert kw == {'resume_state': None, 'isolated': decide}
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
    assert (spec.workdir, spec.isolation) == (str(tmp_path), None)


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
