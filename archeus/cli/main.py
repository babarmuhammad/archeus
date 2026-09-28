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
DEFERRED = {'approve': 'P9'}
VERBS = ('core', 'status', 'terms', 'approve', 'pause', 'route', 'estop', 'pair',
         'sessions', 'resume', 'handoff', 'verify', 'decide', 'automation', 'devices')

USAGE = """usage: archeus core [--open] [--remote-host H]...
                                run Archeus Core in the foreground (Ctrl+C stops it);
                                --remote-host accepts requests for H, a tunnel's https
                                name (Tailscale Serve, a reverse proxy) — tokens still
                                required
       archeus pair [--name N] [--host-label H] [--scopes observe,control,approve]
                                pair a phone or another browser: a one-time code for
                                120 s, and the link to open on it (P15)
       archeus devices          the clients paired or signed in, and which are connected
       archeus devices revoke <id>
                                revoke one: its token stops working, its streams close
       archeus status           is Core running? (exit 0 yes, 1 no, 2 discovery failed,
                                3 its engine failed)
       archeus terms            the provider-terms answers (ADR-0021)
       archeus terms <harness> permit|refuse [--rotation permit|refuse]
                                answer it: may Archeus make automated headless calls on
                                this harness's accounts (and rotate across several)?
       archeus route why <id>   why a resource was chosen: a route decision, or the latest
                                one about a task, mission or other subject (P10)
       archeus pause <mission-id>
                                pause a mission: its executions halt at their next tool call
       archeus pause all --now  the emergency stop (as `archeus estop`)
       archeus estop            stop every execution now; Core stays disarmed until
                                a user device re-arms it (P11; with Core down: P20)
       archeus sessions [--project P] [--mission M]
                                the sessions Core knows, newest activity first (P12)
       archeus resume <session> [--model M] [--effort E]
                                reopen a session on its own harness, with what changed
                                since it was last used
       archeus handoff <session> --to <harness> [--account A] [--model M] [--effort E]
                                continue a session in a new one on another harness or
                                account, from what Archeus hands over
       archeus verify <mission> how a mission's work was verified and reviewed: every
                                check, its evidence, and what waits on you (P13)
       archeus decide <verification> accept|reject [--note N]
                                decide a verification that waits on you
       archeus decide <mission> accept|changes|reject [--note N]
                                review a mission's result yourself (your review is the
                                latest, so it overrides the model's)
       archeus automation list  the automations and any quarantined event (P14)
       archeus automation show|simulate <id>
                                one automation and its latest runs; or which events of
                                the last 30 days it would have fired on
       archeus automation create <file.json>
                                write one ({name, trigger, template, project_id?}); it
                                starts disabled
       archeus automation enable|disable|archive <id>
       archeus automation why <run>
                                why an automated action happened: the event, the rule,
                                and what the mission it asked for then did"""
_TERMS = {'permit': 'permitted', 'refuse': 'refused'}


def main(argv):
    verb, args = (argv[0] if argv else ''), list(argv[1:])
    if verb in DEFERRED:
        print('archeus %s is not available yet (arrives with %s); nothing was done'
              % (verb, DEFERRED[verb]), file=sys.stderr)
        return 2
    if verb == 'core' and _core_args(args) is not None:
        return core(open_browser='--open' in args, remote_hosts=_core_args(args))
    pair_opts = _flags(args) if verb == 'pair' else None
    if verb == 'pair' and pair_opts is not None and set(pair_opts) <= {
            'name', 'host-label', 'scopes'}:
        return pair(pair_opts)
    if verb == 'devices' and (not args or (len(args) == 2 and args[0] == 'revoke')):
        return devices(args[1] if args else None)
    if verb == 'status' and not args:
        return status()
    if verb == 'terms' and not args:
        return terms()
    if (verb == 'terms' and len(args) in (2, 4) and args[1] in _TERMS
            and (len(args) == 2 or (args[2] == '--rotation' and args[3] in _TERMS))):
        return terms(args[0], _TERMS[args[1]], _TERMS[args[3]] if len(args) == 4 else None)
    if verb == 'route' and len(args) == 2 and args[0] == 'why':
        return route_why(args[1])
    if (verb == 'estop' and not args) or (verb == 'pause' and args == ['all', '--now']):
        return estop()
    if verb == 'pause' and len(args) == 1 and args[0] != 'all':
        return pause(args[0])
    if verb == 'verify' and len(args) == 1:
        return verify(args[0])
    if verb == 'decide' and len(args) in (2, 4) and (len(args) == 2 or args[2] == '--note'):
        return decide(args[0], args[1], args[3] if len(args) == 4 else '')
    if verb == 'automation' and args and (args == ['list'] or len(args) == 2):
        return automation(args[0], args[1] if len(args) == 2 else None)
    opts = _flags(args[1:] if verb in ('resume', 'handoff') else args)
    if verb == 'sessions' and opts is not None and set(opts) <= {'project', 'mission'}:
        return sessions(opts)
    if verb == 'resume' and args and opts is not None and set(opts) <= {'model', 'effort'}:
        return resume(args[0], opts)
    if (verb == 'handoff' and args and opts is not None and 'to' in opts
            and set(opts) <= {'to', 'account', 'model', 'effort'}):
        return handoff(args[0], opts)
    print(USAGE, file=sys.stderr)
    return 2


