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

from ._api import endpoints

#: Verbs whose behaviour belongs to a later phase: they do nothing, say so,
#: and exit 2, so no script ever sees a verb change from "opened the TUI" to
#: something else.
DEFERRED = {}
VERBS = ('core', 'status', 'terms', 'approve', 'pause', 'route', 'estop', 'pair',
         'sessions', 'resume', 'handoff', 'verify', 'decide', 'automation', 'devices',
         'tui', 'gui', 'executions', 'doctor', 'wait', 'top')

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
       archeus tui [--open KIND/ID] [--once] [--light]
                                the terminal client of a running Core (P17); it never
                                starts Core
       archeus gui              the desktop app: the Archeus window and its tray (Open,
                                Pause all, Emergency stop, Quit); starts Core if it is
                                not running (P19)
       archeus status           is Core running? (exit 0 yes, 1 no, 2 discovery failed,
                                3 its engine failed)
       archeus doctor           read-only health checks: database integrity, consumer
                                lag, stuck executions, the execution hook (P21); exit 0
                                when nothing is found, else the sum of the findings' codes
       archeus status <mission-id>
                                a mission's state, as Core reports it (P19)
       archeus wait <mission-id> [--until STATE[,STATE]] [--timeout SECONDS]
                                block until the mission reaches a state, polling Core every
                                2 s; prints the `archeus status` line. Default --until:
                                COMPLETED, CANCELLED, FAILED, BLOCKED, PAUSED,
                                APPROVAL_REQUIRED; default --timeout 60. Exit 0 reached,
                                1 Core not running or not answering until the timeout,
                                2 usage or unknown mission, 4 timed
                                out, 5 it ended in a state you did not ask for (with
                                the default, FAILED, BLOCKED or CANCELLED). A final state
                                always ends the wait. FAILED is not final: it may replan
       archeus top --once [--by account|mission|pass]
                                the tokens and cost the usage ledger holds, per account
                                (default), mission or learning pass: one table, read once
                                (a figure nobody reported is `-`; `complete` is `no` while
                                any row is a partial figure)
       archeus terms            the provider-terms answers (ADR-0021)
       archeus terms <harness> permit|refuse [--rotation permit|refuse]
                                answer it: may Archeus make automated headless calls on
                                this harness's accounts (and rotate across several)?
       archeus route why <id>   why a resource was chosen: a route decision, or the latest
                                one about a task, mission or other subject (P10)
       archeus approve          the approvals waiting on you: id, kind, what it would do,
                                mission
       archeus approve <approval-id>
                                one approval, with the action hash to echo back when you
                                decide it
       archeus approve <approval-id> allow|deny --hash H [--note N]
                                decide it: the hash must be the one `archeus approve
                                <approval-id>` showed you; Core refuses without it
       archeus pause <mission-id>
                                pause a mission: its executions halt at their next tool call
       archeus pause all --now  the emergency stop (as `archeus estop`)
       archeus estop            stop every execution now; Core stays disarmed until
                                a user device re-arms it; with Core down it kills the
                                recorded processes itself and never starts Core
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
                                and what the mission it asked for then did
       archeus executions opt-ins
                                what executions may load from their settings sources
                                (ADR-0049): every opt-in, in and out
       archeus executions opt-in|opt-out <account|project> <source|plugin|mcp|context|verify> <name> [--digest <sha256>]
                                a project's mcp opt-in pins the sha256 of its .mcp.json:
                                approve a changed file again with its new digest
                                let an account's or a project's executions load a
                                settings source (an account: user; a project: project,
                                local), a plugin or an MCP server again, or stop it;
                                a project's context injection puts its mission's
                                context package in each execution's prompt, and its
                                context review_rules puts REVIEW.md (read at the
                                mission's base) in its reviews (both off unless opted in);
                                a project's verify baseline runs a failed test again
                                at the revision the work started from, one more
                                checkout per verification (off unless opted in)"""
_TERMS = {'permit': 'permitted', 'refuse': 'refused'}


def main(argv):
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, 'reconfigure'):
            s.reconfigure(encoding='utf-8', errors='replace')
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
    if verb == 'tui':
        from .tui.app import main as tui
        return tui(args)
    if verb == 'gui' and not args:
        from .gui import main as gui
        return gui()
    if verb == 'status' and not args:
        return status()
    if verb == 'doctor' and not args:
        from ..core.doctor import doctor
        return doctor()
    if verb == 'status' and len(args) == 1:
        return mission_status(args[0])
    if verb == 'top' and '--once' in args:
        rest = [a for a in args if a != '--once']
        by = _flags(rest)
        if by is not None and set(by) <= {'by'}:
            return top(by.get('by', 'account'))
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
    if verb == 'approve' and not args:
        return approve_list()
    if verb == 'approve' and len(args) == 1:
        return approve_show(args[0])
    if (verb == 'approve' and len(args) in (4, 6) and args[1] in _APPROVE_DECISION
            and args[2] == '--hash' and not args[3].startswith('--')
            and (len(args) == 4 or (args[4] == '--note' and not args[5].startswith('--')))):
        return approve_decide(args[0], args[1], args[3], args[5] if len(args) == 6 else '')
    if verb == 'automation' and args and (args == ['list'] or len(args) == 2):
        return automation(args[0], args[1] if len(args) == 2 else None)
    if verb == 'executions' and (args == ['opt-ins'] or (
            len(args) in (4, 6) and args[0] in _OPT
            and args[2] in ('source', 'plugin', 'mcp', 'context', 'verify')
            and (len(args) == 4 or args[4] == '--digest'))):
        return opt_ins(*args[:4], digest=args[5] if len(args) == 6 else None)
    opts = _flags(args[1:] if verb in ('resume', 'handoff', 'wait') else args)
    if verb == 'wait' and args and opts is not None and set(opts) <= {'until', 'timeout'}:
        return wait(args[0], opts.get('until'), opts.get('timeout', '60'))
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
            url = launch_url(info)
            if url is None:
                return 2
            import webbrowser
            webbrowser.open(url)
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
        body['scopes'] = [s.strip() for s in opts['scopes'].split(',') if s.strip()]
        if not body['scopes']:
            print('--scopes names no scope: leave it out for the default, or name at least '
                  'observe', file=sys.stderr)
            return 2
    out = _get(info, 'POST', endpoints.pair_start(), body)
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
    info = _running()
    if info is None:
        return 1
    if revoke_id is not None:
        out = _get(info, 'POST', endpoints.revoke_device(revoke_id),
                   {'idempotency_key': os.urandom(16).hex()})
        if out is None:
            print('Core refused to revoke %s' % revoke_id, file=sys.stderr)
            return 2
        print('%s: %s' % (revoke_id, out['state']))
        return 0
    out = _get(info, 'GET', endpoints.list_devices())
    if out is None:
        print('Core did not answer', file=sys.stderr)
        return 2
    for d in out['devices']:
        p = d['presence']
        print('%s  %-7s %-6s %-9s %-10s %s%s' % (
            d['id'], d['state'], d['origin'], d['platform'], p['state'], d['name'],
            '  (%s)' % d['host_label'] if d['host_label'] else ''))
    return 0


def _get(info, method, path, body=None, refusal=None, within=None, deadline=None, clock=None):
    """Core's answer, or None after saying on stderr why, in Core's own code and
    detail (p19-design-gate B11): over the transport the TUI uses. With *refusal*
    (a dict) it also holds the code and detail, for a caller that must branch on
    one rather than only repeat it. *within* caps a GET at that many seconds."""
    from ..infra import discovery
    from .tui import client, sync
    clock = clock or time.monotonic
    if method == 'GET' and within is not None and within <= 0:
        return None
    if method == 'GET' and within is not None and deadline is None:
        deadline = clock() + within
    token = discovery.read_local_token()
    if token is None:
        return None
    core = client.Core(info['port'], token)
    try:
        if method == 'GET' and within is None:
            return core.get(path)[0]
        if method == 'GET':
            return core.get(path, min(client.TIMEOUT_S, within), deadline=deadline, clock=clock)[0]
        return core.post(path, body or {})
    except client.CoreError as e:
        if refusal is not None:
            refusal.update(e.refusal())
        print(sync.explain(e.refusal()), file=sys.stderr)
        return None


def _launch_code(info, slot=None):
    # the user at this machine opens the app with its full grant (p16-design-gate D2)
    body = {'scopes': ['observe', 'control', 'approve', 'admin']}
    if slot:
        body['supersede'] = slot
    out = _get(info, 'POST', endpoints.launch_code(), body)
    if out is None:
        print('could not get a launch code from Core on port %d' % info['port'], file=sys.stderr)
        return None
    return out['code']


def launch_url(info, slot=None):
    """The app's address with a fresh launch code in its fragment, which never
    reaches a server log (api-and-realtime §5.1): `core --open`, `gui` and the
    legacy GUI's "Open Archeus V1" all open the app this way. None after
    saying on stderr why. With *slot* (the Qt shell's page, T-096) the code
    takes that slot, so its redeem revokes the slot's previous holder, and
    `memory=1` has the page keep its token in memory only (p20 D1): no page
    credential outlives the shell."""
    code = _launch_code(info, slot)
    return None if code is None else 'http://127.0.0.1:%d/#launch=%s%s' % (
        info['port'], code, '&memory=1' if slot else '')


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
        out = _get(info, 'GET', endpoints.list_provider_terms())
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
    out = _get(info, 'POST', endpoints.decide_provider_terms(harness), body)
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
    from ..core.domain import ids
    from ..infra import discovery
    state, info = discovery.discover()
    if state != 'running':
        print('Core is not running: start it with `archeus core`', file=sys.stderr)
        return 1
    if ids.is_id(ref, 'route_decision'):
        d = _get(info, 'GET', endpoints.get_route_decision(ref))
    else:
        got = _get(info, 'GET', endpoints.list_route_decisions(source=ref))
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
    """The emergency stop (execution-architecture §10). Core running: Core's
    own e-stop (path 1). Core down or not answering: the STOP sentinel and the
    registry kill, here, without starting Core (path 2, P20 slice A). A Core
    that answers and refuses is not bypassed."""
    import os
    from ..infra import discovery
    from ..node.local import LocalNode
    from .tui import client, sync
    info = _core_or_say()
    token = discovery.read_local_token() if info is not None else None
    if token is not None:
        try:
            out = client.Core(info['port'], token).post(
                endpoints.estop(), {'idempotency_key': os.urandom(16).hex()})
            stopped = len(out['stopped'])
        except client.CoreError as e:
            if e.code != 'network':
                print('Core did not accept the e-stop: %s' % sync.explain(e.refusal()),
                      file=sys.stderr)
                return 2
        except Exception:       # an answer that is not Core's is no stop: do it here
            pass
        else:
            print('emergency stop: %d execution(s) stopped; Core is disarmed until re-armed'
                  % stopped)
            return 0
    try:
        killed, _ = LocalNode.estop_without_core()
    except OSError as e:
        print('emergency stop failed: the STOP file could not be written (%s)' % e,
              file=sys.stderr)
        return 2
    print('emergency stop without Core: %d process(es) killed; Core starts disarmed and runs '
          'nothing until re-armed' % len(killed))
    return 0


def pause(mission_id):
    import os
    info = _core_or_say()
    if info is None:
        print('Core is not running: start it with `archeus core`', file=sys.stderr)
        return 1
    out = _get(info, 'POST', endpoints.pause_mission(mission_id),
               {'idempotency_key': os.urandom(16).hex()})
    if out is None:
        print('Core refused to pause %s' % mission_id, file=sys.stderr)
        return 2
    print('%s: %s (its executions halt at their next tool call)' % (mission_id, out['state']))
    return 0


def mission_status(mission_id):
    """A mission's state as Core reports it: the CLI is one more client of the
    one model (G3; p19-design-gate B11)."""
    info = _core_or_say()
    if info is None:
        print('Core is not running: start it with `archeus core`', file=sys.stderr)
        return 1
    m = _get(info, 'GET', endpoints.get_mission(mission_id))
    if m is None:
        return 2
    _say_mission(m)
    return 0


def _say_mission(m):
    from .tui.view import clean
    print('%s: %s (%s)' % (clean(m['id']), clean(m['state']), clean(m['title'])))


def _is_mission(m):
    return (isinstance(m, dict) and isinstance(m.get('id'), str)
            and isinstance(m.get('state'), str) and 'title' in m)


#: States a mission waits in for a person, and FAILED, which is not final (it may replan)
_WAIT_DEFAULT = ('COMPLETED', 'CANCELLED', 'FAILED', 'BLOCKED', 'PAUSED', 'APPROVAL_REQUIRED')
_WAIT_BAD = ('FAILED', 'BLOCKED', 'CANCELLED')


def wait(mission_id, until=None, timeout='60', *, sleep=time.sleep, clock=time.monotonic):
    """Poll `GET /v1/missions/{id}` until the mission is in a state of *until*. A final
    state ends the wait whatever was asked, since the mission can never leave it. Exit 0
    when the state was asked for, 5 when it was not or is one of the default bad ones."""
    import http.client
    from ..core.domain import states
    from .tui.view import clean
    known = states.states('mission')
    want = _WAIT_DEFAULT if until is None else tuple(x.strip().upper() for x in until.split(','))
    try:
        seconds = float(timeout)
    except ValueError:
        seconds = 0
    if not seconds > 0 or not all(x in known for x in want):
        print('--until names mission states (%s) and --timeout is seconds > 0' % ', '.join(known),
              file=sys.stderr)
        return 2
    deadline = clock() + seconds
    info = _running()
    if info is None:
        return 1
    stop = set(want) | states.terminal('mission')
    m = None
    try:
        while True:
            remaining = deadline - clock()
            if remaining > 0:
                refusal = {}
                try:
                    m = _get(info, 'GET', endpoints.get_mission(mission_id), refusal=refusal,
                             within=remaining, deadline=deadline, clock=clock)
                    if m is not None and not _is_mission(m):
                        raise ValueError('not a mission')
                except (http.client.HTTPException, ValueError, OSError) as e:
                    print('Core gave no readable answer (%s)' % type(e).__name__, file=sys.stderr)
                    m = None
                if m is None and refusal.get('code') == 'not_found':
                    return 2
            if m is not None and m['state'] in stop and clock() <= deadline:
                _say_mission(m)
                bad = m['state'] not in want or (until is None and m['state'] in _WAIT_BAD)
                return 5 if bad else 0
            if clock() >= deadline:
                if m is None:
                    print('Core did not answer for %s before the timeout' % mission_id,
                          file=sys.stderr)
                    return 1
                print('timed out after %gs: %s is still %s' % (
                    seconds, clean(m['id']), clean(m['state'])), file=sys.stderr)
                return 4
            sleep(min(2, max(0, deadline - clock())))
    except KeyboardInterrupt:
        return 130


def top(by):
    """The usage ledger as one table, from Core's `/v1/usage`: read only, and a
    figure nobody reported is `-`, never 0."""
    info = _running()
    if info is None:
        return 1
    out = _get(info, 'GET', endpoints.usage_by(by=by))
    if out is None:
        return 2
    from .tui.view import clean
    cols = ('calls', 'tokens_in', 'tokens_out', 'cache_read', 'cache_write', 'cost_usd')
    print('%-40s %6s %11s %11s %11s %11s %9s  complete' % ((by,) + cols))
    for r in out['rows']:
        fig = ['-' if r[c] is None else '%.4f' % r[c] if c == 'cost_usd' else clean(r[c])
               for c in cols]
        print('%-40s %6s %11s %11s %11s %11s %9s  %s' % (
            clean(r[by]) or '(none)', *fig, 'yes' if r['complete'] else 'no'))
    if not out['rows']:
        print('no usage recorded')
    return 0


def verify(mission_id):
    """Every verification of the mission and its reviews (P13 §21)."""
    info = _running()
    if info is None:
        return 1
    m = mission_id
    vs = _get(info, 'GET', endpoints.list_verifications(m))
    rs = _get(info, 'GET', endpoints.list_reviews(m))
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
    info = _running()
    if info is None:
        return 1
    key = {'idempotency_key': os.urandom(16).hex(), 'note': note or None}
    t = target
    if target.startswith('ver_') and verdict in ('accept', 'reject'):
        out = _get(info, 'POST', endpoints.decide_verification(t), dict(key, decision=verdict))
    elif target.startswith('msn_') and verdict in _REVIEW_VERDICTS:
        out = _get(info, 'POST', endpoints.review_mission(t),
                   dict(key, verdict=_REVIEW_VERDICTS[verdict]))
    else:
        print(USAGE, file=sys.stderr)
        return 2
    if out is None:
        print('Core refused: %s is not waiting for that decision' % target, file=sys.stderr)
        return 2
    print('%s: %s' % (target, out.get('state') or out.get('verdict')))
    return 0


_APPROVE_DECISION = {'allow': 'approve', 'deny': 'reject'}


def _approval_what(a):
    p = a.get('presented') or {}
    what = ', '.join(' '.join(x for x in (w.get('class'), w.get('target')) if x)
                     for w in p.get('what') or [])
    return what or p.get('why') or ''


def approve_list():
    info = _running()
    if info is None:
        return 1
    out = _get(info, 'GET', endpoints.list_approvals(state='PENDING'))
    if out is None:
        print('Core did not answer', file=sys.stderr)
        return 2
    for a in out['approvals']:
        print('%s  %-6s  %s  %s' % (a['id'], a['kind'], a['mission_id'], _approval_what(a)))
    if not out['approvals']:
        print('nothing waits on you')
    return 0


def approve_show(approval_id):
    info = _running()
    if info is None:
        return 1
    a = _get(info, 'GET', endpoints.get_approval(approval_id))
    if a is None:
        return 2
    print('%s: %s (%s): %s' % (a['id'], a['kind'], a['state'], _approval_what(a)))
    print('mission: %s' % a['mission_id'])
    print('action hash: %s' % a['action_hash'])
    return 0


def approve_decide(approval_id, verdict, action_hash, note=''):
    """The decision carries the hash the human was shown (X02): the CLI never
    reads it from Core and posts it in one invocation, so deciding something
    that was not displayed is impossible. A step-up answer is Core's: this CLI
    does not carry PINs, the app does."""
    import os
    info = _running()
    if info is None:
        return 1
    body = {'decision': _APPROVE_DECISION[verdict], 'action_hash': action_hash,
            'note': note or None, 'idempotency_key': os.urandom(16).hex()}
    refusal = {}
    out = _get(info, 'POST', endpoints.decide_approval(approval_id), body, refusal=refusal)
    if out is None:
        reason = str((refusal.get('detail') or {}).get('reason') or '')
        if refusal.get('code') == 'guard_failed' and 'step-up' in reason:
            print('%s needs the Archeus app: it asks for its step-up PIN there'
                  % approval_id, file=sys.stderr)
        return 1
    print('%s: %s' % (approval_id, out.get('state')))
    return 0


_AUTOMATION_ACTIONS = ('enable', 'disable', 'archive')


def automation(what, arg):
    """The automations (P14 §17): read, write, switch, explain."""
    import os
    if what not in ('list', 'show', 'simulate', 'create', 'why') + _AUTOMATION_ACTIONS:
        print(USAGE, file=sys.stderr)
        return 2
    body = None
    if what == 'create':
        try:
            with open(arg, encoding='utf-8') as f:
                body = json.load(f)
        except (OSError, ValueError, RecursionError) as e:
            print('cannot read %s: %s' % (arg, e), file=sys.stderr)
            return 2
        if not isinstance(body, dict):
            print('%s must hold one JSON object' % arg, file=sys.stderr)
            return 2
    info = _running()
    if info is None:
        return 1
    key = {'idempotency_key': os.urandom(16).hex()}
    a = arg or ''
    if what == 'list':
        out = _get(info, 'GET', endpoints.list_automations())
    elif what == 'show':
        out = _get(info, 'GET', endpoints.get_automation(a))
    elif what == 'simulate':
        out = _get(info, 'GET', endpoints.simulate_automation(a))
    elif what == 'why':
        out = _get(info, 'GET', endpoints.get_automation_run(a))
    elif what == 'create':
        out = _get(info, 'POST', endpoints.create_automation(), dict(body, **key))
    else:
        out = _get(info, 'POST', endpoints.set_automation_state(a), dict(key, action=what))
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


_OPT = {'opt-in': True, 'opt-out': False}


def opt_ins(what, owner=None, kind=None, name=None, digest=None):
    """P20 D6 (ADR-0049): list the opt-ins, or opt one in or out. Core decides
    and records; this sends the command with the local token."""
    import os
    info = _running()
    if info is None:
        return 1
    if what == 'opt-ins':
        out = _get(info, 'GET', endpoints.list_opt_ins())
        if out is None:
            return 2
        for x in out['opt_ins']:
            print('%s  %-7s %-26s %-6s %-3s %s  (version %d)' % (
                x['id'], x['owner'], x['owner_id'], x['kind'],
                'in' if x['opted_in'] else 'out', x['name'], x['version']))
        if not out['opt_ins']:
            print('no opt-ins: every execution excludes its settings sources\' hooks, '
                  'plugins, skills and MCP servers')
        return 0
    out = _get(info, 'POST', endpoints.set_opt_in(), {
        'owner_id': owner, 'kind': kind, 'name': name, 'opted_in': _OPT[what],
        **({'digest': digest} if digest else {}), 'idempotency_key': os.urandom(16).hex()})
    if out is None:
        return 2
    x = out['opt_in']
    if not out['changed']:
        print('%s %s %s: no change' % (owner, kind, name))
    else:
        print('%s %s %s: opted %s (version %d)' % (owner, kind, name,
                                                   'in' if x['opted_in'] else 'out',
                                                   x['version']))
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
    info = _running()
    if info is None:
        return 1
    out = _get(info, 'GET', endpoints.list_sessions(**opts))
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
    info = _running()
    if info is None:
        return 1
    body = dict(opts, request_id=os.urandom(12).hex(), idempotency_key=os.urandom(16).hex())
    out = _get(info, 'POST', endpoints.resume_session(session_id), body)
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
    info = _running()
    if info is None:
        return 1
    body = {'request_id': os.urandom(12).hex(), 'idempotency_key': os.urandom(16).hex(),
            'harness_id': opts['to']}
    body.update({k: opts[k] for k in ('account', 'model', 'effort') if k in opts})
    if 'account' in body:
        body['account_id'] = body.pop('account')
    out = _get(info, 'POST', endpoints.handoff_session(session_id), body)
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
    health = _get(info, 'GET', endpoints.health())
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
    from .tui.view import clean
    print('Core: running (pid %d, port %d, up %s, version %s)'
          % (c['pid'], info['port'], uptime, clean(c['version'])))
    print('schema %s, engine %s, ports %s' % (clean(c['schema']), clean(e['state']),
                                               clean(c['ports'])))
    if c['ports'] == 'stub':
        print('walking skeleton: fake harness, stub policy — missions here do no real work')
    _ok, warning = discovery.token_protection()
    if warning:
        print('warning: %s' % warning)
    return 3 if e['state'] == 'failed' else 0
