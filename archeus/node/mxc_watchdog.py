"""Independent watchdog over recorded execution Jobs: injected observation only.

The watchdog holds no outer Job handle and no process handle. It can ask for the
kill of a job Core recorded while it was alive, and nothing else: it never adopts
an execution that was not recorded, never re-adopts one after it has acted or
stood down, and never asks for the kill of a PID whose creation time no longer
matches the record (a reused PID is somebody else's process).

Every observation is read to the end before the first kill is requested, so a
reader that raises, or one that answers with something unreadable, leaves the
watchdog UNCERTAIN with a recorded verdict and no kill requested at all. Uncertain
is never retried by the watchdog itself; the report is what the supervisor acts on.
"""

import math


ARMED = 'ARMED'
FIRED = 'FIRED'
STOOD_DOWN = 'STOOD_DOWN'
UNCERTAIN = 'UNCERTAIN'
STATES = (ARMED, FIRED, STOOD_DOWN, UNCERTAIN)

KILLED = 'KILLED'
KILL_FAILED = 'KILL_FAILED'
KILL_UNVERIFIED = 'KILL_UNVERIFIED'
ALREADY_ABSENT = 'ALREADY_ABSENT'
SKIPPED_REUSED_PID = 'SKIPPED_REUSED_PID'

JOB_FIELDS = {'execution_id', 'pid', 'create_time', 'job_ref'}
HEARTBEAT_FIELDS = {'seq', 'sent_at'}


class WatchdogUnavailable(ValueError):
    pass


def _number(value):
    if type(value) is bool or type(value) not in (int, float):
        return False
    return type(value) is int or math.isfinite(value)


def _text(value):
    return isinstance(value, str) and bool(value) and '\0' not in value


def _job_problem(record):
    if not isinstance(record, dict) or set(record) != JOB_FIELDS:
        return 'malformed job record'
    if not _text(record['execution_id']):
        return 'invalid execution id'
    for name in ('pid', 'create_time'):
        if type(record[name]) is not int or record[name] <= 0:
            return 'invalid ' + name
    if record['job_ref'] is None:
        return 'missing job ref'
    return None


def _heartbeat_problem(record, last_seq, armed_at, now):
    if not isinstance(record, dict) or set(record) != HEARTBEAT_FIELDS:
        return 'malformed heartbeat record'
    if type(record['seq']) is not int or not _number(record['sent_at']):
        return 'malformed heartbeat record'
    if record['seq'] <= last_seq:
        return 'replayed heartbeat sequence'
    if not armed_at <= record['sent_at'] <= now:
        return 'heartbeat outside the armed clock window'
    return None


class Watchdog:
    def __init__(self, *, clock, deadline_s, channel, core_alive, identity_reader, kill):
        if not _number(deadline_s) or deadline_s <= 0:
            raise WatchdogUnavailable('deadline must be a positive number')
        for name, reader in (('clock', clock), ('channel', channel), ('core_alive', core_alive),
                             ('identity_reader', identity_reader), ('kill', kill)):
            if not callable(reader):
                raise WatchdogUnavailable('%s must be injected' % name)
        self.clock, self.deadline_s = clock, deadline_s
        self.channel, self.core_alive = channel, core_alive
        self.identity_reader, self.kill = identity_reader, kill
        self.state, self.reason = ARMED, 'armed'
        self.jobs, self.verdicts = [], []
        self.last_seq, self.last_beat = 0, None
        try:
            armed_at = clock()
        except Exception:
            raise WatchdogUnavailable('clock unreadable at arm time') from None
        if not _number(armed_at) or armed_at < 0:
            raise WatchdogUnavailable('clock malformed at arm time')
        self.armed_at = armed_at

    def record(self, job):
        self._refuse_if_terminal('record a job')
        problem = _job_problem(job)
        if problem is not None:
            raise WatchdogUnavailable(problem)
        if any(recorded['execution_id'] == job['execution_id'] for recorded in self.jobs):
            raise WatchdogUnavailable('execution already recorded')
        if any(recorded['job_ref'] == job['job_ref'] for recorded in self.jobs):
            raise WatchdogUnavailable('job ref already recorded')
        self.jobs.append(dict(job))
        return True

    def stand_down(self, reason='stood_down'):
        self._refuse_if_terminal('stand down')
        if not _text(reason):
            raise WatchdogUnavailable('invalid stand-down reason')
        return self._set(STOOD_DOWN, reason)

    def tick(self):
        if self.state is not ARMED:
            return self.state
        try:
            now = self.clock()
        except Exception:
            return self._set(UNCERTAIN, 'clock read failed')
        if not _number(now) or now < self._quiet_since():
            return self._set(UNCERTAIN, 'malformed clock observation')
        try:
            alive = self.core_alive()
        except Exception:
            return self._set(UNCERTAIN, 'core_alive read failed')
        if type(alive) is not bool:
            return self._set(UNCERTAIN, 'malformed core_alive observation')
        try:
            heartbeats = list(self.channel())
        except Exception:
            return self._set(UNCERTAIN, 'heartbeat channel read failed')
        problem = None
        for beat in heartbeats:
            problem = _heartbeat_problem(beat, self.last_seq, self.armed_at, now)
            if problem is not None:
                break
        if problem is not None:
            return self._set(UNCERTAIN, problem)
        for beat in heartbeats:
            self.last_seq = beat['seq']
            if self.last_beat is None or beat['sent_at'] > self.last_beat:
                self.last_beat = beat['sent_at']
        if alive is False:
            return self._fire('core_dead')
        if now - self._quiet_since() >= self.deadline_s:
            return self._fire('core_silent')
        return self.state

    def report(self):
        return {'state': self.state, 'reason': self.reason, 'deadline_s': self.deadline_s,
                'armed_at': self.armed_at, 'last_beat': self.last_beat,
                'recorded': [recorded['execution_id'] for recorded in self.jobs],
                'verdicts': [dict(row) for row in self.verdicts]}

    def _quiet_since(self):
        return self.last_beat if self.last_beat is not None else self.armed_at

    def _refuse_if_terminal(self, action):
        if self.state is not ARMED:
            raise WatchdogUnavailable('cannot %s from %s' % (action, self.state))

    def _set(self, state, reason):
        self.state, self.reason = state, reason
        self.verdicts.append({'execution_id': None, 'verdict': state, 'reason': reason})
        return state

    def _observe(self, reason):
        observations = []
        for recorded in self.jobs:
            try:
                current = self.identity_reader(recorded['pid'])
            except Exception:
                return None, 'identity read failed'
            if current is None:
                observations.append((recorded, ALREADY_ABSENT, 'process already absent', False))
            elif type(current) is not int or current <= 0:
                return None, 'malformed identity observation'
            elif current != recorded['create_time']:
                observations.append((recorded, SKIPPED_REUSED_PID,
                                     'pid creation time differs from record', False))
            else:
                observations.append((recorded, KILLED, reason, True))
        return observations, None

    def _fire(self, reason):
        observations, problem = self._observe(reason)
        if problem is not None:
            return self._set(UNCERTAIN, problem)
        unverified = False
        for recorded, verdict, why, killable in observations:
            if killable:
                try:
                    if self.kill(recorded['job_ref']) is not True:
                        verdict, why = KILL_UNVERIFIED, 'kill did not confirm'
                except Exception:
                    verdict, why = KILL_FAILED, 'kill raised'
                unverified = unverified or verdict != KILLED
            self.verdicts.append({'execution_id': recorded['execution_id'],
                                  'verdict': verdict, 'reason': why})
        if unverified:
            return self._set(UNCERTAIN, 'kill not verified')
        return self._set(FIRED, reason)
