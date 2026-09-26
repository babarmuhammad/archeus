"""`archeus core | status | terms | route why` and the reserved V1 verbs (p3.5b design
gate §3 D6, §8).

`claude_sessions/cli.py` sends these verbs here with a lazy import placed
after the statusline fast path, so a conversation turn never pays for them.
`status` talks HTTP only (ADR-0002) and never opens the database; it sends the
local token only once discovery has proved the port belongs to our Core (A5).

`status` reports Core LIVENESS. It is not `CoreClient.status()` — the
cross-project status of S13, which arrives with P4 — and there is no
`/v1/status` route.

Standard library only at import: a deferred verb must cost nothing.
"""

import calendar
import json
import sys
import time

#: Verbs whose behaviour belongs to a later phase: they do nothing, say so,
#: and exit 2, so no script ever sees a verb change from "opened the TUI" to
#: something else.
DEFERRED = {'approve': 'P9', 'pause': 'P11', 'estop': 'P11', 'pair': 'P15'}
VERBS = ('core', 'status', 'terms', 'approve', 'pause', 'route', 'estop', 'pair')

USAGE = """usage: archeus core [--open]    run Archeus Core in the foreground (Ctrl+C stops it)
       archeus status           is Core running? (exit 0 yes, 1 no, 2 discovery failed,
                                3 its engine failed)
       archeus terms            the provider-terms answers (ADR-0021)
       archeus terms <harness> permit|refuse [--rotation permit|refuse]
                                answer it: may Archeus make automated headless calls on
                                this harness's accounts (and rotate across several)?
       archeus route why <id>   why a resource was chosen: a route decision, or the latest
                                one about a task, mission or other subject (P10)"""
_TERMS = {'permit': 'permitted', 'refuse': 'refused'}


def main(argv):
    verb, args = (argv[0] if argv else ''), list(argv[1:])
    if verb in DEFERRED:
        print('archeus %s is not available yet (arrives with %s); nothing was done'
              % (verb, DEFERRED[verb]), file=sys.stderr)
        return 2
    if verb == 'core' and set(args) <= {'--open'}:
        return core(open_browser='--open' in args)
    if verb == 'status' and not args:
        return status()
    if verb == 'terms' and not args:
        return terms()
    if (verb == 'terms' and len(args) in (2, 4) and args[1] in _TERMS
            and (len(args) == 2 or (args[2] == '--rotation' and args[3] in _TERMS))):
        return terms(args[0], _TERMS[args[1]], _TERMS[args[3]] if len(args) == 4 else None)
    if verb == 'route' and len(args) == 2 and args[0] == 'why':
        return route_why(args[1])
    print(USAGE, file=sys.stderr)
    return 2


def core(*, open_browser=False):
    from ..infra import discovery
    if open_browser:
        state, info = discovery.discover()
        if state == 'running':          # ask the running Core instead of starting one
            code = _launch_code(info)
            if code is None:
                return 2
            import webbrowser
            webbrowser.open('http://127.0.0.1:%d/#launch=%s' % (info['port'], code))
            print('opened Archeus on http://127.0.0.1:%d' % info['port'])
            return 0
    from ..core import runtime
    return runtime.run(port=runtime.DEFAULT_PORT, open_browser=open_browser)


def _get(info, method, path, body=None):
    import urllib.request
    from ..infra import discovery
    token = discovery.read_local_token()
    if token is None:
        return None
    data = json.dumps(body or {}).encode() if method == 'POST' else None
    req = urllib.request.Request('http://127.0.0.1:%d%s' % (info['port'], path), method=method,
                                 data=data,
                                 headers={'Authorization': 'Bearer ' + token,
                                          'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _launch_code(info):
    out = _get(info, 'POST', '/v1/devices/launch/code')
    if out is None:
        print('could not get a launch code from Core on port %d' % info['port'], file=sys.stderr)
        return None
    return out['code']


def terms(harness=None, headless=None, rotation=None):
    """List the provider-terms answers, or give one (ADR-0021). Only this
    command, or the admin route it calls, ever changes one: nothing in Core
    assumes an answer, and `unknown` blocks every real call as `refused` does."""
    from ..infra import discovery
    state, info = discovery.discover()
    if state != 'running':
        print('Core is not running: start it with `archeus core`', file=sys.stderr)
        return 1
    if harness is None:
        out = _get(info, 'GET', '/v1/provider-terms')
        if out is None:
            print('Core did not answer', file=sys.stderr)
            return 2
        for t in out['provider_terms']:
            print('%-14s headless %-9s rotation %s' % (t['id'], t['headless'], t['rotation']))
        return 0
    import os
    body = {'headless': headless, 'idempotency_key': os.urandom(16).hex()}
    if rotation is not None:
        body['rotation'] = rotation
    out = _get(info, 'POST', '/v1/provider-terms/%s' % harness, body)
    if out is None:
        print('Core refused the answer for %s' % harness, file=sys.stderr)
        return 2
    t = out['provider_terms']
    print('%s: headless %s, rotation %s' % (t['id'], t['headless'], t['rotation']))
    return 0


def route_why(ref):
    """The explanation Core generated from a persisted RouteDecision (no model
    call; resource-router §8): *ref* is its id, or the id of what it is about,
    whose latest decision is shown."""
    from urllib.parse import quote
    from ..core.domain import ids
    from ..infra import discovery
    state, info = discovery.discover()
    if state != 'running':
        print('Core is not running: start it with `archeus core`', file=sys.stderr)
        return 1
    if ids.is_id(ref, 'route_decision'):
        d = _get(info, 'GET', '/v1/route-decisions/%s' % quote(ref, safe=''))
    else:
        got = _get(info, 'GET', '/v1/route-decisions?source=%s' % quote(ref, safe=''))
        d = got['route_decisions'][-1] if got and got['route_decisions'] else None
    if d is None:
        print('no route decision for %s' % ref, file=sys.stderr)
        return 2
    print('%s (%s): %s' % (d['id'], d.get('result') or 'selected', d['explanation']))
    return 0


def status():
    from ..infra import discovery
    state, info = discovery.discover()
    if state == 'not_running':
        print('Core: not running')
        return 1
    if state == 'unreadable':
        print('Core: running, discovery file unreadable (%s); nothing was sent to it'
              % discovery.core_json_path())
        return 2
    health = _get(info, 'GET', '/v1/health')
    if health is None:
        print('Core: running (pid %d, port %d), but /v1/health did not answer'
              % (info['pid'], info['port']))
        return 2
    c, e = health['core'], health['engine']
    try:
        up = time.time() - calendar.timegm(time.strptime(c['started_at'], '%Y-%m-%dT%H:%M:%SZ'))
        uptime = '%ds' % max(0, up)
    except (KeyError, ValueError):
        uptime = '?'
    print('Core: running (pid %d, port %d, up %s, version %s)'
          % (c['pid'], info['port'], uptime, c['version']))
    print('schema %s, engine %s, ports %s' % (c['schema'], e['state'], c['ports']))
    if c['ports'] == 'stub':
        print('walking skeleton: fake harness, stub policy — missions here do no real work')
    _ok, warning = discovery.token_protection()
    if warning:
        print('warning: %s' % warning)
    return 3 if e['state'] == 'failed' else 0
