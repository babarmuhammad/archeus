"""`metrics_daily` (P21 slice D, p21-design-gate D2, plan section 28): Core's
nightly figures, one row per finished UTC day, written once by this worker.

Every figure is read from what Core already recorded (events, missions,
approvals, route decisions, the usage ledger, context packages); a figure the
day gives nothing to measure is None, never 0. A day is computed only after it
has ended, so a row is final and never rewritten.
"""

import datetime as dt
import json
import statistics

DAY = dt.timedelta(days=1)
ENDS = ('COMPLETED', 'FAILED')


def _today():
    return dt.datetime.now(dt.timezone.utc).date()


def _ts(s):
    return dt.datetime.fromisoformat(s.replace('Z', '+00:00'))


def _rate(part, whole):
    return round(part / whole, 4) if whole else None


def compute(conn, day):
    """The figures for UTC *day* ('YYYY-MM-DD') from a read connection."""
    lo = day + 'T00:00:00'
    hi = (dt.date.fromisoformat(day) + DAY).isoformat() + 'T00:00:00'
    # ponytail: events.at has no index, so each day scans the log; add one if
    # a long history makes the nightly pass slow
    changes = conn.execute(
        "SELECT type, subject_id, at, payload FROM events WHERE at >= ? AND at < ? "
        "AND type IN ('mission.state_changed', 'verification.state_changed')", (lo, hi)).fetchall()
    ended, verdicts = {}, []
    for etype, sid, at, payload in changes:
        to = json.loads(payload).get('to')
        if etype == 'mission.state_changed' and to in ENDS:
            ended[sid] = (to, at)
        elif etype == 'verification.state_changed' and to in ('PASSED', 'FAILED'):
            verdicts.append(to)
    done = [m for m, (to, _a) in ended.items() if to == 'COMPLETED']
    created = dict(conn.execute(
        'SELECT id, created_at FROM missions WHERE id IN (%s)' % ','.join('?' * len(ended)),
        list(ended)).fetchall()) if ended else {}
    durations = [(_ts(ended[m][1]) - _ts(created[m])).total_seconds()
                 for m in done if m in created]

    approvals = conn.execute(
        'SELECT COUNT(*) FROM approvals WHERE mission_id IN (%s)' % ','.join('?' * len(ended)),
        list(ended)).fetchone()[0] if ended else 0

    routed = [json.loads(b).get('result') for (b,) in conn.execute(
        'SELECT body FROM route_decisions WHERE created_at >= ? AND created_at < ?', (lo, hi))]
    chosen = [r for r in routed if r in ('selected', 'fallback')]

    bands = {}
    for m in ended:
        plan = conn.execute('SELECT body FROM plans WHERE mission_id = ? ORDER BY plan_version '
                            'DESC LIMIT 1', (m,)).fetchone()
        band = (json.loads(plan[0]).get('estimated_cost') if plan else None) or 'unknown'
        costs = [json.loads(b).get('cost_usd') for (b,) in conn.execute(
            'SELECT u.body FROM usage_ledger u LEFT JOIN executions e ON e.id = u.execution_id '
            'LEFT JOIN route_decisions r ON r.id = u.route_decision_id '
            'WHERE e.mission_id = ? OR r.mission_id = ?', (m, m))]
        reported = [c for c in costs if c is not None]
        bands.setdefault(band, []).append(sum(reported) if reported else None)

    tokens = {}
    for (b,) in conn.execute('SELECT body FROM route_decisions WHERE created_at >= ? AND '
                             'created_at < ? AND task_id IS NOT NULL', (lo, hi)):
        rd = json.loads(b)
        if not rd.get('context_package_id'):
            continue
        task = conn.execute('SELECT body FROM tasks WHERE id = ?', (rd['task_id'],)).fetchone()
        pkg = conn.execute('SELECT body FROM context_packages WHERE id = ?',
                           (rd['context_package_id'],)).fetchone()
        used = (json.loads(pkg[0]).get('budget') or {}).get('used_tokens') if pkg else None
        if task and used is not None:
            kind = json.loads(task[0]).get('kind') or 'unknown'
            tokens[kind] = tokens.get(kind, 0) + used

    return {
        'missions_completed': len(done),
        'missions_failed': len(ended) - len(done),
        'median_time_to_complete_s': statistics.median(durations) if durations else None,
        'approvals_per_mission': _rate(approvals, len(ended)),
        'fallback_rate': _rate(chosen.count('fallback'), len(chosen)),
        'verification_failure_rate': _rate(verdicts.count('FAILED'), len(verdicts)),
        'cost_per_mission_band': {
            band: {'missions': len(v),
                   'cost_usd_mean': (round(sum(c for c in v if c is not None)
                                           / len([c for c in v if c is not None]), 6)
                                     if any(c is not None for c in v) else None)}
            for band, v in sorted(bands.items())},
        'context_tokens_per_task_kind': dict(sorted(tokens.items())),
    }


def record(tx, *, day, metrics):
    """Writer command: a finished day's row, once."""
    tx.execute('INSERT INTO metrics_daily (day, metrics, computed_at) VALUES (?, ?, ?) '
               'ON CONFLICT (day) DO NOTHING',
               (day, json.dumps(metrics, sort_keys=True), tx.now))


MAX_DAYS = 90


def daily(conn, days):
    """The newest *days* rows, newest first: what Control -> About -> Health
    shows (P21 D12). A figure stays None (unknown) as it was recorded."""
    got = conn.execute('SELECT day, metrics, computed_at FROM metrics_daily '
                       'ORDER BY day DESC LIMIT ?', (days,))
    return {'days': [{'day': d, 'metrics': json.loads(m), 'computed_at': c}
                     for d, m, c in got]}


def missing_days(conn, today):
    """Finished days since the first event that have no row yet, oldest first."""
    first = conn.execute('SELECT MIN(at) FROM events').fetchone()[0]
    if first is None:
        return []
    have = {r[0] for r in conn.execute('SELECT day FROM metrics_daily')}
    d, out = dt.date.fromisoformat(first[:10]), []
    while d < today:
        if d.isoformat() not in have:
            out.append(d.isoformat())
        d += DAY
    return out


class Metrics:
    """`archeus-metrics`: a WorldLoop worker that fills in each finished day."""

    def __init__(self, db, *, today=_today):
        self.db, self.today = db, today
        self.on_wake = None
        self.stopping = lambda: False
        # WorldLoop runs a pass after every commit; once every finished day has
        # its row, nothing is due until the date changes, so skip the log scan
        self._filled_through = None

    def sweep(self):
        return []

    def pending(self):
        today = self.today()
        if self._filled_through == today:
            return 0
        with self.db.read() as conn:
            return len(missing_days(conn, today))

    def pass_once(self):
        today = self.today()
        if self._filled_through == today:
            return {'changed': False}
        with self.db.read() as conn:
            days = missing_days(conn, today)
            if not days:
                self._filled_through = today
                return {'changed': False}
            figures = compute(conn, days[0])
        self.db.writer.execute(record, {'day': days[0], 'metrics': figures})
        return {'changed': True}