def _core_args(args):
    """The `--remote-host` values of `archeus core [--open] [--remote-host H]...`,
    or None when the arguments are not that."""
    hosts, rest = [], list(args)
    while rest:
        a = rest.pop(0)
        if a == '--remote-host' and rest and not rest[0].startswith('--'):
            hosts.append(rest.pop(0))
        elif a != '--open':
            return None
    return hosts


def core(*, open_browser=False, remote_hosts=()):
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
    from ..api import auth
    try:
        hosts = [auth.remote_host(h) for h in remote_hosts]
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    return runtime.run(port=runtime.DEFAULT_PORT, open_browser=open_browser, remote_hosts=hosts)


def pair(opts):
    """Start a pairing (p15-design-gate §6): the code works once, for 120 s, on
    the scopes chosen here. The link carries it in its fragment, which never
    reaches a server log."""
    info = _running()
    if info is None:
        return 1
    body = {'name': opts.get('name'), 'host_label': opts.get('host-label')}
    if 'scopes' in opts:
        body['scopes'] = [s for s in opts['scopes'].split(',') if s]
    out = _get(info, 'POST', '/v1/devices/pair/start', body)
    if out is None:
        print('Core refused to start a pairing (the scopes must include observe)',
              file=sys.stderr)
        return 2
    print('pairing code (valid %ds, once): %s' % (out['expires_in'], out['code']))
    print('scopes: %s' % ', '.join(out['scopes']))
    if out['url']:
        print('open on the new device: %s' % out['url'])
    else:
        print('no remote host is set: start Core with `archeus core --remote-host <name>` '
              'to reach it from another device')
    return 0


def devices(revoke_id=None):
    import os
    from urllib.parse import quote
    info = _running()
    if info is None:
        return 1
    if revoke_id is not None:
        out = _get(info, 'POST', '/v1/devices/%s/revoke' % quote(revoke_id, safe=''),
                   {'idempotency_key': os.urandom(16).hex()})
        if out is None:
            print('Core refused to revoke %s' % revoke_id, file=sys.stderr)
            return 2
        print('%s: %s' % (revoke_id, out['state']))
        return 0
    out = _get(info, 'GET', '/v1/devices')
    if out is None:
        print('Core did not answer', file=sys.stderr)
        return 2
    for d in out['devices']:
        p = d['presence']
        print('%s  %-7s %-6s %-9s %-10s %s%s' % (
            d['id'], d['state'], d['origin'], d['platform'], p['state'], d['name'],
            '  (%s)' % d['host_label'] if d['host_label'] else ''))
    return 0


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


def _core_or_say():
    from ..infra import discovery
    state, info = discovery.discover()
    if state != 'running':
        return None
    return info


