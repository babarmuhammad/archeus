"""P11, the pure half (p11-design-gate §11, §8.2, §10, §19, D16): the action
canonicaliser, the execution state table, the hook's protocol, redaction, and
the branch/host slot P9 left for the action stage."""

import json
import os
import threading
import time

import pytest

from archeus.core.application import executions as X
from archeus.core.domain import actions, ids, states
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


# ── §10 the hook's protocol, without a process ──────────────────────────────

def test_the_hook_speaks_claude_codes_vocabulary():
    assert hook.decision('allow') == {'hookSpecificOutput': {
        'hookEventName': 'PreToolUse', 'permissionDecision': 'allow'}}
    assert hook.decision('deny', 'no')['hookSpecificOutput']['permissionDecisionReason'] == 'no'
    assert hook.decision('halt', 'stop') == {'continue': False, 'stopReason': 'stop'}


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


def test_concurrent_hooks_take_distinct_sequence_numbers(tmp_path):
    box = str(tmp_path)
    seqs = []
    ts = [threading.Thread(target=lambda: seqs.append(hook._reserve(box, {'x': 1})))
          for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(seqs) == list(range(1, 9))
