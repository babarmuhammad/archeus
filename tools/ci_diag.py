"""Summarise a CI diagnostics file written under ARCHEUS_CI_DIAG (tests/ci_diag.py).

    python tools/ci_diag.py diag.jsonl [more.jsonl ...]

Prints delimited, greppable sections: the P2 throughput record with its disk,
SQLite and CPU probes; the never-reading-reader record; execution start-up
latencies; per-group and P12 per-file durations with the processes each test
launched; and the process census over the run. Diagnostic only: it never fails.
"""

import collections
import json
import sys

P12_FILES = ('tests/v1/integration/test_sessions.py', 'tests/v1/integration/test_sessions_http.py',
             'tests/v1/judge/test_c01_resume_continuity.py', 'tests/v1/judge/test_c03_session_handoff.py',
             'tests/v1/judge/test_c04_session_model_and_concurrency.py',
             'tests/v1/judge/test_h01_r01_session_harnesses.py',
             'tests/v1/judge/test_s02_long_mission_handoffs.py',
             'tests/v1/judge/test_s04_limit_and_fallback.py',
             'tests/v1/unit/test_session_boundaries.py', 'tests/v1/unit/test_session_units.py')


def pct(xs, q):
    xs = sorted(x for x in xs if x is not None)
    return xs[min(len(xs) - 1, int(len(xs) * q))] if xs else None


def group(test_id):
    f = test_id.split('::')[0]
    return '/'.join(f.split('/')[:3]) if f.startswith('tests/v1/') else 'tests (legacy)'


def total(t):
    return t.get('setup', 0) + t.get('call', 0) + t.get('teardown', 0)


def show(path):
    recs = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            try:
                recs.append(json.loads(line))
            except ValueError:
                pass
    by = collections.defaultdict(list)
    for r in recs:
        by[r['kind']].append(r)
    head = recs[0] if recs else {}
    print('==== ARCHEUS-DIAG %s  job=%s platform=%s py=%s records=%d' % (
        path, head.get('job'), head.get('platform'), head.get('py'), len(recs)))

    for r in by['p2_throughput']:
        print('---- P2 throughput: best %.1f/s (floor %s), batches %s, %d commands, %.2fs wall'
              % (r['best'], r['floor'], r['batch_rates'], r['commands'], r['end'] - r['start']))
        p = r['probes']
        print('     cpu probe %.4fs' % p['cpu_s'])
        for k in ('db_dir', 'runner_temp'):
            if k in p:
                v = p[k]
                if 'error' in v:
                    print('     %-11s %s ERROR %s' % (k, v['path'], v['error']))
                    continue
                print('     %-11s %s  fsync p50 %.2fms p95 %.2fms max %.1fms | sqlite commit '
                      'p50 %.2fms p95 %.2fms max %.1fms' % (
                          k, v['path'], v['fsync']['p50_ms'], v['fsync']['p95_ms'],
                          v['fsync']['max_ms'], v['sqlite_commit']['p50_ms'],
                          v['sqlite_commit']['p95_ms'], v['sqlite_commit']['max_ms']))
        print('     census', r['census'])
    for r in by['reader_never_reads']:
        print('---- reader-never-reads: %d writes in %.2fs; census %s'
              % (r['writes'], r['seconds'], r['census']))

    tl = [x for r in by['executions'] for x in r['timeline']]
    if tl:
        print('---- execution start-up (%d executions in %d rig tests; ms)' % (
            len(tl), len(by['executions'])))
        for k in ('to_prepared_ms', 'spawn_ms', 'first_output_ms'):
            xs = [x[k] for x in tl]
            print('     %-16s n=%-4d p50 %s  p95 %s  max %s' % (
                k, sum(x is not None for x in xs), pct(xs, .5), pct(xs, .95), pct(xs, 1)))
        slow = sorted((x for x in tl if (x['spawn_ms'] or 0) + (x['first_output_ms'] or 0) > 5000),
                      key=lambda x: -((x['spawn_ms'] or 0) + (x['first_output_ms'] or 0)))
        for x in slow[:10]:
            print('     slow start: %s' % x)
    for r in by['drive_timeout']:
        print('---- drive() TIMEOUT %s after %ss' % (r['test'], r['timeout']))
        for p in r['procs']:
            print('     proc', json.dumps(p)[:600])
        for x in r['timeline']:
            print('     timeline', x)

    tests = by['test']
    if tests:
        g = collections.Counter()
        gl = collections.Counter()
        for t in tests:
            g[group(t['id'])] += total(t)
            gl[group(t['id'])] += t.get('launches', 0)
        print('---- groups (seconds / processes launched from pytest):',
              ' '.join('%s=%.0fs/%d' % (k, g[k], gl[k]) for k in sorted(g)),
              '| total %.0fs, %d launches' % (sum(g.values()), sum(gl.values())))
        files = collections.defaultdict(lambda: [0.0, 0, 0])
        for t in tests:
            f = files[t['id'].split('::')[0]]
            f[0] += total(t)
            f[1] += t.get('launches', 0)
            f[2] += 1
        print('---- P12 files (seconds, launches, tests):')
        for f in P12_FILES:
            if f in files:
                s, n, c = files[f]
                print('     %-62s %7.1fs %5d %4d' % (f, s, n, c))
        print('---- slowest 25 tests (setup/call/teardown, launches):')
        for t in sorted(tests, key=lambda t: -total(t))[:25]:
            print('     %6.2fs  %5.2f/%5.2f/%5.2f  %3d  %s%s' % (
                total(t), t.get('setup', 0), t.get('call', 0), t.get('teardown', 0),
                t.get('launches', 0), t['id'], '' if t['outcome'] == 'passed' else
                '  [%s]' % t['outcome']))
        print('---- most launches, top 15:')
        for t in sorted(tests, key=lambda t: -t.get('launches', 0))[:15]:
            print('     %4d  %6.2fs  %s' % (t.get('launches', 0), total(t), t['id']))
        bad = [t for t in tests if t['outcome'] not in ('passed',) and not
               t['outcome'].startswith('skipped')]
        for t in bad:
            print('     NOT PASSED: %s %s %.2fs' % (t['outcome'], t['id'], total(t)))

    mods = by['module_start']
    if mods:
        print('---- census at each V1 module start (python processes / all processes):')
        prev = None
        for m in mods:
            c = m['census'] or {}
            py = c.get('python')
            if prev is None or py != prev:
                print('     py=%s all=%s threads=%s  %s' % (py, c.get('total'), c.get('threads_here'),
                                                         m['module']))
            prev = py
    for k in ('session_start', 'session_end'):
        for r in by[k]:
            print('---- %s census %s' % (k, r['census']))


if __name__ == '__main__':
    for p in sys.argv[1:]:
        try:
            show(p)
        except Exception as err:                 # diagnostic: never fail the job
            print('ci_diag: could not read %s: %r' % (p, err))