def estop():
    """The e-stop with Core running (execution-architecture §10 path 1). With
    Core down the registry kill is P20's; nothing is attempted."""
    import os
    info = _core_or_say()
    if info is None:
        print('Core is not running: the e-stop without Core arrives with P20; start Core '
              'with `archeus core` or stop the processes yourself', file=sys.stderr)
        return 2
    out = _get(info, 'POST', '/v1/estop', {'idempotency_key': os.urandom(16).hex()})
    if out is None:
        print('Core did not accept the e-stop', file=sys.stderr)
        return 2
    print('emergency stop: %d execution(s) stopped; Core is disarmed until re-armed'
          % len(out['stopped']))
    return 0


def pause(mission_id):
    import os
    from urllib.parse import quote
    info = _core_or_say()
    if info is None:
        print('Core is not running: start it with `archeus core`', file=sys.stderr)
        return 1
    out = _get(info, 'POST', '/v1/missions/%s/pause' % quote(mission_id, safe=''),
               {'idempotency_key': os.urandom(16).hex()})
    if out is None:
        print('Core refused to pause %s' % mission_id, file=sys.stderr)
        return 2
    print('%s: %s (its executions halt at their next tool call)' % (mission_id, out['state']))
    return 0


def verify(mission_id):
    """Every verification of the mission and its reviews (P13 §21)."""
    from urllib.parse import quote
    info = _running()
    if info is None:
        return 1
    m = quote(mission_id, safe='')
    vs = _get(info, 'GET', '/v1/missions/%s/verifications' % m)
    rs = _get(info, 'GET', '/v1/missions/%s/reviews' % m)
    if vs is None or rs is None:
        print('Core does not know mission %s' % mission_id, file=sys.stderr)
        return 2
    for v in vs['verifications']:
        s = v['subject']
        what = ('criterion %d' % v['criterion'] if s['kind'] == 'mission'
                else 'task %s' % s['id'])
        print('%s  %-14s %-13s %s at %s%s' % (
            v['id'], v['state'], v['verifier'], what, (v.get('revision') or '-')[:12],
            '  (waits on you)' if v['state'] == 'AWAITING_HUMAN' else ''))
        for c in v['checks']:
            print('    %-5s %s%s' % (c['result'], c['name'],
                                     ' — %s' % c['detail'] if c.get('detail') else ''))
    for r in rs['reviews']:
        print('%s  %-17s review by %s%s: %s' % (
            r['id'], r['state'], r['reviewer'], '' if r['independent'] else ' (not independent)',
            r.get('summary') or r.get('verdict') or ''))
    if not vs['verifications'] and not rs['reviews']:
        print('nothing verified yet')
    return 0


_REVIEW_VERDICTS = {'accept': 'accept', 'changes': 'changes_requested', 'reject': 'reject'}


def decide(target, verdict, note=''):
    """A verification that waits on you (ver_…), or your own review of a
    mission in review (msn_…)."""
    import os
    from urllib.parse import quote
    info = _running()
    if info is None:
        return 1
    key = {'idempotency_key': os.urandom(16).hex(), 'note': note or None}
    t = quote(target, safe='')
    if target.startswith('ver_') and verdict in ('accept', 'reject'):
        out = _get(info, 'POST', '/v1/verifications/%s/decide' % t, dict(key, decision=verdict))
    elif target.startswith('msn_') and verdict in _REVIEW_VERDICTS:
        out = _get(info, 'POST', '/v1/missions/%s/review' % t,
                   dict(key, verdict=_REVIEW_VERDICTS[verdict]))
    else:
        print(USAGE, file=sys.stderr)
        return 2
    if out is None:
        print('Core refused: %s is not waiting for that decision' % target, file=sys.stderr)
        return 2
    print('%s: %s' % (target, out.get('state') or out.get('verdict')))
    return 0


_AUTOMATION_ACTIONS = ('enable', 'disable', 'archive')


