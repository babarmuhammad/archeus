"""Helpers the judge scenarios share. Contract-level only: they use a
`CoreClient` and the rig, never Core internals."""

import json
import os
import shutil
import subprocess
import tempfile
import time

import pytest

from archeus.infra import paths

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'fixtures', 'repos')
#: A fixture commit is the same bytes on every machine: no user config, no
#: signing, a fixed identity.
GIT_ENV = {'GIT_AUTHOR_NAME': 'judge', 'GIT_AUTHOR_EMAIL': 'judge@example.invalid',
           'GIT_COMMITTER_NAME': 'judge', 'GIT_COMMITTER_EMAIL': 'judge@example.invalid',
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull}


class FixtureRepo:
    """A real git repository a scenario commits to."""

    def __init__(self, path):
        self.path = path
        self.project_id = self.repository_id = None

    @classmethod
    def create(cls, name, parent):
        """A new repository in *parent* holding fixtures/repos/<name> (all
        of it but `constraints.json`), committed once."""
        dest = tempfile.mkdtemp(prefix=name + '-', dir=parent)
        shutil.copytree(os.path.join(FIXTURES, name), dest, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('constraints.json'))
        repo = cls(dest)
        repo.git('-c', 'init.defaultBranch=main', 'init', '-q')
        repo.commit('fixture %s' % name, {})
        return repo

    @staticmethod
    def constraints(name):
        """The fixture's declared constraints (CoreClient kwargs), if any."""
        spec = os.path.join(FIXTURES, name, 'constraints.json')
        if not os.path.isfile(spec):
            return []
        with open(spec, encoding='utf-8') as f:
            return json.load(f)

    def git(self, *args):
        return subprocess.run(['git', '-c', 'commit.gpgsign=false', *args], cwd=self.path,
                              check=True, capture_output=True, text=True,
                              env=dict(os.environ, **GIT_ENV)).stdout

    def head(self):
        return self.git('rev-parse', 'HEAD').strip()

    def commit(self, message, files):
        """Write *files* ({relative path: text, or None to delete}) and commit
        everything; returns the new HEAD."""
        for rel, text in files.items():
            p = os.path.join(self.path, *rel.split('/'))
            if text is None:
                os.remove(p)
                continue
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w', encoding='utf-8', newline='\n') as f:
                f.write(text)
        self.git('add', '-A')
        self.git('commit', '-q', '--allow-empty', '-m', message)
        return self.head()

#: Set by the judge's `client` fixture to the binding's `_idle()`: True when
#: nothing in the Core under test can change state on its own, so waiting for a
#: change can only time out. Until an engine runs (P3.5) that is always the
#: case, and a wait fails at once as "not built yet" instead of after 30 s.
idle = None


def wait_for(fn, timeout=30.0, interval=0.05):
    """Poll *fn* until it returns something truthy; fail the test on timeout."""
    deadline = time.monotonic() + timeout
    while True:
        got = fn()
        if got:
            return got
        if idle is not None and idle():
            got = fn()      # read before idle(): what finished in between shows only now
            if got:
                return got
            raise NotImplementedError('waiting for %s, but nothing in this Core advances '
                                      'state on its own yet' % getattr(fn, '__name__', fn))
        if time.monotonic() > deadline:
            raise AssertionError('timed out after %.0fs waiting for %s'
                                 % (timeout, getattr(fn, '__name__', fn)))
        time.sleep(interval)


def wait_state(client, mission_id, state, timeout=30.0):
    def reached():
        m = client.get_mission(mission_id)
        return m if m['state'] == state else None
    reached.__name__ = 'mission %s -> %s' % (mission_id, state)
    return wait_for(reached, timeout)


def events_of(client, type_, after=0):
    return [e for e in client.events(after) if e['type'] == type_]


def mission_states(client, mission_id):
    """The `to` of every mission.state_changed for one mission, in order."""
    return [e['payload']['to'] for e in events_of(client, 'mission.state_changed')
            if e['subject']['id'] == mission_id]


def knowledge_pass(client, project_id):
    """The project's initial knowledge pass once it has ended (P6, K1-K3)."""
    def ended():
        (p,) = [x for x in client.status(project_id=project_id)['projects']
                if x['id'] == project_id]
        kp = p['knowledge_pass']
        return kp if kp and kp['state'] not in ('queued', 'running') else None
    ended.__name__ = 'the knowledge pass of %s to end' % project_id
    return wait_for(ended)


