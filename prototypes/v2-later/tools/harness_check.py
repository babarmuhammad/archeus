"""LV2-1 W0: prove the harness and the scorer before any participant sees them.

1. Scorer self-test: synthetic sessions built to pass or to miss specific criteria; the scorer must
   report exactly those misses, per participant, and must call a short participant list INCOMPLETE.
2. Counterbalancing: the plans for participants 1-8 rotate variant order, fixture and arms.
3. Harness drive: for participant 1, every desktop stimulus opens in its popup with no page error
   and fills every answer key; every device trial's key loads.
Prototype tooling.   py prototypes/v2-later/tools/harness_check.py
"""
import json
import os
import subprocess
import sys
import tempfile

from serve import results, serve

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def check(name, cond, detail=''):
    print(('ok   ' if cond else 'FAIL ') + name + (('  ' + str(detail)) if detail and not cond else ''))
    if not cond:
        FAILS.append(name)


def q(n, mark='ok', secs=4.0, wrong=0, override=None):
    out = {str(j): {'mark': mark, 'secs': secs, 'wrong': wrong} for j in range(n)}
    for j, v in (override or {}).items():
        out[str(j)].update(v)
    return out


def session(pid, n, profile, bar=('two', 'one'), names='new', hdr='28', miss=None):
    miss = miss or {}
    T = {}
    for dev in ('desktop', 'phone'):
        for v in ('a', 'b') + (('c',) if dev == 'desktop' else ()):
            T['h1r-%s-%s' % (dev, v)] = {'part': 'recall', 'device': dev, 'v': v, 'q': q(6, override=miss.get(('recall', dev, v)))}
        for v in ('a', 'b'):
            T['h1f-%s-%s' % (dev, v)] = {'part': 'find', 'device': dev, 'v': v, 'q': q(9, secs=(9.0 if v == 'a' else 5.0), override=miss.get(('find', dev, v)))}
        T['h2-%s-new' % dev] = {'part': 'decide', 'device': dev, 'v': 'c' if dev == 'desktop' else 'b', 'q': q(7, override=miss.get(('decide', dev)))}
        T['h2-%s-v1' % dev] = {'part': 'decide', 'device': dev, 'v': 'a', 'q': q(7, mark='no')}
    for arm in ('p', 'pb', 'prb', 'pbc'):
        good = arm in ('pb', 'prb', 'pbc')
        T['h1c-' + arm] = {'part': 'context', 'device': 'desktop', 'v': 'b', 'arm': arm, 'q': q(3, override={0: {'mark': 'ok' if good else 'no'}, 1: {'mark': 'ok'}})}
    for dev in ('iphone', 'android'):
        base = {'t1': {'ok': True, 'secs': 3}, 't2': {'ok': True, 'secs': 3}, 't3': {'step_ok': True, 'project_ok': True, 'taps': '1', 'secs': 4},
                't4': {'presses': '2', 'secs': 2.5}, 't5': {'stayed': True}, 't6': {'stayed': True}, 'ap1': {'ok': True, 'secs': 3}, 'ap2': {'ok': True, 'secs': 4},
                'why': {'ok': True, 'secs': 8}, 't7': {'ok': True}}
        for k, v in miss.get(('h3', dev), {}).items():
            base[k].update(v)
        T['h3-' + dev] = {'part': 'phone', 'device': dev, 'v': 'b', 'q': base}
    return {'pid': pid, 'n': n, 'names': names, 'hdr': hdr, 'bar': list(bar), 'profile': profile, 'trials': T}


def scorer():
    d = tempfile.mkdtemp(prefix='lv21-check-')
    S = [session('P1', 1, {'owner': True}),
         session('P2', 2, {'new_to_archeus': True}, names='v1', bar=('one', 'two')),
         session('P3', 3, {'new_to_archeus': True}, hdr='20', miss={('find', 'desktop', 'b'): {8: {'mark': 'inv'}}}),
         session('P4', 4, {'daily_agent': True}, names='v1', hdr='20', miss={('recall', 'phone', 'b'): {0: {'mark': 'no'}, 1: {'mark': 'no'}}}),
         session('P5', 5, {}, miss={('h3', 'android'): {'t4': {'armed_as_stopped': True}}, ('find', 'phone', 'b'): {3: {'secs': 61}}})]
    for s in S:
        json.dump(s, open(os.path.join(d, 'lv21-%s.json' % s['pid']), 'w'))
    env = dict(os.environ, LV21_SESSIONS=d, LV21_OUT=os.path.join(d, 'out.json'), PYTHONIOENCODING='utf-8')
    subprocess.run([sys.executable, os.path.join(HERE, 'h_score.py')], env=env, check=True, capture_output=True)
    R = json.load(open(os.path.join(d, 'out.json'), encoding='utf-8'))
    misses = {pid: sorted(k for k, v in r.items() if not k.startswith('_') and v is False) for pid, r in R['participants'].items()}
    check('scorer: complete mix is COMPLETE', R['status'] == 'COMPLETE', R['status'])
    check('scorer: a perfect participant misses nothing', misses['P1'] == [] and misses['P2'] == [], misses)
    check('scorer: an invented remote is a miss for that participant only', misses['P3'] == ['H1 zero invented remotes'], misses['P3'])
    check('scorer: 4/6 phone recall is a miss (not averaged)', misses['P4'] == ['H1 recall B >= 5/6 (phone)'], misses['P4'])
    check('scorer: armed-as-stopped and a 61 s task are both misses', misses['P5'] == ['H1 find each < 60 s (phone)', 'H3 armed never described as stopped (android)'], misses['P5'])
    check('scorer: row context keeps the smallest arm that is always right', R['group']['rule: row context']['keep'] == 'pb', R['group']['rule: row context'])
    check('scorer: B beats A on 9/9 when every B task is faster', R['group']['H1 B median beats A on >= 7/9 tasks (desktop)']['pass'] is True)
    check('scorer: names tie keeps V1', R['group']['rule: names']['keep'] == 'v1', R['group']['rule: names'])
    os.remove(os.path.join(d, 'lv21-P5.json'))
    subprocess.run([sys.executable, os.path.join(HERE, 'h_score.py')], env=env, check=True, capture_output=True)
    R = json.load(open(os.path.join(d, 'out.json'), encoding='utf-8'))
    check('scorer: four participants is INCOMPLETE', R['status'].startswith('INCOMPLETE'), R['status'])