def automation(what, arg):
    """The automations (P14 §17): read, write, switch, explain."""
    import os
    from urllib.parse import quote
    if what not in ('list', 'show', 'simulate', 'create', 'why') + _AUTOMATION_ACTIONS:
        print(USAGE, file=sys.stderr)
        return 2
    body = None
    if what == 'create':
        try:
            with open(arg, encoding='utf-8') as f:
                body = json.load(f)
        except (OSError, ValueError) as e:
            print('cannot read %s: %s' % (arg, e), file=sys.stderr)
            return 2
    info = _running()
    if info is None:
        return 1
    key = {'idempotency_key': os.urandom(16).hex()}
    a = quote(arg or '', safe='')
    if what == 'list':
        out = _get(info, 'GET', '/v1/automations')
    elif what == 'show':
        out = _get(info, 'GET', '/v1/automations/%s' % a)
    elif what == 'simulate':
        out = _get(info, 'GET', '/v1/automations/%s/simulate' % a)
    elif what == 'why':
        out = _get(info, 'GET', '/v1/automation-runs/%s' % a)
    elif what == 'create':
        out = _get(info, 'POST', '/v1/automations', dict(body, **key))
    else:
        out = _get(info, 'POST', '/v1/automations/%s/state' % a, dict(key, action=what))
    if out is None:
        print('Core refused or does not know %s' % (arg or 'that'), file=sys.stderr)
        return 2
    if what == 'list':
        for x in out['automations']:
            print('%s  %-10s %-28s %s' % (x['id'], x['state'], x['trigger']['type'], x['name']))
        for q in out['quarantined']:
            print('quarantined event %d: %s' % (q['seq'], q['error']))
        if not out['automations']:
            print('no automations')
    elif what in ('show', 'why', 'simulate'):
        print(json.dumps(out, indent=2))
    else:
        print('%s: %s' % (out['id'], out['state']))
    return 0


def _flags(args):
    """`--name value` pairs, or None when they are not that."""
    if len(args) % 2:
        return None
    out = {}
    for k, v in zip(args[::2], args[1::2]):
        if not k.startswith('--') or v.startswith('--'):
            return None
        out[k[2:]] = v
    return out


def _running():
    info = _core_or_say()
    if info is None:
        print('Core is not running: start it with `archeus core`', file=sys.stderr)
    return info


def sessions(opts):
    from urllib.parse import urlencode
    info = _running()
    if info is None:
        return 1
    q = urlencode({k: v for k, v in opts.items()})
    out = _get(info, 'GET', '/v1/sessions' + ('?' + q if q else ''))
    if out is None:
        print('Core did not answer', file=sys.stderr)
        return 2
    for s in out['sessions']:
        print('%s  %-7s %-20s %-12s %s%s' % (
            s['id'], s['state'], s['harness_id'], s.get('model') or '-', s['cwd'],
            '  (from %s)' % s['handoff_from_session_id']
            if s.get('handoff_from_session_id') else ''))
    if not out['sessions']:
        print('no sessions')
    return 0


def resume(session_id, opts):
    import os
    from urllib.parse import quote
    info = _running()
    if info is None:
        return 1
    body = dict(opts, request_id=os.urandom(12).hex(), idempotency_key=os.urandom(16).hex())
    out = _get(info, 'POST', '/v1/sessions/%s/resume' % quote(session_id, safe=''), body)
    if out is None:
        print('Core refused to resume %s' % session_id, file=sys.stderr)
        return 2
    b = out.get('brief') or {}
    n = (b.get('changes') or {}).get('count', 0)
    print('%s: resumed on %s%s; %d change(s) since it was last used'
          % (session_id, out['harness_id'], ' (%s)' % out['model'] if out.get('model')
             else '', n))
    launch = out.get('launch') or {}
    if launch.get('error'):
        print('the terminal did not open: %s' % launch['error'], file=sys.stderr)
        return 2
    return 0


def handoff(session_id, opts):
    import os
    from urllib.parse import quote
    info = _running()
    if info is None:
        return 1
    body = {'request_id': os.urandom(12).hex(), 'idempotency_key': os.urandom(16).hex(),
            'harness_id': opts['to']}
    body.update({k: opts[k] for k in ('account', 'model', 'effort') if k in opts})
    if 'account' in body:
        body['account_id'] = body.pop('account')
    out = _get(info, 'POST', '/v1/sessions/%s/handoff' % quote(session_id, safe=''), body)
    if out is None:
        print('Core refused to hand %s off' % session_id, file=sys.stderr)
        return 2
    print('%s -> %s on %s' % (session_id, out['id'], out['harness_id']))
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