class Rig:
    """What a scenario controls besides Core: the fake harness's scripts, fake
    usage and fake time, and Core's own process (testing-strategy §1.1 fixtures).

    P1 declares it; `TempCore` (P3.5) and the phases that need each lever give
    it bodies. Until then every lever fails loudly, like `InProcessClient`.
    """

    def __init__(self, client=None):
        self.client = client

    def _pending(self, what, phase):
        raise NotImplementedError('judge rig: %s arrives with %s' % (what, phase))

    def script_harness(self, task_key, steps):
        """Make the fake harness run *steps* (fake_agent.py format) for the task
        keyed *task_key* (`t1`, `t2`, … — Core keys a plan's tasks, P8). Given a
        body in P8, the first phase whose scenario (S6) needs it."""
        if not hasattr(self.client, '_script'):
            self._pending('scripting the fake harness for this binding', 'P8')
        self.client._script(task_key, list(steps))

    def usage(self, account_id, window, utilisation_pct):
        """Report provider usage for an account (FakeUsageFeed)."""
        self._pending('the fake usage feed', 'P10')

    def advance(self, seconds):
        """Move fake time forward (FakeClock)."""
        self._pending('the fake clock', 'P10')

    def restart_core(self, *, kill=True):
        """Kill (or stop) Core and start it again on the same ARCHEUS_HOME.
        In-process, a kill drops queued commands and closes without draining;
        a real process kill is tests/v1/integration's (a child process)."""
        if not hasattr(self.client, '_restart'):
            self._pending('Core restarts for this binding', 'P3.5')
        self.client._restart(kill=kill)

    def fixture_repo(self, name):
        """A throwaway git repository from tests/v1/fixtures/repos/<name>,
        registered as a project through the contract (`create_project`, then
        `declare_constraint` for each entry of its `constraints.json`), and
        returned only once Core has assessed its first revision — so a
        scenario always starts from an evaluated baseline."""
        repo = FixtureRepo.create(name, os.path.dirname(paths.archeus_home()))
        project = self.client.create_project(name=name, root_paths=[repo.path])
        repo.project_id = project['project']['id']
        repo.repository_id = project['repositories'][0]['id']
        for c in FixtureRepo.constraints(name):
            self.client.declare_constraint(project_id=repo.project_id, **c)
        self.assessed(repo)
        return repo

    def assessed(self, repo):
        """Wait until *repo*'s assessment is of its current HEAD."""
        def done():
            st = self.client.status(project_id=repo.project_id)
            (r,) = [x for p in st['projects'] for x in p['repositories']
                    if x['id'] == repo.repository_id]
            return (r['architecture_state'] in ('CONSISTENT', 'DRIFTED')
                    and r['last_revision'] == repo.head())
        done.__name__ = 'the assessment of %s at HEAD' % repo.path
        return wait_for(done)

    def device(self, name, scopes):
        """A paired device's own client (its token, its scopes)."""
        self._pending('paired devices', 'P15')

    def revoke(self, device):
        self._pending('device revocation', 'P15')

    def principal_client(self, kind):
        """A client acting as a non-user principal (brain, execution, …),
        on the same Core (P9)."""
        return self.client._principal_client(kind)

    def estop_without_core(self):
        """Run `archeus estop` with Core stopped."""
        self._pending('the Core-less e-stop', 'P11')

    def http_get(self, path):
        """A raw authenticated GET; only the HTTP binding has a wire to send it on."""
        if not hasattr(self.client, '_http_get'):
            pytest.skip('raw HTTP exists only over the http binding')
        return self.client._http_get(path)

    def device_token(self):
        if not hasattr(self.client, 'token'):
            pytest.skip('device tokens exist only over the http binding')
        return self.client.token

    def gui(self):
        """The SPA driven by Playwright against this Core."""
        self._pending('the SPA driver', 'P16')

    def tui(self):
        self._pending('the TUI driver', 'P17')

    def cli(self, *argv):
        self._pending('the V1 CLI', 'P3.5')

    def fixture_legacy_home(self, name):
        self._pending('fixture legacy homes', 'P22')

    def import_legacy(self, legacy_home):
        self._pending('the legacy importer', 'P22')