def harness():
    from playwright.sync_api import sync_playwright
    base, srv = serve()
    out = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        c = b.new_context(viewport={'width': 1500, 'height': 1000})
        pg = c.new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(base + 'harness.html')
        plans = pg.evaluate('[1,2,3,4,5,6,7,8].map(n => window.__plan(n))')
        for P in plans:
            T = P['trials']
            rd = [t for t in T if t['part'] == 'recall' and t['device'] == 'desktop']
            check('plan %d: desktop recall shows A, B, C on three different days' % P['n'], sorted(t['v'] for t in rd) == ['a', 'b', 'c'] and len({t['fx'] for t in rd}) == 3)
            for dev in ('desktop', 'phone'):
                f = [t for t in T if t['part'] == 'find' and t['device'] == dev]
                check('plan %d: %s findability A and B on different days' % (P['n'], dev), len({t['fx'] for t in f}) == 2)
            check('plan %d: four context arms' % P['n'], sorted(t['arm'] for t in T if t['part'] == 'context') == ['p', 'pb', 'pbc', 'prb'])
        firsts = [P['trials'][0]['v'] for P in plans[:3]]
        check('plans 1-3: each variant leads desktop recall once', sorted(firsts) == ['a', 'b', 'c'], firsts)
        check('plans 1-8: names alternate, header spacing 28,28,20,20, bar order alternates',
              [P['names'] for P in plans[:4]] == ['new', 'v1', 'new', 'v1'] and [P['hdr'] for P in plans[:4]] == ['28', '28', '20', '20'] and plans[0]['bar'] != plans[1]['bar'])
        pg.fill('#pid', 'CHECK')
        pg.fill('#pn', '1')
        pg.click('#build')
        sections = pg.locator('section.trial')
        n_ok = 0
        for i in range(sections.count()):
            s = sections.nth(i)
            if s.locator('[data-open]').count():
                with pg.expect_popup() as pop:
                    s.locator('[data-open]').click()
                w = pop.value
                perr = []
                w.on('pageerror', lambda e: perr.append(str(e)))
                w.wait_for_load_state()
                pg.wait_for_timeout(700)
                w.close()
            elif s.locator('[data-keys]').count():
                s.locator('[data-keys]').click()
                pg.wait_for_timeout(900)
                perr = []
            else:
                continue
            keys = s.locator('[data-key]').all_inner_texts()
            good = keys and not any(k.strip() in ('…', '') for k in keys) and not perr
            n_ok += bool(good)
            if not good:
                check('trial %d keys filled' % (i + 1), False, (keys[:3], perr))
        check('harness: every trial with keys filled them (%d)' % n_ok, n_ok >= 10)
        check('harness: no page error', not errs, errs)
        pg.click('#wipe')
        b.close()
    srv.shutdown()
    return out


def phone_server():
    """The H-3 session server's gate, exercised on loopback only (no network exposure)."""
    import http.client
    import http.server
    import threading
    import serve_lan as L
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), L._Gate)
    port = srv.server_address[1]
    L._Gate.allowed_host = '127.0.0.1:%d' % port
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def req(path, method='GET', host=None, cookie=None):
        c = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        h = {'Host': host or L._Gate.allowed_host}
        if cookie:
            h['Cookie'] = cookie
        c.request(method, path, headers=h)
        r = c.getresponse()
        r.read()
        return r.status, r.getheader('Set-Cookie')
    page = '/proto/v2-later/lab/ia.html'
    check('server: no token is 403', req(page)[0] == 403)
    check('server: a wrong token is 403', req('/s/nope/' + page[1:])[0] == 403)
    st, ck = req('/s/%s%s' % (L.TOKEN, page))
    check('server: the path token serves the page and sets an HttpOnly SameSite=Strict cookie', st == 200 and ck and 'HttpOnly' in ck and 'SameSite=Strict' in ck, (st, ck))
    check('server: the cookie serves a root-relative asset', req('/v1styles/tokens.css', cookie='lv21k=' + L.TOKEN)[0] == 200)
    check('server: a forged cookie is 403', req('/v1styles/tokens.css', cookie='lv21k=x' + L.TOKEN)[0] == 403)
    check('server: a rebound Host header is 403', req('/s/%s%s' % (L.TOKEN, page), host='evil.example:%d' % port)[0] == 403)
    check('server: POST is refused', req('/s/%s%s' % (L.TOKEN, page), method='POST')[0] == 405)
    check('server: no directory listing', req('/s/%s/proto/v2-later/lab/' % L.TOKEN)[0] == 404)
    check('server: nothing outside the two roots', req('/s/%s/tools/serve.py' % L.TOKEN)[0] in (403, 404))
    srv.shutdown()
    srv.server_close()


def main():
    scorer()
    phone_server()
    harness()
    print('FAILURES:', FAILS or 'none')
    open(results('lv21', 'harness_check.txt'), 'w', encoding='utf-8').write('FAILURES: %s\n' % (FAILS or 'none'))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
