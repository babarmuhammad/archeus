"""Helpers the judge scenarios share. Contract-level only: they use a
`CoreClient` and the rig, never Core internals."""

import time

import pytest

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
        """Make the fake harness run *steps* (fake_agent.py format) for a task."""
        self._pending('scripting the fake harness per scenario', 'the first phase whose '
                      'scenario needs it (P9)')

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
        """A throwaway git repository from tests/v1/fixtures/repos/<name>."""
        self._pending('fixture repositories', 'P4')

    def device(self, name, scopes):
        """A paired device's own client (its token, its scopes)."""
        self._pending('paired devices', 'P15')

    def revoke(self, device):
        self._pending('device revocation', 'P15')

    def principal_client(self, kind):
        """A client acting as a non-user principal (brain, execution, …)."""
        self._pending('principal-scoped clients', 'P9')

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
