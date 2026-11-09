"""The watchdog host (PV-20 B13): a small separate process that runs `Watchdog` over the
heartbeat channel and ends what Core recorded when Core goes silent or dies.

    py -m archeus.node.mxc_watchdog_host

It is closed: `HOST_ENABLED` is False and the native process readers it needs are not
built, so `main` refuses to start. Importing this module spawns nothing and loads
nothing native.

What it may end is only what the ledger says Core launched: a registration is watched
only if the journal's ownership record names the same pid and creation time, the kill is
asked again against that record, and the process table is read by creation time too,
never by pid alone. A hung Core (alive, silent) gets the STOP sentinel first, as the
Core-less e-stop does (design 3.7, item 83), then the same identity-checked kill; a dead
Core needs no sentinel, its Job is already closed. The sentinel not being verifiable
never withholds the kill, it is recorded.

The Job Core holds stays the Core-death authority (threat model, "Decision: Core death").
This host is the belt for what outlived it.
"""

import argparse
import sys
import time

from . import mxc_heartbeat, mxc_ledger, mxc_watchdog
from .pv20_switches import enabled

HOST_ENABLED = False

IDLE = 'IDLE'
OWNED_OPS = ['intent', 'ownership']


class WatchdogHost:
    def __init__(self, *, channel, clock, deadline_s, core, identity_reader, terminate,
                 engage_sentinel, journals):
        """*core* is Core's (pid, creation time); *journals* returns the ledger's journals
        by name; *terminate* ends a process by (pid, creation time) and answers whether it
        did; *engage_sentinel* writes the STOP sentinel and answers whether it reads back."""
        self.channel, self.clock, self.deadline_s = channel, clock, deadline_s
        self.core_pid, self.core_create_time = core
        self.identity_reader, self.terminate = identity_reader, terminate
        self.engage_sentinel, self.journals = engage_sentinel, journals
        self.dog, self.pending = None, []
        self.rejected, self.sentinel, self.fault = {}, None, None
        self.core_gone = False
        self._core_seen = None

    def tick(self):
        if not self.done():
            self._advance()
        self.channel.write_status(self.report())
        return self.state()

    def done(self):
        return self.fault is not None or self.core_gone or (
            self.dog is not None and self.dog.state in (mxc_watchdog.FIRED, mxc_watchdog.UNCERTAIN))

    def state(self):
        if self.fault is not None:
            return mxc_watchdog.UNCERTAIN
        return IDLE if self.dog is None else self.dog.state

    def report(self):
        held = self.dog.report() if self.dog is not None else {'recorded': [], 'verdicts': []}
        return {'at': self.clock(), 'state': self.state(),
                'reason': self.fault or (self.dog.reason if self.dog is not None else (
                    'core gone with nothing watched' if self.core_gone else 'idle')),
                'recorded': held['recorded'], 'verdicts': held['verdicts'],
                'rejected': dict(self.rejected), 'sentinel': self.sentinel}

    def _advance(self):
        try:
            for message in self.channel.read():
                getattr(self, '_' + message['kind'])(message)
        except Exception as err:
            self.fault = 'channel read failed: %s' % type(err).__name__
        if self.dog is not None and self.dog.state is mxc_watchdog.ARMED:
            self.dog.tick()
            return
        try:
            alive = self._core_alive()
        except Exception as err:
            self.fault = 'core read failed: %s' % type(err).__name__
            return
        self.core_gone = alive is False

    def _beat(self, message):
        if self.dog is not None and message['sent_at'] >= self.dog.armed_at:
            self.pending.append({'seq': message['seq'], 'sent_at': message['sent_at']})

    def _register(self, message):
        name = message['execution_id']
        why = self._ownership_problem(name, message['pid'], message['create_time'])
        if why is None:
            if self.dog is None or self.dog.state is mxc_watchdog.STOOD_DOWN:
                self.dog, self.pending = self._arm(), []
            try:
                self.dog.record({'execution_id': name, 'pid': message['pid'],
                                 'create_time': message['create_time'], 'job_ref': name})
            except mxc_watchdog.WatchdogUnavailable as err:
                why = str(err)
        if why is not None:
            self.rejected[name] = why

    def _stand_down(self, message):
        if (self.dog is not None and self.dog.state is mxc_watchdog.ARMED
                and self.dog.report()['recorded'] == [message['execution_id']]):
            self.dog.stand_down(message['reason'])

    def _arm(self):
        return mxc_watchdog.Watchdog(clock=self.clock, deadline_s=self.deadline_s,
                                     channel=self._drain, core_alive=self._core_alive,
                                     identity_reader=self.identity_reader, kill=self._kill)

    def _drain(self):
        if self.fault is not None:
            raise ValueError(self.fault)
        beats, self.pending = self.pending, []
        return beats

    def _core_alive(self):
        current = self.identity_reader(self.core_pid)
        if current is not None and (type(current) is not int or current <= 0):
            raise ValueError('malformed identity observation')
        self._core_seen = current == self.core_create_time
        return self._core_seen

    def _ownership_problem(self, name, pid, create_time):
        records, invalid = mxc_ledger.read_records(self.journals().get(name), name)
        if invalid or [r['op'] for r in records[:2]] != OWNED_OPS:
            return 'the journal holds no open ownership record'
        if (records[1]['pid'], records[1]['create_time']) != (pid, create_time):
            return 'the ownership record names another process'
        return None

    def _kill(self, name):
        job = next(j for j in self.dog.jobs if j['job_ref'] == name)
        problem = self._ownership_problem(name, job['pid'], job['create_time'])
        if problem is not None:
            raise ValueError(problem)
        if self._core_seen is True and self.sentinel is None:
            try:
                engaged = self.engage_sentinel() is True
            except Exception:
                engaged = False
            self.sentinel = 'engaged' if engaged else 'unverified'
        return self.terminate(job['pid'], job['create_time']) is True

    def run(self, poll_s, sleep=time.sleep, stop=lambda: False):
        while not stop() and not self.done():
            self.tick()
            sleep(poll_s)
        return self.report()


def main(argv=None, *, bindings=None):
    parser = argparse.ArgumentParser(prog='archeus.node.mxc_watchdog_host')
    parser.add_argument('--root', required=True)
    parser.add_argument('--ledger', required=True)
    parser.add_argument('--core-pid', type=int, required=True)
    parser.add_argument('--core-create-time', type=int, required=True)
    parser.add_argument('--deadline-s', type=float, required=True)
    parser.add_argument('--poll-s', type=float, required=True)
    args = parser.parse_args(argv)
    if bindings is None or enabled(bindings.get('switches'), 'host', HOST_ENABLED) is not True:
        print('the watchdog host is closed', file=sys.stderr)
        return 2
    parts = {name: part for name, part in bindings.items() if name != 'switches'}
    host = WatchdogHost(channel=mxc_heartbeat.Channel(args.root), deadline_s=args.deadline_s,
                        core=(args.core_pid, args.core_create_time),
                        journals=mxc_ledger.Ledger(args.ledger).journals, **parts)
    report = host.run(args.poll_s)
    return 0 if report['state'] in (mxc_watchdog.FIRED, mxc_watchdog.STOOD_DOWN, IDLE) else 3


if __name__ == '__main__':
    sys.exit(main())
