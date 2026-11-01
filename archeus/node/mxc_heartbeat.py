"""The Core to watchdog-host channel (PV-20 B13): Core's heartbeats, the registration of
each live launch, and the host's published status, in one Core-private directory.

Core writes an append-only line file and reads one status file; the host reads the lines
and writes the status. Nothing here is a grant to an execution: the directory is Core's
and no execution is ever given a path to it. The host still trusts no line: a
registration is checked against the ledger before it is watched.

Both ends are closed by `HEARTBEAT_ENABLED`; nothing in production sets it.
"""

import json
import math
import os
import threading

from claude_sessions import config

from . import mxc_watchdog

HEARTBEAT_ENABLED = False

KINDS = {'beat': {'kind', 'seq', 'sent_at'},
         'register': {'kind', 'execution_id', 'pid', 'create_time'},
         'stand_down': {'kind', 'execution_id', 'reason'}}


class Channel:
    def __init__(self, root):
        self.root = os.fspath(root)
        os.makedirs(self.root, exist_ok=True)
        self.path = os.path.join(self.root, 'channel.jsonl')
        self.status_path = os.path.join(self.root, 'status.json')
        self.offset = 0
        self._lock = threading.Lock()

    def append(self, message):
        if message.get('kind') not in KINDS or set(message) != KINDS[message['kind']]:
            raise ValueError('malformed channel message')
        line = json.dumps(message, sort_keys=True, separators=(',', ':'), allow_nan=False)
        with self._lock, open(self.path, 'ab') as stream:
            stream.write(line.encode('ascii') + b'\n')

    def read(self):
        """The messages appended since the last read. A last line with no newline yet is
        still being written and waits; a shorter file than was read, or a line that is not
        a well-formed message, raises, so the reader never guesses past damage."""
        try:
            with open(self.path, 'rb') as stream:
                stream.seek(0, os.SEEK_END)
                if stream.tell() < self.offset:
                    raise ValueError('the channel shrank')
                stream.seek(self.offset)
                data = stream.read()
        except FileNotFoundError:
            if self.offset:
                raise ValueError('the channel vanished') from None
            return []
        data = data[:data.rfind(b'\n') + 1]
        messages = []
        for line in data.splitlines():
            message = json.loads(line)
            if (not isinstance(message, dict) or message.get('kind') not in KINDS
                    or set(message) != KINDS[message['kind']]):
                raise ValueError('malformed channel message')
            messages.append(message)
        self.offset += len(data)
        return messages

    def write_status(self, status):
        text = json.dumps(status, sort_keys=True, allow_nan=False)
        if not config.write_atomic(self.status_path, text, mode=0o600):
            raise OSError('host status not written')

    def read_status(self):
        try:
            with open(self.status_path, encoding='utf-8') as stream:
                status = json.load(stream)
        except (OSError, ValueError):
            return None
        return status if isinstance(status, dict) else None


def _open():
    if HEARTBEAT_ENABLED is not True:
        raise mxc_watchdog.WatchdogUnavailable('the heartbeat channel is closed')


class HeartbeatSender:
    """Core's heartbeats: one per manager pass, strictly increasing in sequence and never
    older than the one before, so a stepped clock cannot make Core look newer or older."""

    def __init__(self, channel, clock):
        _open()
        self.channel, self.clock = channel, clock
        self.seq, self.sent_at = 0, None

    def beat(self):
        now = self.clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise ValueError('the heartbeat clock is unreadable')
        if self.sent_at is not None:
            now = max(now, self.sent_at)
        self.channel.append({'kind': 'beat', 'seq': self.seq + 1, 'sent_at': now})
        self.seq, self.sent_at = self.seq + 1, now


class WatchdogProxy:
    """What `MxcLaunch` holds as its watchdog when the real one lives in the host: the
    same `record`, `report` and `stand_down`, answered from the host's published status.
    A host that is absent, stale or unreadable is never read as armed: the launch is
    refused at record time, and a clean end is refused at the end."""

    def __init__(self, channel, clock, *, max_age_s):
        _open()
        if type(max_age_s) not in (int, float) or not math.isfinite(max_age_s) or max_age_s <= 0:
            raise mxc_watchdog.WatchdogUnavailable('the status age bound must be positive')
        self.channel, self.clock, self.max_age_s = channel, clock, max_age_s
        self.registered = set()

    def _status(self):
        status = self.channel.read_status()
        if (status is None or type(status.get('at')) not in (int, float)
                or status.get('state') not in mxc_watchdog.STATES + ('IDLE',)
                or not isinstance(status.get('recorded'), list)
                or not isinstance(status.get('rejected'), dict)):
            raise mxc_watchdog.WatchdogUnavailable('the host status is unreadable')
        if not 0 <= self.clock() - status['at'] <= self.max_age_s:
            raise mxc_watchdog.WatchdogUnavailable('the host status is stale')
        return status

    def record(self, job):
        problem = mxc_watchdog._job_problem(job)
        if problem is not None:
            raise mxc_watchdog.WatchdogUnavailable(problem)
        status = self._status()
        if status['state'] not in (mxc_watchdog.ARMED, 'IDLE', mxc_watchdog.STOOD_DOWN):
            raise mxc_watchdog.WatchdogUnavailable('the host is %s' % status['state'])
        self.channel.append({'kind': 'register', 'execution_id': job['execution_id'],
                             'pid': job['pid'], 'create_time': job['create_time']})
        self.registered.add(job['execution_id'])
        return True

    def report(self):
        try:
            status = self._status()
        except mxc_watchdog.WatchdogUnavailable as err:
            return {'state': mxc_watchdog.UNCERTAIN, 'reason': str(err), 'recorded': []}
        refused = sorted(self.registered & set(status['rejected']))
        if refused:
            return {'state': mxc_watchdog.UNCERTAIN, 'recorded': status['recorded'],
                    'reason': 'the host refused %s: %s' % (refused[0], status['rejected'][refused[0]])}
        if status['state'] == 'IDLE':
            return {'state': mxc_watchdog.UNCERTAIN, 'reason': 'the host holds no watch yet',
                    'recorded': status['recorded']}
        return {'state': status['state'], 'reason': status.get('reason', ''),
                'recorded': status['recorded']}

    def stand_down(self, reason='stood_down'):
        report = self.report()
        if report['state'] != mxc_watchdog.ARMED or len(report['recorded']) != 1:
            raise mxc_watchdog.WatchdogUnavailable('the host cannot stand down from here')
        self.channel.append({'kind': 'stand_down', 'execution_id': report['recorded'][0],
                             'reason': reason})
        return True
