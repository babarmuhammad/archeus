"""LV2-X.3: a real-data replay. Runs the real Core in-process (TempCore: the runtime, its workers and the
fake harness, exactly as the judge does), drives it through the API to a small busy afternoon, and writes
every read the E prototype would make, verbatim, to lvx/replay.js (window.CORE_REPLAY). Prototype tooling.

  py prototypes/v2-later/tools/lvx_replay.py

Nothing here is invented: the titles and objectives are what a user would type; every id, state, time,
branch and event is Core's. What Core cannot be made to produce without a model (ideas, which need the
brain's intent call) is left out and reported, not faked.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path[:0] = [ROOT, os.path.join(ROOT, 'tests')]
home = tempfile.mkdtemp(prefix='arch-replay-')
os.environ['ARCHEUS_HOME'] = home
os.environ.pop('ARCHEUS_EXECUTION_ID', None)

from archeus.core import engine, ports, runtime  # noqa: E402
from v1.judge.http import TempCore  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), '..', 'lvx', 'replay.js')
task = engine.SKELETON_PLAN['tasks'][0]
WRITE = dict(engine.SKELETON_PLAN, summary='Change the code, then check it',
             tasks=[dict(task, key='edit', title='Make the change'),
                    dict(task, key='check', title='Run the checks', depends_on=['edit'])])
DEPLOY = dict(engine.SKELETON_PLAN, summary='Build the site, deploy it to staging, then smoke-test it',
              tasks=[dict(task, key='build', title='Build the site'),
                     dict(task, key='deploy', title='Deploy to staging', action_classes=['deploy'], depends_on=['build']),
                     dict(task, key='smoke', title='Smoke-test staging', depends_on=['deploy'])])
brain = ports.FixedPlanBrain(WRITE)
P = runtime.Ports(brain=brain)
tc = TempCore(home, ports=P).start()
k = [0]


def call(method, path, body=None):
    k[0] += 1
    if method == 'POST':
        body = dict(body or {}, idempotency_key='r-%d-%f' % (k[0], time.time()))
    r = tc.http(method, path, body=body) if body is not None else tc.http(method, path)
    if r.status != 200:
        print('!', method, path, r.status, r.body[:300])
        return None
    return r.json()


def state(mid):
    return call('GET', '/v1/missions/' + mid)['state']


def wait(mid, want, t=60):
    d = time.monotonic() + t
    while state(mid) not in want:
        if time.monotonic() > d:
            print('  timeout', mid, state(mid), 'want', want)
            return False
        time.sleep(0.15)
    return True


def repo(name):
    d = os.path.join(home, 'repos', name)
    os.makedirs(d)
    for a in (['init', '-q', '-b', 'main'], ['config', 'user.email', 'r@example.org'], ['config', 'user.name', 'replay']):
        subprocess.run(['git'] + a, cwd=d, check=True)
    open(os.path.join(d, 'README.md'), 'w').write('# %s\n' % name)
    subprocess.run(['git', 'add', '.'], cwd=d, check=True)
    subprocess.run(['git', 'commit', '-q', '-m', 'start'], cwd=d, check=True)
    return d


def pending(mid):
    return [a for a in call('GET', '/v1/approvals?state=PENDING&mission=' + mid)['approvals']]


def approve_all(mid):
    for a in pending(mid):
        call('POST', '/v1/approvals/%s/decide' % a['id'], {'decision': 'approve'})


def mission(title, objective, pid, plan, scenario=None, approve=True, settle=None):
    brain.plan = plan
    if scenario is not None:
        P.scenarios.clear()
        P.scenarios.update(scenario)
    mid = call('POST', '/v1/missions', {'title': title, 'objective': objective, 'project_id': pid})['id']
    wait(mid, {'APPROVAL_REQUIRED', 'APPROVED', 'EXECUTING', 'BLOCKED', 'COMPLETED', 'REVIEWING', 'FAILED'})
    if approve:
        approve_all(mid)
    if settle:
        wait(mid, settle)
    print('  %-40s %s' % (title[:40], state(mid)))
    return mid


pids = {n: call('POST', '/v1/projects', {'name': n, 'root_paths': [repo(n)]})['id'] for n in ('invoicing', 'website', 'archeus')}
print('projects', pids)
LONG = {'t1': [{'emit': {'type': 'assistant', 'text': 'Working on it.'}}, {'sleep': 900}]}
DONE = {}
FAIL = {'t1': [{'emit': {'type': 'assistant', 'text': 'Trying.'}}, {'exit': 3}]}
ids = {}
ids['done'] = mission('Tidy the release checklist', 'One checklist with no duplicates', pids['website'], WRITE, DONE,
                      settle={'COMPLETED', 'REVIEWING'})
ids['fail'] = mission('Profile the startup path', 'Know where the 1.4 s startup goes', pids['archeus'], WRITE, FAIL,
                      settle={'FAILED', 'BLOCKED', 'REPLANNING'})
ids['twin_a'] = mission('Update the currency formatter', 'Euro amounts keep two decimals and put € after the number',
                        pids['invoicing'], WRITE, LONG, settle={'EXECUTING'})
time.sleep(1.5)
ids['twin_b'] = mission('Update the currency formatter', 'Invoice totals round half-to-even, as the ledger does',
                        pids['invoicing'], WRITE, LONG, settle={'EXECUTING'})
time.sleep(1.5)
ids['wait'] = mission('Deploy release notes to staging', 'The 1.9 release notes are live on staging and the smoke test passes',
                      pids['website'], DEPLOY, None, approve=False)
time.sleep(4)
print({k2: state(v) for k2, v in ids.items()})

snap = {'captured_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'ids': ids}
snap['projects'] = call('GET', '/v1/projects')
snap['missions'] = call('GET', '/v1/missions')
snap['mission'] = {m: call('GET', '/v1/missions/' + m) for m in ids.values()}
snap['plan'] = {m: call('GET', '/v1/missions/%s/plan' % m) for m in ids.values()}
snap['verifications'] = {m: call('GET', '/v1/missions/%s/verifications' % m) for m in ids.values()}
snap['timeline'] = {m: call('GET', '/v1/missions/%s/timeline' % m) for m in ids.values()}
snap['approvals'] = call('GET', '/v1/approvals')
snap['status'] = call('GET', '/v1/status')
snap['events'] = call('GET', '/v1/events?limit=500')
snap['ideas'] = call('GET', '/v1/ideas')
snap['harnesses'] = call('GET', '/v1/harnesses')
tc.stop(kill=True)
# the scratch home's path names this machine's user; it is the one thing redacted
snap = json.loads(json.dumps(snap, ensure_ascii=False).replace(json.dumps(home)[1:-1], '%ARCHEUS_HOME%')
                  .replace(json.dumps(home.lower())[1:-1], '%archeus_home%'))
open(OUT, 'w', encoding='utf-8').write('/* LV2-X.3 replay: the real Core\'s reads, verbatim (tools/lvx_replay.py). */\nwindow.CORE_REPLAY = '
                                       + json.dumps(snap, indent=1, ensure_ascii=False) + ';\n')
print('wrote', OUT, os.path.getsize(OUT), 'bytes')
