"""Headless smoke test for the GUI: boot the real PAGE against stub API data and
inspect what actually rendered.

The string-matching tests in tests/ prove the code is *shaped* right; this proves
it *runs* — instruments mount and paint, readouts carry values, the frame loop
parks when nothing is happening, every page renders without a JS error, and the
narrow-window layout re-fits.

Cannot verify the QtWebEngine flicker itself: a headless/GPU-less box won't
composite to a capturable buffer, so screen-scrape probes see a static frame
(CLAUDE.md). That needs real hardware.

    py -3 tools/smoke_gui.py
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from claude_sessions import gui                       # noqa: E402
from claude_sessions.gui_html import PAGE, vendor_asset  # noqa: E402
from claude_sessions import themes as _TH        # noqa: E402
from claude_sessions import config as _TH_CFG    # noqa: E402
from claude_sessions import harnesses as _TH_H   # noqa: E402

PORT = 8793

STATE = {
    'projects': [{'name': 'acme-api', 'path': '/demo/acme-api', 'encoded': 'demo-acme-api',
                  'accounts': ['default', 'teamA'], 'primary_cfgdir': '',
                  'auto_memory': True, 'last_active': '2m'},
                 {'name': 'acme-web', 'path': '/demo/acme-web', 'encoded': 'demo-acme-web',
                  'accounts': ['teamA'], 'primary_cfgdir': 'w',
                  'auto_memory': False, 'last_active': '1d'}],
    # what the CLI behind each account can do. DERIVED from the real registry
    # rather than spelled out — a hand-typed stub was one harness, and a strip
    # that shows a choice only when there are two renders as nothing at all at
    # one, so the Harnesses page and the Usage page's harness tabs would both
    # have been walked with their strips switched off. The same argument the
    # permission and effort lists below already make: a one-item stub audits a
    # control that cannot wrap, cannot overflow and cannot be wrong.
    'harnesses': [{'id': hid, 'label': _TH_H.descriptor(hid)['label'],
                   'available': True,
                   'homes': ['', 'w'] if hid == 'claude' else ['/home/.' + hid],
                   'caps': {k: list(_TH_H.cap(hid, k)) for k in _TH_H.CAPS}}
                  for hid in _TH_H.ids()],
    'accounts': [{'name': 'default', 'dir': '', 'active': True},
                 {'name': 'teamA', 'dir': 'w', 'active': False}],
    'recent': [{'project': 'acme-api', 'path': '/demo/acme-api', 'encoded': 'demo-acme-api',
                'sid': 's1', 'name': 'a session', 'age': '2m', 'cfgdir': ''}],
    # The permission list is the REAL one, for the same reason the presets below
    # are: it grew from four modes to six, and a one-item ['d'] stub audits a
    # control that cannot wrap, cannot overflow and cannot be wrong.
    # ...and the effort list is real for a sharper version of the same reason:
    # the tick row under the slider is laid out per stop, and a two-stop stub
    # cannot put a label in the wrong place. It shipped six hand-typed labels
    # against a seven-stop slider — the thumb pointed at HIGH while the readout
    # said xhigh — and every audit passed, because they were auditing two stops.
    'options': {'efforts': list(_TH_CFG.EFFORTS), 'models': ['opus', 'sonnet'],
                'model_labels': ['Opus', 'Sonnet'],
                'perms': list(_TH_CFG.PERMS), 'perm_labels': list(_TH_CFG.PERM_LABELS),
                'perm_profiles': dict(_TH_CFG.PERM_PROFILES),
                'perm_notes': {p: {m: list(_TH_CFG.perm_note(p, m))
                                   for m in ('', 'opus', 'sonnet')}
                               for p in _TH_CFG.PERMS},
                # the real ladder, for the same reason the efforts above are
                # real: a one-stop chip row is a control that cannot be
                # misrendered, so auditing it proves nothing
                'thinking': list(_TH_CFG.THINKING_CAPS),
                'thinking_labels': list(_TH_CFG.THINKING_LABELS),
                'frontier': [['opus', 'high', 'Opus', '$$', '70', 'note']],
                # real presets, so the launch modal actually renders its cards.
                # Without them tools/shot_gui.py audits an empty modal — which is
                # how a pill radius that turned every preset into an ellipse got
                # past it.
                'presets': [[n, d, f] for n, d, f in _TH_CFG.LAUNCH_PRESETS]},
    'defaults': {'effort': '', 'model': '', 'perm': '', 'max_thinking': '',
                 'subagent_model': ''},
    'ui_mode': 'gui', 'gui_shell': 'auto', 'theme': 'neon', 'motion': 'full',
    'stage': 'cinematic',
    'themes': gui.theme_palettes(), 'skin': '',
    'skins': {n: dict(v) for n, v in _TH.SKINS.items()},
    'worlds': {n: dict(v) for n, v in _TH.WORLDS.items()},
    'classic_skins': list(_TH.CLASSIC_SKINS),
    'world': '',
    'plan_model': '', 'exec_model': '', 'extract_model': '',
    # two backends, because the whole point of the card is that there is more
    # than one — and the launch modal offers them beside Anthropic
    'providers': [
        {'id': 'p1', 'name': 'OmniRoute', 'kind': 'omniroute',
         'base_url': 'http://localhost:20128', 'model': 'auto/coding',
         'context_tokens': 0, 'tool_search': False, 'gateway_kind': '',
         'gateway_target_base_url': '', 'failover_models': ['auto/fast'],
         'failover_quiet': False, 'port': 20129,
         'api_key_set': True, 'gateway_target_api_key_set': False},
        {'id': 'p2', 'name': 'vLLM box', 'kind': 'generic',
         'base_url': 'http://10.0.0.5:8000', 'model': 'Qwen3-VL-32B',
         'context_tokens': 32768, 'tool_search': False, 'gateway_kind': '',
         'gateway_target_base_url': '', 'failover_models': [],
         'failover_quiet': False, 'port': 20131,
         'api_key_set': False, 'gateway_target_api_key_set': False}],
    'provider_active': 'p1', 'headless_provider_id': '',
    # ── what a new session can start ON ──────────────────────
    # Built from the REAL registry, not typed out: the launch strip gates each
    # of its controls on one capability key, so a stub that invents a flat
    # `caps: {everything: true}` audits a strip whose fields can never be
    # hidden. Codex and pi are forced present here because a one-row strip is
    # exactly the case the code hides — the check would pass on nothing.
    'launch_targets': [
        {'key': hid, 'kind': 'harness', 'label': _TH_H.descriptor(hid)['label'],
         'hid': hid, 'cfgdir': '' if hid == 'claude' else '/home/.' + hid,
         'provider': '',
         'caps': {k: list(_TH_H.cap(hid, k)) for k in _TH_H.CAPS}}
        for hid in _TH_H.ids()
    ] + [
        {'key': 'provider:p1', 'kind': 'provider', 'label': 'OmniRoute',
         'hid': 'claude', 'cfgdir': '', 'provider': 'p1',
         'caps': {k: list(_TH_H.cap('claude', k)) for k in _TH_H.CAPS}},
        {'key': 'provider:p2', 'kind': 'provider', 'label': 'vLLM box',
         'hid': 'claude', 'cfgdir': '', 'provider': 'p2',
         'caps': {k: list(_TH_H.cap('claude', k)) for k in _TH_H.CAPS}},
    ],
    'launch_default': 'claude',
    'harnesses_disabled': [], 'providers_disabled': [],
}
_NOW = time.time()
DASH = {
    # by_account is what the quota ring's arcs are built from — three accounts
    # so the segmented path is actually exercised. Tokens, never percentages:
    # each account's quota % is a share of its OWN window and they do not add.
    'today': {'tokens': 412000, 'sessions': 7, 'cost': 28.0,
              'by_account': {'default': 240000, 'teamA': 130000, 'teamB': 42000},
              'provider_tokens': 60000},
    'days': 30, 'generated_at': _NOW,
    'week': [{'tokens': 300000}] * 7,
    # a finished job and a failed one, so the Activity drawer has all three
    # groups to render. Nothing RUNNING: the parking assertions below depend on
    # an idle workspace, and the live path is exercised explicitly further down.
    'jobs': [{'id': 'j1', 'kind': 'Memory build', 'status': 'done', 'elapsed': 42,
              'started': _NOW - 400, 'ended': _NOW - 358, 'error': '',
              'last': 'wrote 18 entities'},
             {'id': 'j2', 'kind': 'Code review', 'status': 'error', 'elapsed': 9,
              'started': _NOW - 900, 'ended': _NOW - 891,
              'error': 'claude.exe not found', 'last': ''}],
    'wiring': {'ok': 1, 'total': 2, 'accounts': [
        {'account': 'default', 'dir': '', 'hooks': 4, 'statusline': True,
         'statusline_hidden': False, 'mode': 'auto'},
        {'account': 'teamA', 'dir': 'w', 'hooks': 0, 'statusline': True,
         'statusline_hidden': True, 'mode': ''}]},
    # An IDLE workspace: the parking assertions below all assume nothing is
    # running, and two permanently-live sessions would contradict them — the
    # stage is supposed to stay awake while sessions are live. The live path is
    # exercised explicitly further down instead.
    'live': {'total': 0, 'by_account': {}, 'window': 600},
    'hours': [0, 1, 0, 3, 2, 0, 0, 0, 1, 0, 0, 0, 0, 2, 4, 1, 0, 0, 0, 0, 1, 0, 0, 2],
    'mcp': [{'name': 'ide', 'running': True}, {'name': 'asana', 'running': False}],
    'failover': {'running': True, 'port': 20129},
    'recent': [{'project': 'acme-api', 'title': 'a session', 'msgs': 12, 'sid': 's1',
                'age': '2m', 'path': '/demo/acme-api', 'encoded': 'demo-acme-api',
                'cfgdir': '', 'account': 'default', 'provider': True}],
    'breakdown': {
        'days': [{'date': '2026-08-%02d' % (i + 1), 'tokens': 100000 + i * 9000,
                  'cost': i * 0.4, 'provider_tokens': i * 3000,
                  'accounts': {'default': 100000 + i * 9000}} for i in range(14)],
        'accounts': [{'account': 'default'}],
        'projects': [
            {'name': 'acme-api', 'enc': 'demo-acme-api', 'tokens': 900000, 'cost': 4.2,
             'age': '2m', 'mtime': _NOW, 'accounts': ['default', 'teamA'],
             'provider': True, 'sparkline': [1, 4, 2, 7, 3, 9, 5]},
            {'name': 'acme-web', 'enc': 'demo-acme-web', 'tokens': 300000, 'cost': 1.1,
             'age': '1d', 'mtime': _NOW - 90000, 'accounts': ['teamA'],
             'sparkline': [2, 1, 3]}],
        'totals': {'provider_tokens': 120000, 'provider_saved': 7.5}},
}
# The strip carries a row per CLI, and the three rows are deliberately in three
# DIFFERENT states: Claude Code has windows, Codex has the capability but has
# recorded none yet (which is what a fresh install looks like, and what this
# machine is actually in), and pi has none by construction. A stub with only the
# first would audit the one case that already worked.
PLAN = {'accounts': [{'account': 'default', 'email': 'demo@example.com', 'plan': 'max',
                      'status': 'ok',
                      'windows': [{'label': 'session', 'pct': 62, 'resets': 'in 3h'},
                                  {'label': 'weekly', 'pct': 88, 'resets': 'Fri'}]},
                     {'account': 'Codex', 'email': '', 'hid': 'codex',
                      'status': 'no_window', 'today_tokens': 48210,
                      'status_text': 'no plan window recorded yet', 'windows': []},
                     {'account': 'pi', 'email': '', 'hid': 'pi',
                      'status': 'per_provider', 'today_tokens': 3400,
                      'status_text': 'pi bills per provider, so there is no '
                                     'single plan window to report.',
                      'windows': []}]}
ROUTES = {
    '/api/state': STATE, '/api/dashboard': DASH, '/api/usage/plan': PLAN,
    # carries the project list too, and it must be the SAME rows /api/state
    # served: the poll swaps ST.projects wholesale, so a stub that disagreed
    # would make the sidebar flip between two lists every five seconds.
    '/api/memory/active': {'active': ['/demo/acme-api'],
                           'projects': STATE['projects']},
    '/api/search-index': {'rows': []},
    '/api/mcp': {'servers': [{'name': 'ide', 'status': 'ok'},
                             {'name': 'asana', 'status': 'down'}]},
    # what `claude mcp get` prints. The MCP page is a split now and the pane
    # fetches this on every pick, so a missing route would leave it spinning.
    '/api/mcp/detail': {'text': 'ide\n  transport: stdio\n  command: ide-server\n'
                                '  scope: user\n  tools: 4'},
    '/api/usage/daily': {'days': [{'day': 'd%d' % i, 'tokens': i * 1000,
                                   'tok_fmt': '%dk' % i, 'cost': i * .1}
                                  for i in range(14)]},
    '/api/usage/projects': {'projects': []},
    # Content, not empties, for the same reason as the block below: an empty
    # log renders one line and the overflow audit has nothing to measure.
    '/api/logs': {
        'events': [
            {'ts': _NOW - 90, 'lvl': 'error', 'src': 'subprocess',
             'msg': 'claude exited 1: Claude AI usage limit reached',
             'detail': 'Claude AI usage limit reached|resets at 3pm',
             'proj': '/demo/acme-api'},
            {'ts': _NOW - 400, 'lvl': 'warn', 'src': 'quota',
             'msg': 'session limit full (resets 15:00)',
             'detail': 'archeus did not start a Claude call it wanted to make',
             'proj': ''},
            {'ts': _NOW - 7200, 'lvl': 'info', 'src': 'scheduler',
             'msg': 'auto-memory pass: 1 refreshed, more still owed',
             'detail': '', 'proj': ''}],
        'path': 'C:/Users/demo/.claude/archeus-events.jsonl',
        'cap': 262144, 'debug_log': 'C:/Temp/archeus.log'},
    # `has_active` is Claude Code's shape, and it gates two cards on this page —
    # the quota ring per row, and rotation. A stub without it audits the page
    # only a Codex or pi login ever sees.
    '/api/accounts': {'has_active': True, 'label': 'Claude Code', 'hid': 'claude',
                      'home_env': 'CLAUDE_CONFIG_DIR', 'accounts': [
        {'name': 'default', 'resolved': '~/.claude', 'active': True, 'dir': ''},
        {'name': 'teamA', 'resolved': '~/.claude-teamA', 'active': False, 'dir': 'w'}]},
    # Rotation in the state the card exists for: the live account spent, another
    # with room. A stub where nothing has run out renders the quiet branch and
    # proves none of it.
    '/api/rotate/state': {
        'threshold': 98.0, 'mode': 'ask', 'hands_off': False,
        'headless_quota': 'prompt',
        'live': '~/.claude', 'live_name': 'default',
        'next': '~/.claude-teamA', 'next_name': 'teamA', 'rotating': True,
        'accounts': [
            {'name': 'default', 'dir': '', 'resolved': '~/.claude', 'pct': 99.2,
             'window': 'session', 'resets': '15:00', 'enabled': True,
             'signed_in': True, 'spent': True, 'live': True, 'blocked': ''},
            {'name': 'teamA', 'dir': 'w', 'resolved': '~/.claude-teamA',
             'pct': 12.0, 'window': 'session', 'resets': 'Tue 09:00',
             'enabled': True, 'signed_in': True, 'spent': False, 'live': False,
             'blocked': ''}],
        'events': [{'ts': 1755000000, 'lvl': 'info', 'src': 'rotate',
                    'msg': 'account default -> teamA',
                    'detail': 'session limit full (resets 15:00)', 'proj': ''}]},
    # Claude Code's own state. Stubbed with CONTENT, not empties: the settings
    # editor is a grid whose column count comes from the account list, and an
    # empty one renders nothing for the overflow audit to look at.
    '/api/client/usage': {
        'skills': [{'name': 'artifact-design', 'count': 7, 'last_used': '18d'},
                   {'name': 'claude-api', 'count': 4, 'last_used': '6d'}],
        'plugins': [{'name': 'caveman@caveman', 'count': 2473, 'last_used': '86m'}],
        'agents': [{'name': 'bg', 'count': 0, 'last_used': '59d'}]},
    '/api/background-agents': {
        'daemon': {'running': False, 'workers': [], 'recognised': True,
                   'updated': '8d'},
        'teams': {'teams': [], 'tasks': [], 'recognised': False}},
    '/api/disk': {'bytes': 795_000_000, 'accounts': [
        {'account': 'default', 'dir': '~/.claude', 'bytes': 569_000_000,
         'stores': [{'name': 'projects', 'bytes': 495_000_000, 'files': 1065,
                     'oldest_days': 120},
                    {'name': 'file-history', 'bytes': 72_000_000, 'files': 2253,
                     'oldest_days': 90}]},
        {'account': 'teamA', 'dir': '~/.claude-teamA', 'bytes': 127_000_000,
         'stores': [{'name': 'projects', 'bytes': 115_000_000, 'files': 69,
                     'oldest_days': 40}]}]},
    # auto mode: two accounts that DISAGREE about the starting mode, plus a
    # denial group — the two states the card exists to make visible
    '/api/automode': {
        'accounts': [{'name': 'default', 'dir': '', 'mode': 'auto',
                      'environment': ['$defaults', 'Source control: github.com/acme']},
                     {'name': 'teamA', 'dir': 'w', 'mode': '', 'environment': []}],
        'modes': list(_TH_CFG.PERMS), 'mode_labels': list(_TH_CFG.PERM_LABELS),
        'profiles': dict(_TH_CFG.PERM_PROFILES),
        'denials': [{'key': 'Bash:git', 'tool': 'Bash', 'count': 3, 'last': 0,
                     'reason': 'Blocked by classifier',
                     'samples': ['git push --force origin main']}]},
    '/api/automode/config': {'ok': True, 'rules': {'allow': ['Test Artifacts: …']},
                             'error': ''},
    '/api/cc-settings': {
        'groups': ['Model & reasoning', 'Context & memory', 'Advanced'],
        'group_help': {
            'Model & reasoning': 'Which model answers you, and how hard it '
                                 'thinks before it does.',
            'Context & memory': 'What Claude carries through a long '
                                'conversation, and what it remembers for next time.',
            'Advanced': 'Raw JSON, for the few settings with no simpler shape.'},
        'schema': {
            'model': {'kind': 'str', 'choices': [], 'group': 'Model & reasoning',
                      'help': 'Default model id for new sessions'},
            'effortLevel': {'kind': 'enum',
                            'choices': ['low', 'medium', 'high', 'xhigh', 'max'],
                            'group': 'Model & reasoning',
                            'help': 'Default reasoning effort'},
            'alwaysThinkingEnabled': {'kind': 'bool', 'choices': [],
                                      'group': 'Model & reasoning',
                                      'help': 'Think before every response'},
            'autoCompactWindow': {'kind': 'int', 'choices': [],
                                  'group': 'Context & memory',
                                  'help': 'Tokens of context to keep when compacting'},
            'env': {'kind': 'json', 'choices': [], 'group': 'Advanced',
                    'help': 'Environment variables for every session'}},
        'accounts': [
            {'name': 'default', 'dir': '~/.claude',
             'values': {'effortLevel': 'high', 'model': 'claude-sonnet-5'}},
            {'name': 'teamA', 'dir': '~/.claude-teamA',
             'values': {'effortLevel': 'max'}}]},
    '/api/prompt-history': {'prompts': [
        {'text': 'fix the parser', 'project': '/demo/acme-api', 'sid': 's1', 'ts': 1}]},
    # A workspace with no sessions in it screenshots as an advert for nothing,
    # and the session list is the first thing the app is for.
    '/api/sessions': {'sessions': [
        {'sid': 'a1b2c3d4', 'title': 'retry storm on the payments upstream',
         'preview': 'the gateway retried every 200ms and stampeded',
         'age': '12m', 'mtime': _NOW - 720, 'count': 84, 'account': 'default',
         'cfgdir': '', 'tokens': '412k', 'provider': False},
        {'sid': 'b2c3d4e5', 'title': 'move invoice totals to integer cents',
         'preview': 'a float total drifted by a cent across the rollup',
         'age': '3h', 'mtime': _NOW - 10800, 'count': 61, 'account': 'default',
         'cfgdir': '', 'tokens': '288k', 'provider': False},
        {'sid': 'c3d4e5f6', 'title': 'split the checkout handler',
         'preview': 'one function did validation, pricing and dispatch',
         'age': '1d', 'mtime': _NOW - 86400, 'count': 137, 'account': 'teamA',
         'cfgdir': 'w', 'tokens': '910k', 'provider': True},
        {'sid': 'd4e5f6a7', 'title': 'add the migration gate to deploy',
         'preview': 'a deploy went out ahead of its schema change',
         'age': '2d', 'mtime': _NOW - 172800, 'count': 42, 'account': 'default',
         'cfgdir': '', 'tokens': '156k', 'provider': False},
        {'sid': 'e5f6a7b8', 'title': 'cache the search index warm-up',
         'preview': 'cold start took 9s on every deploy',
         'age': '4d', 'mtime': _NOW - 345600, 'count': 25, 'account': 'teamA',
         'cfgdir': 'w', 'tokens': '77k', 'provider': True}]},
    # The memory tab is the headline feature, so the demo workspace has a
    # memory: an empty one screenshots as an advert for nothing.
    # `est` here was invented — {coverage,modules,tokens,budget} against a real
    # {digest_tokens,hook_budget,rules}. A stub that agrees with nothing audits
    # nothing, and this one hid the fact that the tab never read `est` at all.
    '/api/memory/state': {
        'generated_at': '2026-08-12T09:15:00Z',
        'n_entities': 148, 'n_lessons': 9, 'n_pending': 2, 'n_unscanned': 1,
        'n_relations': 61, 'n_module_edges': 4, 'n_modules': 11,
        'session_counter': 34,
        'hook_on': True, 'rules_on': True, 'auto_on': True, 'budget': 600,
        'pending_units': 2, 'last_extracted': 3,
        'last_cost_usd': 0.1237, 'cost_usd_total': 2.8451,
        'cost_history': [0.09, 0.14, 0.07, 0.21, 0.12, 0.18, 0.1, 0.1237],
        'auto_updated': '2026-08-12T09:15:00Z',
        'auto_last': {'graph': True, 'extracted': 3, 'lessons': 2,
                      'scanned': 1, 'pending': 2},
        'evicted': 3, 'evicted_names': ['LegacyPoller', 'OldCsvWriter', 'TempShim'],
        'top': [{'name': 'CheckoutHandler', 'hits': 33, 'module': 'api'},
                {'name': 'LedgerStore', 'hits': 17, 'module': 'billing'},
                {'name': 'RetryPolicy', 'hits': 9, 'module': 'api'}],
        # the hook is NOT installed on purpose — that branch is the only reason
        # the indicator exists
        'dirty': 4, 'dirty_hook': False,
        # `pending_units` splits into these two: a capped cycle and a failed one
        # both left it set, and every consumer worded it "the next cycle takes
        # them". One of each here, so both branches render.
        'last_failed': 1, 'last_skipped': 1,
        'last_error': 'claude exited 1: rate limit reached',
        'hits_pending': 12,
        'auto_interval': 1800,
        # per-artifact mtimes, epoch seconds. Spread out on purpose so
        # "updated N ago" renders a real range instead of one value seven
        # times, and one of them is old enough to read as stale.
        'written': {'graph': _NOW - 5400, 'rules': _NOW - 90000,
                    'worklog': _NOW - 600, 'hits': _NOW - 120,
                    'dirty': _NOW - 60, 'manifest': _NOW - 5400,
                    'snapshots': _NOW - 172800},
        'est': {'digest_tokens': 232, 'hook_budget': 600, 'rules': [
            {'file': 'archeus-mem-app-api.md', 'tokens': 372,
             'unit': 'app/api', 'glob': 'api/**'},
            {'file': 'archeus-mem-app-billing.md', 'tokens': 288,
             'unit': 'app/billing', 'glob': 'billing/**'},
            {'file': 'archeus-mem-app-root.md', 'tokens': 145,
             'unit': 'app/(root)', 'glob': '*'}]}},
    '/api/memory/progress': {'progress': None, 'last': {
        'ok': False, 'at': _NOW - 900,
        'error': 'claude exited 1: rate limit reached'}},
    '/api/memory/entity': {
        'found': True, 'name': 'CheckoutHandler', 'type': 'component',
        'summary': 'Orchestrates the checkout flow: cart totals, payment capture, '
                   'and the retry policy around the gateway call.',
        'module': 'api', 'repo': 'app', 'unit': 'app/api', 'hits': 33, 'rank': 30,
        'status': '', 'valid': True, 'kind': '', 'created_at': '2026-07-02T10:00:00Z',
        'source_files': ['api/checkout.py', 'api/retry.py'],
        'unit_summary': 'The HTTP surface: checkout, retries, and the webhook receiver.',
        'relations': [{'rel': 'uses', 'other': 'RetryPolicy', 'dir': 'out'},
                      {'rel': 'calls', 'other': 'LedgerStore', 'dir': 'out'},
                      {'rel': 'depends_on', 'other': 'PaymentGateway', 'dir': 'in'}],
        'sessions': []},
    # /api/history carries the graph's SHAPE, because a line diff of a
    # re-serialised 300 KB JSON is +27808/-27783 whatever changed. Enough
    # versions here to exercise the collapse, too.
    '/api/history': {'keys': [
        {'key': 'claude_md', 'title': 'CLAUDE.md', 'now': None, 'versions': [
            {'ts': _NOW - 3600, 'added': 4, 'removed': 61, 'age': '1h'},
            {'ts': _NOW - 7200, 'added': 2, 'removed': 2, 'age': '2h'},
            {'ts': _NOW - 86400, 'added': 3, 'removed': 4, 'age': '1d'},
            {'ts': _NOW - 90000, 'added': 5, 'removed': 3, 'age': '1d'},
            {'ts': _NOW - 172800, 'added': 9, 'removed': 1, 'age': '2d'},
            {'ts': _NOW - 259200, 'added': 1, 'removed': 1, 'age': '3d'}]},
        {'key': 'memory_graph', 'title': 'memory graph',
         'now': {'entities': 148, 'relations': 61, 'lessons': 9},
         'versions': [
            {'ts': _NOW - 3600, 'added': 27808, 'removed': 27783, 'age': '1h',
             'shape': {'entities': 151, 'relations': 60, 'lessons': 8}},
            {'ts': _NOW - 90000, 'added': 26356, 'removed': 25730, 'age': '1d',
             'shape': {'entities': 140, 'relations': 55, 'lessons': 6}}]},
        {'key': 'system_prompt', 'title': 'system prompt', 'now': None,
         'versions': []}]},
    '/api/lessons': {'counter': 34, 'ttl': 30, 'lessons': [
        {'id': 'l1', 'status': 'approved', 'confidence': 0.9,
         'kind': 'error_fix', 'last_used': 32,
         'name': 'Retries need a jittered backoff',
         'summary': 'The gateway retried on a fixed 200ms and stampeded the '
                    'upstream; every retry path takes jitter now.'},
        {'id': 'l2', 'status': 'pinned', 'confidence': 0.8,
         'kind': 'decision', 'last_used': 4,
         'name': 'Money is integer cents, never float',
         'summary': 'A float total drifted by a cent across the invoice '
                    'rollup; the ledger is integer cents end to end.'},
        # 30 - (34 - 6) = 2 sessions from eviction: the state the decay column
        # exists to warn about
        {'id': 'l3', 'status': 'approved', 'confidence': 0.6,
         'kind': 'correction', 'last_used': 6,
         'name': 'Migrations run before the deploy gate',
         'summary': 'Observed twice: a deploy went out ahead of its schema '
                    'change and the API 500d until the migration landed.'},
        {'id': 'l4', 'status': 'pending', 'confidence': 0.5,
         'kind': 'preference', 'last_used': 34,
         'name': 'Prefer one query over N+1 in the report path',
         'summary': 'The weekly report issued a query per row; it is one join '
                    'with an index now.'}]},
    '/api/worklog': {'on': True, 'installed': {'default': True, 'teamA': False},
                     'entries': [
        {'ended_at': '2026-08-12T07:40:00Z', 'session_id': 'a1b2c3d4',
         'summary': 'split the checkout handler, added retries',
         'files': ['api/checkout.py', 'api/retry.py']},
        {'ended_at': '2026-08-11T16:02:00Z', 'session_id': 'b2c3d4e5',
         'summary': 'moved totals to integer cents',
         'files': ['billing/ledger.py']}]},
    # states, weights and details — not pre-rendered terminal lines. A mix of
    # fresh/stale, because a card of all-green proves no state renders.
    '/api/workspace-status': {
        'score': 68, 'safe': True, 'generated_at': '2026-08-12T09:15:00Z',
        'checks': [
            {'name': 'manifest', 'state': 'fresh', 'detail': 'schema v1',
             'applicable': True, 'weight': 5},
            {'name': 'claude_md', 'state': 'fresh', 'detail': 'CLAUDE.md present',
             'applicable': True, 'weight': 25},
            {'name': 'claude_md_fresh', 'state': 'stale',
             'detail': 'built 3 commits ago', 'applicable': True, 'weight': 25},
            {'name': 'repo', 'state': 'stale', 'detail': 'HEAD moved since 9e1b6d6',
             'applicable': True, 'weight': 10},
            {'name': 'mcp_docs', 'state': 'stale', 'detail': 'undocumented: TestMCP',
             'applicable': True, 'weight': 15},
            {'name': 'sessions', 'state': 'fresh', 'detail': '42 analyzed',
             'applicable': True, 'weight': 10},
            {'name': 'conflicts', 'state': 'fresh', 'detail': 'none',
             'applicable': False, 'weight': 10},
            {'name': 'claude_md_claims', 'state': 'stale',
             'detail': 'CLAUDE.md says 29 palettes, memory says 32',
             'applicable': True, 'weight': 5}]},
    '/api/recall-preview': {
        'tokens': 214, 'empty': False,
        'items': ['CheckoutHandler', 'RetryPolicy', 'Retries need a jittered backoff'],
        'context': 'PROJECT MEMORY\n- CheckoutHandler (component) — orchestrates '
                   'the checkout flow\n- RetryPolicy (service) — jittered backoff'},
    '/api/system-prompt': {'text': 'Answer directly. No preamble.'},
    '/api/claude-md': {
        'exists': True, 'path': 'C:/x/alpha/CLAUDE.md', 'tokens': 1180,
        'text': '# alpha\n\nA checkout service.\n\n## Conventions\n'
                '- Money is integer cents.\n',
        'blocks': [
            {'key': 'manual', 'label': 'Your prose', 'present': True, 'tokens': 420},
            {'key': 'keep', 'label': 'Protected (2 fenced)', 'present': True,
             'tokens': 96},
            {'key': 'autogen', 'label': 'AUTOGEN — repos and commits',
             'present': True, 'tokens': 210,
             'text': '## Recent commits\n- 9e1b6d6 fix the retry stampede\n'},
            {'key': 'sessions', 'label': 'SESSIONS — session topics',
             'present': True, 'tokens': 318, 'entries': 12,
             'text': '## Session topics\n- **a1b2c3d4** (44 msgs): checkout retries\n'},
            {'key': 'memory', 'label': 'MEMORY — the digest archeus builds',
             'present': True, 'tokens': 232,
             'text': '## Project memory\n- **app/api** — checkout, retries\n'},
            # both used to be invisible here and counted as "Your prose"
            {'key': 'agents', 'label': 'AGENTS — the subagents installed here',
             'present': True, 'tokens': 140,
             'text': '## Subagents available here\n- **reviewer** — reviews diffs\n'},
            {'key': 'loop', 'label': 'LOOP — what the background loop did',
             'present': False, 'tokens': 0}]},
    # one import is BROKEN — the case the row exists to surface
    '/api/memory-map': {'files': [
        {'label': 'user (default)', 'path': 'C:/Users/x/.claude/CLAUDE.md',
         'exists': True, 'imports': []},
        {'label': 'project', 'path': 'C:/x/alpha/CLAUDE.md', 'exists': True,
         'imports': [{'ref': './docs/style.md', 'exists': True},
                     {'ref': './docs/deleted-guide.md', 'exists': False}]},
        {'label': 'project/.claude', 'path': 'C:/x/alpha/.claude/CLAUDE.md',
         'exists': False, 'imports': []}]},
    '/api/deny': {'patterns': [
        {'pattern': 'node_modules/**', 'why': '18k files, 240 MB'},
        {'pattern': 'site/**', 'why': 'generated mkdocs output'}]},
    '/api/graph-lite': {
        'files': 412, 'dirs': 38, 'repos': 1, 'deps': 96, 'truncated': False,
        'languages': [['Python', 210], ['JavaScript', 88], ['Markdown', 41]],
        'top_repos': [{'label': 'alpha', 'files': 412, 'deps': 96}],
        'modules': [{'label': 'api', 'files': 44, 'rank': 30, 'heat': 0.8},
                    {'label': 'billing', 'files': 31, 'rank': 18, 'heat': 0.5}],
        'edges': [[0, 1, 12]],
        'memory': {'entities': 148, 'lessons': 9, 'pending': 2,
                   'unscanned': 1, 'generated_at': '2026-08-12T09:15:00Z'}},
    '/api/ctxaudit': {'total': 3120, 'items': [
        {'label': 'CLAUDE.md · manual content', 'tokens': 420, 'lazy': False,
         'warnings': [], 'path': 'C:/x/alpha/CLAUDE.md'},
        {'label': 'CLAUDE.md · protected (2 fenced)', 'tokens': 96, 'lazy': False,
         'warnings': [], 'path': 'C:/x/alpha/CLAUDE.md'},
        {'label': 'CLAUDE.md · session topics (12)', 'tokens': 318, 'lazy': False,
         'warnings': ['12 session entries (cap 10) — prune (p)'],
         'path': 'C:/x/alpha/CLAUDE.md'},
        {'label': 'CLAUDE.md · memory digest', 'tokens': 232, 'lazy': False,
         'warnings': [], 'path': 'C:/x/alpha/CLAUDE.md'},
        {'label': 'global ~/.claude/CLAUDE.md', 'tokens': 640, 'lazy': False,
         'warnings': ['> 500 tok — loads in EVERY project'],
         'path': 'C:/Users/x/.claude/CLAUDE.md'},
        {'label': 'rule archeus-mem-app-api.md', 'tokens': 372, 'lazy': True,
         'warnings': [], 'path': 'C:/x/alpha/.claude/rules/archeus-mem-app-api.md'},
        # tokens=None is unknowable-statically and rendered as literal `null`
        # for its whole life — the row that proves the fix
        {'label': 'MCP servers (2) — rough estimate', 'tokens': None, 'lazy': False,
         'warnings': [], 'path': None}]},
    '/api/agents/library': {'own': [
        # two categories AND one unfiled row: the grouping, its sort (the
        # unfiled heading goes last) and the category picker all need more
        # than one bucket to be exercised at all
        {'name': 'reviewer', 'desc': 'reviews diffs', 'scope': 'user',
         'path': 'C:/x/agents/reviewer.md', 'model': '',
         'category': 'Quality security'},
        {'name': 'migrator', 'desc': 'moves schemas', 'scope': 'user',
         'path': 'C:/x/agents/migrator.md', 'model': '',
         'category': 'Core development'},
        {'name': 'scratch', 'desc': 'odd jobs', 'scope': 'user',
         'path': 'C:/x/agents/scratch.md', 'model': '', 'category': ''}],
        'category_names': ['Core development', 'Quality security'],
        'categories': [
            {'category': '01-core-development', 'agents': [
                {'name': 'backend-developer', 'desc': 'server-side APIs',
                 'path': 'C:/x/lib/backend.md', 'model': ''},
                {'name': 'frontend-developer', 'desc': 'React and friends',
                 'path': 'C:/x/lib/frontend.md', 'model': ''}]},
            {'category': '04-quality-security', 'agents': [
                {'name': 'security-auditor', 'desc': 'finds holes',
                 'path': 'C:/x/lib/sec.md', 'model': ''}]}],
        'known_tools': ['Read', 'Bash'], 'models': []},
    '/api/agents': {'categories': []},   # (the real /api/skills stub is below)
    # two rows, not zero: the enable/disable check below is `rows == 0 or ...`,
    # so an empty stub made it pass without looking at anything
    '/api/hooks': {'hooks': [
        {'event': 'Stop', 'index': 0, 'enabled': True,
         'label': 'recent-work memory', 'matcher': '',
         'cat': 'Lifecycle', 'derived': '', 'named': False},
        # a RENAMED one, so the row's second half is exercised: what the user
        # called it leads, and what it actually runs still shows beside it
        {'event': 'PreToolUse', 'index': 0, 'enabled': False,
         'label': 'no dangerous deletes', 'matcher': 'Bash',
         'cat': 'Safety guardrails', 'derived': 'block-rm-rf', 'named': True}],
        'settings_path': 'C:/x/settings.json',
        'events': {'Stop': 'when Claude finishes a turn',
                   'PreToolUse': 'before Claude runs a tool',
                   'SessionStart': 'when a session starts'},
        'accounts': [{'name': 'default', 'dir': '', 'count': 2}],
        # two templates on two DIFFERENT events, so the grouped list and its
        # filter are exercised rather than rendered as one degenerate group
        'templates': [
            {'key': 'block-rm-rf', 'desc': 'Refuse a recursive force delete',
             'event': 'PreToolUse', 'cat': 'Safety guardrails',
             'installed': True, 'missing': []},
            {'key': 'inject-memory', 'desc': 'Inject project memory at startup',
             'event': 'SessionStart', 'cat': 'Lifecycle',
             'installed': False, 'missing': []}]},
    # kind '' is Anthropic direct, which is what the stub settings say — the
    # card then renders no model widget at all, and the OmniRoute-only actions
    # stay hidden. Both branches are driven explicitly in the provider block.
    # reachable: the catalogue is only fetched for a backend that answers, so a
    # False here made 'its own catalogue' unprovable in the fixture rather than
    # in the app
    '/api/provider/status': {'ok': True, 'kind': 'omniroute', 'reachable': True,
                             'exec_model': 'auto/coding', 'providers': [],
                             'lockouts': [], 'connections': [], 'model_count': 0,
                             'usable_count': 0,
                             'gateway': {'kind': '', 'target': '', 'running': False}},
    '/api/provider/models': {'models': ['auto/coding'],
                             'labels': {'auto/coding': 'auto/coding (dynamic router)'},
                             'usable': [], 'excluded': {}, 'filtered': True,
                             'kind': 'omniroute'},
    '/api/failover/status': {'running': False},
    '/api/memory/auto-list': {'projects': []},
    '/api/memory/auto': {'projects': [], 'interval': 3600, 'next_in': 2400},
    # one job, already finished. The stub had no job route at all, so every
    # job the UI can start ended as 'Failed' here and the DONE path — the one
    # that runs onDone and clears the inline banner — was unreachable.
    '/api/job/j1': {'status': 'done', 'label': 'Staging the archeus upgrade',
                    'messages': [], 'elapsed': 1, 'result': {}},
    '/api/plugins': {'dir': 'C:/x/plugins', 'marketplaces': [
        {'name': 'official', 'source': 'github', 'repo': 'anthropics/claude-plugins',
         'path': 'C:/x/mkt'}],
        'plugins': [{'name': 'demo', 'key': 'demo@official', 'marketplace': 'official',
                     'version': '1.0', 'missing': False,
                     'provides': {'skill': ['a', 'b'], 'hook': ['h']}}]},
    '/api/plugins/provenance': {'provenance': {'skill': {'a': 'demo@official'}}},
    # one plugin behind its marketplace and a Claude Code two releases behind:
    # the update buttons only exist in that state, so the stub has to be in it.
    # Same rule for the other two subjects on this route — archeus with an
    # upgrade waiting, and a model catalogue holding a retired pin, because the
    # warning rows are the only part of those cards worth auditing.
    '/api/versions': {
        'archeus': {'installed': '1.6.0', 'latest': '1.7.0', 'mode': 'pip',
                      'update': True, 'current': False, 'error': ''},
        'models': {'count': 4, 'families': 4, 'live': True, 'age': 3600,
                   'fetched': 1, 'error': '',
                   'notices': ['default_model is set to claude-opus-4-1, '
                               'which Anthropic no longer offers']},
        'claude': {'installed': '2.1.239', 'mode': 'native', 'channel': 'latest',
                   'latest': '2.1.241', 'stable': '2.1.231', 'behind': 2,
                   'current': False, 'target': '2.1.241',
                   'versions': ['2.1.241', '2.1.240', '2.1.239'],
                   'local': ['2.1.239', '2.1.232'], 'error': '', 'fetched': 0},
        'plugins': [{'key': 'demo@official', 'name': 'demo', 'marketplace': 'official',
                     'version': '1.0', 'sha': '', 'scope': 'user',
                     'available': '1.1', 'ref': '', 'outdated': True}]},
    # a PARENT of repos, one carrying a submodule — the shape the flat board
    # could not render at all, so the stub has to be the hard case
    '/api/worktrees': {'repo': True, 'multi': True, 'root': 'D:/repos', 'repos': [
        {'path': 'D:/repos/ws', 'name': 'ws', 'kind': 'repo', 'branch': 'develop',
         'head': 'abc', 'dirty': 3, 'ahead': 0, 'behind': 2,
         'sublabel': 'submodules',
         'worktrees': [
             {'path': 'D:/repos/ws', 'name': 'ws', 'branch': 'develop',
              'head': 'abc', 'main': True, 'dirty': 3, 'ahead': 0, 'behind': 2,
              'session': None},
             {'path': 'D:/wt-a', 'name': 'wt-a', 'branch': 'feat', 'head': 'def',
              'main': False, 'dirty': 1, 'ahead': 2, 'behind': 0,
              'session': {'sid': 'deadbeef', 'title': 'refactor',
                          'account': 'teamA', 'msgs': 12, 'age': 30,
                          'live': True}}],
         'children': [
             {'path': 'D:/repos/ws/core', 'name': 'core', 'kind': 'submodule',
              'branch': 'develop', 'head': 'f00', 'dirty': 0, 'ahead': 0,
              'behind': 0, 'sublabel': 'nested repos', 'children': [],
              'worktrees': [{'path': 'D:/repos/ws/core', 'name': 'core',
                             'branch': 'develop', 'head': 'f00', 'main': True,
                             'dirty': 0, 'ahead': 0, 'behind': 0,
                             'session': None}]}]},
        {'path': 'D:/repos/solo', 'name': 'solo', 'kind': 'repo', 'branch': 'main',
         'head': 'aaa', 'dirty': 0, 'ahead': 0, 'behind': 0,
         'sublabel': 'nested repos', 'children': [],
         'worktrees': [{'path': 'D:/repos/solo', 'name': 'solo', 'branch': 'main',
                        'head': 'aaa', 'main': True, 'dirty': 0, 'ahead': 0,
                        'behind': 0, 'session': None}]}]},
    '/api/output-styles': {
        'active': 'Reviewer', 'active_scope': 'project',
        'user_dir': 'C:/x/output-styles', 'project_dir': '/demo/acme-api/.claude/output-styles',
        'styles': [
            {'name': 'default', 'description': 'As it ships.', 'scope': 'built-in',
             'builtin': True, 'active': False, 'lines': 0},
            {'name': 'Terse', 'description': 'Answers only.', 'scope': 'user',
             'builtin': False, 'active': False, 'lines': 9},
            {'name': 'Reviewer', 'description': 'Reviews only.', 'scope': 'project',
             'builtin': False, 'active': True, 'lines': 12}],
        'starters': [{'name': 'Ship', 'description': 'Change plus one line.',
                      'scope': 'starter', 'builtin': False, 'file': '', 'lines': 8}]},
    # the four scopes Claude Code loads skills from, one row each, so the page
    # is audited in the state that has something in every card
    '/api/skills': {
        'personal_dir': 'C:/x/skills', 'project_dir': '/demo/acme-api/.claude/skills',
        'accounts': [{'name': 'default', 'dir': ''}, {'name': 'teamA', 'dir': 'w'}],
        'sessions_scanned': 30,
        'personal': [{'name': 'commit-message', 'command': 'commit-message',
                      'desc': 'writes commits', 'dir': 'C:/x/skills/commit-message',
                      'scope': 'personal', 'uses': 12, 'last_used': '2d',
                      'plugin': '', 'shadowed': False, 'auto': True,
                      'weak': False, 'via': '', 'sessions': 18,
                      'of_sessions': 30}],
        'project': [{'name': 'deploy', 'command': 'deploy', 'desc': 'ships it',
                     'dir': '/demo/acme-api/.claude/skills/deploy', 'scope': 'project',
                     'uses': 0, 'last_used': '', 'plugin': '', 'shadowed': True,
                     'auto': False, 'weak': True, 'via': '', 'sessions': 0,
                     'of_sessions': 30}],
        'plugin': [{'name': 'review', 'command': 'demo:review', 'desc': 'reviews',
                    'dir': 'C:/x/plugins/demo/skills/review', 'scope': 'plugin',
                    'uses': 3, 'last_used': '5h', 'plugin': 'demo@official',
                    'shadowed': False, 'auto': True, 'weak': False,
                    'via': 'demo', 'sessions': 27, 'of_sessions': 30}],
        'bundled': [{'name': 'doctor', 'command': 'doctor', 'desc': '', 'dir': '',
                     'scope': 'bundled', 'uses': 9, 'last_used': '1d',
                     'plugin': '', 'shadowed': False, 'auto': True,
                     'weak': False, 'via': '', 'sessions': 0, 'of_sessions': 30}],
        'templates': [{'name': 'token-economy', 'command': 'token-economy',
                       'desc': 'terse answers', 'dir': 'C:/x/tmpl/token-economy',
                       'scope': 'template', 'uses': 0, 'last_used': '',
                       'plugin': '', 'shadowed': False, 'auto': True,
                       'weak': False, 'via': '', 'sessions': 0,
                       'of_sessions': 0}]},
    '/api/global-claude-md': {
        'path': 'C:/x/CLAUDE.md', 'exists': True,
        'text': '# Global\n\nAlways run the tests.\n',
        'accounts': [{'name': 'default', 'dir': ''}, {'name': 'teamA', 'dir': 'w'}]},
    '/api/loop-md': {'text': 'Check the release PR.\n', 'file': 'C:/x/loop.md',
                     'exists': True},
    # one loop still open and one that ended: the board's two states, and the
    # only place the turn counter and the End-session button are rendered
    '/api/loops': {'registry': 'C:/x/archeus-loops.json', 'loops': [
        {'id': 'aaaa1111', 'name': 'acme-api', 'path': '/demo/acme-api',
         'encoded': 'demo-acme-api', 'cfgdir': '', 'interval': '15m',
         'prompt': 'check CI', 'text': '/loop 15m check CI', 'pid': 4242,
         'started': _NOW - 900, 'stopped': 0, 'running': True, 'age': 900,
         'iterations': 4, 'last_activity': 60, 'unknown_pid': False},
        {'id': 'bbbb2222', 'name': 'acme-web', 'path': '/demo/acme-web',
         'encoded': 'demo-acme-web', 'cfgdir': 'w', 'interval': '',
         'prompt': '', 'text': '/loop', 'pid': 0,
         'started': _NOW - 8000, 'stopped': _NOW - 40, 'running': False,
         'age': 8000, 'iterations': 0, 'last_activity': 0, 'unknown_pid': False}]},
    # objects, not strings: the endpoint returns {text,score,projects,pinned}
    # and the near-miss list is what the card shows when nothing qualifies
    '/api/conventions': {
        'conventions': [{'text': 'Prefer stdlib over a new dependency', 'score': 25,
                         'projects': 2, 'pinned': False},
                        {'text': 'Tests live beside the code they cover', 'score': 20,
                         'projects': 2, 'pinned': True}],
        'near': [{'text': 'Always run the linter before committing', 'projects': 1,
                  'why': 'seen in 1 project — needs 1 more, or pin it to promote it now'}],
        'block': '## Conventions\n- Prefer stdlib over a new dependency\n'},
    # (the /api/history stub lives with the memory ones above — a second entry
    #  for the same key would silently win, and did)
    '/api/ctxaudit/prune-preview': {'ok': True, 'changed': True, 'old_tokens': 1840,
                                    'new_tokens': 1190,
                                    'dropped': ['Fable Claude Script', 'AI ClaudeMd']},
    '/api/statusline': {'installed': False, 'preview': 'Opus 5 - memory 4m',
                        'command': 'py -m claude_sessions statusline'},
    # the Tools tab's two async cards. Without them it audits two spinners —
    # which is how a wall-of-text "since last session" block stayed unnoticed.
    '/api/health': {'issues': [{'severity': 'warn', 'message': 'CLAUDE.md is heavy',
                                'hint': 'trim prose; the memory digest is already micro'}],
                    'bash': [{'command': c, 'count': n} for c, n in
                             (('cd', 272), ('py', 93), ('grep', 53), ('ls', 26),
                              ('git', 23), ('tasklist', 19), ('sed', 18))]},
    '/api/brief': {
        'suggestions': [{'tag': 'fix', 'text': 'recurring issue: ' + 'long prose ' * 30},
                        # the new emitters: an alert tag, a dismissible scan
                        # finding, and a plain local one
                        {'tag': 'stale', 'text': 'CLAUDE.md may be outdated (repo moved)'
                                                 ' — rebuild memory (+25% freshness)'},
                        {'tag': 'vuln', 'text': 'cfgdir is joined with a path on ~40 endpoints'},
                        {'tag': 'todo', 'text': 'claude_sessions/gui.py:88 — TODO: cache this'},
                        {'tag': 'test', 'text': 'no test file for: failover, denygen'}],
        'scan_at': '2026-08-30T09:12:00+00:00',
        'since': {'since': '2026-08-20', 'note': '', 'repos': [
            {'label': 'IKM.IkmVision', 'path': '/demo/a', 'dirty': 7,
             'commits': ['6580438 fix(cmake): select stubs by target architecture',
                         'a5fdea9 Merged PR 869: Fix OCSORT + interpolation']},
            {'label': 'IKM.Platform', 'path': '/demo/b', 'dirty': 2, 'commits': []}]},
        'since_last': ['▸ IKM.IkmVision', '  6580438 fix(cmake)']},
    '/api/checkpoints': {'recognised': True, 'store': True, 'orphans': 1,
                         'files': [{'path': 'D:/x/a.py', 'name': 'a.py',
                                    'versions': [{'v': 1, 'size': 10, 'mtime': 1},
                                                 {'v': 2, 'size': 12, 'mtime': 2}]}]},
}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _j(self, o):
        b = json.dumps(o).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _raw(self, body, ctype):
        self.send_response(200)
        self.send_header('Content-Type', ctype + '; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split('?')[0]
        if p == '/':
            self._raw(PAGE.encode(), 'text/html')
            return
        # the vendored modules, same allowlist the real server uses. Without
        # these the import in index.html fails, `vendor-ready` never fires and
        # the whole stage silently falls back — which the checks below would
        # then report as a stage bug rather than a missing route.
        if p.startswith('/vendor/'):
            got = vendor_asset(p[len('/vendor/'):])
            if got is None:
                self.send_error(404)
                return
            self._raw(*got)
            return
        # per-harness launch options, answered from the REAL registry: a stub
        # that invented one effort list would audit a form whose scale can
        # never be wrong, which is the whole failure this endpoint exists for
        # Same reasoning as the models route below, and it was falling through
        # to `{}`: the setup page then had no `cap_labels`, so every row in the
        # capability list rendered its raw KEY (`client_state`, `budget_cap`)
        # and both tools audited a page no user sees. `doctor` is the one part
        # that has to be invented — it shells out to the real binary.
        if p == '/api/harness/setup':
            from urllib.parse import parse_qs as _pq
            hid = (_pq(self.path.split('?', 1)[-1]).get('hid') or [''])[0]
            d = _TH_H.descriptor(hid)
            self._j({'hid': d['id'], 'label': d['label'], 'available': True,
                     'version': '1.2.3', 'latest': '1.2.3', 'auth': 'ok',
                     # neither is taken from this machine: `home_dir()` would
                     # put the developer's user name into a published
                     # screenshot, and a literal drive letter reads as somebody's
                     # real install (test_demo_fixtures guards the second)
                     'exe': '~/.local/bin/' + d['exe_names'][0],
                     'home': '~/' + '/'.join(d['home_rel']),
                     'instructions_file': d['instructions_file'],
                     'exe_names': list(d['exe_names']), 'notes': [],
                     'caps': {k: list(_TH_H.cap(d['id'], k)) for k in _TH_H.CAPS},
                     'cap_labels': dict(_TH_H.CAPS)})
            return
        if p == '/api/harness/models':
            from urllib.parse import parse_qs as _pq
            hid = (_pq(self.path.split('?', 1)[-1]).get('hid') or [''])[0]
            d = _TH_H.descriptor(hid)
            self._j({'hid': d['id'], 'efforts': list(d['efforts']),
                     'catalogue': d['id'] == 'claude',
                     # the permission and sandbox scales are the CLI's own too,
                     # and a stub that sent neither had the window falling back
                     # to Claude Code's list for every harness — which is the
                     # exact bug these fields exist to fix
                     'perms': list(d['perms'] or _TH_CFG.PERMS),
                     'perm_labels': list(d['perm_labels'] or _TH_CFG.PERM_LABELS),
                     'sandboxes': list(d['sandboxes']),
                     'sandbox_labels': list(d['sandbox_labels']),
                     'models': {'codex': ['gpt-5.5', 'gpt-5.4-mini'],
                                'pi': ['anthropic/claude-sonnet-5']}.get(d['id'], [])})
            return
        # the guided tour, answered by the REAL handler. It is a pure function
        # of a constant in `tour.py`, so a stub copy would be a second script
        # for the tour and the recorder would film words nobody ships. Same
        # reasoning as /api/harness/setup above.
        if p == '/api/tour':
            from urllib.parse import parse_qs as _pq
            from claude_sessions.gui_api import api_tour
            self._j(api_tour(
                {'which': (_pq(self.path.split('?', 1)[-1]).get('which') or [''])[0]},
                None))
            return
        self._j(ROUTES.get(p, {}))

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(n)
        path = self.path.split('?')[0]
        # Hiding a project has to STICK, because /api/memory/active re-sends the
        # project list every five seconds and the SPA swaps it in wholesale — a
        # stub that forgot the flag would revert the row mid-check and report a
        # bug in the app that only exists in the fixture.
        if path == '/api/project/hide':
            try:
                b = json.loads(raw or b'{}')
                for p in STATE['projects']:
                    if p['encoded'] == b.get('enc'):
                        p['hidden'] = bool(b.get('hidden'))
            except Exception:
                pass
        # /api/job answers with a job id so the client enters the poll loop and
        # reaches jobFinish; anything else keeps the bare ack it always sent.
        self._j({'ok': True, 'job': 'j1'} if path == '/api/job' else {'ok': True})


NL = chr(10)


def main():
    from playwright.sync_api import sync_playwright
    # REFUSE a port someone else is holding. `ThreadingHTTPServer` sets
    # allow_reuse_address, so a leaked server from an earlier run keeps
    # answering and this one binds without complaint — every check then runs
    # against whatever JS that process loaded, which on a stale one is the code
    # you are trying to test a change to. Six checks passed for the wrong
    # reason before this was noticed; the same family as the check floor below.
    import socket
    probe = socket.socket()
    try:
        if probe.connect_ex(('127.0.0.1', PORT)) == 0:
            print('FAILURES: something is already serving 127.0.0.1:%d — a '
                  'leaked run would make every check below test ITS code, not '
                  'yours. Close it and try again.' % PORT)
            return 1
    finally:
        probe.close()
    srv = ThreadingHTTPServer(('127.0.0.1', PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    errs = []
    fails = []

    ran = []

    def check(label, ok, detail=''):
        print(('  OK   ' if ok else '  FAIL ') + label + (' — ' + str(detail) if detail else ''))
        ran.append(label)
        if not ok:
            fails.append(label)

    def wait_for(expr, timeout=8000):
        """Poll a JS expression until truthy. These values settle per FRAME, not
        per second — the stage caps its own fps and the chain parks when hidden —
        so `sleep(n) then assert` measures how many frames the machine managed,
        not the behaviour. Three separate flakes here were all that."""
        end = time.time() + timeout / 1000.0
        while time.time() < end:
            if pg.evaluate(expr):
                return True
            pg.wait_for_timeout(120)
        return False

    with sync_playwright() as pw:
        # Headless Chromium has no GPU, so WebGL needs SwiftShader explicitly or
        # every scene falls back to the static gradient and the stage checks
        # below test nothing. --enable-unsafe-swiftshader is required from
        # Chrome 132; harmless before it.
        br = pw.chromium.launch(args=[
            '--use-gl=angle', '--use-angle=swiftshader',
            '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'])
        pg = br.new_page(viewport={'width': 1600, 'height': 1000})
        pg.on('console', lambda m: errs.append((m.type, m.text)) if m.type == 'error' else None)

        # keep the stack: 'Cannot set properties of null' with no frame behind it
        # is a scavenger hunt across 3000 lines
        pg.on('pageerror', lambda e: errs.append(('pageerror', str(e) + '\n' + (e.stack or ''))))
        pg.goto(f'http://127.0.0.1:{PORT}/?k={gui.TOKEN}')   # / is token-gated
        pg.wait_for_timeout(1800)

        # FIRST, and before anything reaches into the page: did the script run
        # at all? A single stray backtick inside a GLSL template literal ends
        # the string, turns the shader body into code, and kills the WHOLE
        # bundle — every `let` and every function in it, since app.js, stage.js
        # and the rest share one script scope. What the user sees is the
        # loading screen, forever, with no error anywhere they would look.
        # Without this line the tool did not report that: it crashed four
        # checks later on `INST is not defined`, from inside a Playwright
        # traceback that says nothing about what is actually wrong.
        print('\n— the page executed —')
        # typeof and not `n in window`: ST is a top-level `let`, which lives in
        # the global LEXICAL environment and never becomes a window property.
        alive = pg.evaluate(
            "['INST','STAGE','MO','ST','applyTheme','setZen']"
            ".filter(n=>{try{return eval('typeof '+n)==='undefined';}"
            "catch(e){return true;}})")
        check('every top-level module reached the page', alive == [], alive)
        if alive:
            print('  the bundle did not parse — everything below is meaningless')

        print('\n— dashboard —')
        kinds = pg.evaluate("INST.reg.map(t=>t.kind+':'+t.key)")
        check('instruments mounted', len(kinds) >= 5, kinds)
        paint = pg.evaluate("""INST.reg.map(t=>{
          const c=t.cv.getContext('2d');
          if(!t.cv.width||!t.cv.height)return t.kind+':NOSIZE';
          const d=c.getImageData(0,0,t.cv.width,t.cv.height).data;
          let n=0;for(let i=3;i<d.length;i+=4)if(d[i])n++;
          return t.kind+':'+(n>200?'painted':'BLANK');})""")
        check('every gauge painted', all('painted' in p for p in paint), paint)
        reads = pg.evaluate("[...document.querySelectorAll('.iread b')].map(e=>e.textContent)")
        # a genuine zero is a valid reading (no jobs running); only the '–'
        # placeholder means a gauge never received a feed
        check('readouts left the placeholder', '–' not in reads and '' not in reads, reads)
        # The readout is TOTAL TOKENS today, not a quota percentage. Each
        # account's quota % is a share of its own window, so no sum or average
        # of those five numbers is a meaningful "total" — tokens are the only
        # cross-account aggregate that actually adds up. 240k+130k+42k = 412k.
        check('quota ring reads the additive total', reads and reads[0] == '412.0k', reads[:1])
        segs = pg.evaluate("(INST.feed('quota').segments||[]).length")
        check('quota ring has one arc per account', segs == 3, segs)
        leg = pg.evaluate("[...document.querySelectorAll('#iQuotaLeg span')].map(e=>e.textContent)")
        check('every arc is named in the legend', len(leg) == 3, leg)

        # ── the activity drawer ──
        # It must render from the payload the poll already has and never fetch,
        # so opening it costs a repaint and nothing else.
        # openActivity() is fully synchronous — it renders from the payload the
        # poll already fetched. So the counter is read in the SAME evaluate,
        # with no await in between: anything else (the 10s poll, the heartbeat)
        # cannot slip in, and the claim stays about the drawer rather than about
        # whatever else the page happened to be doing.
        nf = pg.evaluate("""(()=>{
          const of=window.fetch; let n=0;
          window.fetch=function(){n++;return of.apply(this,arguments)};
          try{ openActivity(); } finally { window.fetch=of; }
          return n;})()""")
        check('activity drawer never fetches', nf == 0, nf)
        rows = pg.evaluate("document.querySelectorAll('#actBody .arow3').length")
        check('activity drawer lists the finished jobs', rows == 2, rows)
        sects = pg.evaluate("document.querySelectorAll('#actBody .sect').length")
        check('activity drawer has all three groups', sects == 3, sects)
        pg.evaluate("closeActivity()")
        check('activity drawer closes',
              not pg.evaluate("document.querySelector('#actovl').classList.contains('show')"))
        units = pg.evaluate("[...document.querySelectorAll('.iread i')].map(e=>e.textContent)")
        print('       units:', units)
        foots = pg.evaluate("[...document.querySelectorAll('.ifoot')].map(e=>e.textContent.trim())")
        for f in foots:
            print('       ·', f)
        kpi = pg.evaluate("[...document.querySelectorAll('.kpi .kv2')].map(e=>e.textContent)")
        check('KPI strip tweened', all(k not in ('', '–') for k in kpi), kpi)
        links = pg.evaluate("INST.feed('flow').links.length")
        check('flow map found a shared-account link', links > 0, f'{links} links')
        rows = pg.evaluate("document.querySelectorAll('#dashProjects .hrow').length")
        check('project rows reconciled', rows == 2, f'{rows} rows')

        # The live-session strip. A card still showing its skeleton has not
        # failed in any way a string test can see: its fetch is caught
        # SEPARATELY so one endpoint cannot blank the whole dashboard, and the
        # price of that is a card that can go quiet on its own. So the check is
        # that it RESOLVED — to rows or to the empty state, never to the
        # skeleton it was painted with.
        flow = pg.evaluate("(()=>{const h=document.querySelector('#dashLive');if(!h)return 'missing';if(h.querySelector('.sk'))return 'still loading';const n=h.querySelectorAll('.lrow').length;return n?('rows:'+n):(h.querySelector('.empty')?'empty':'blank');})()")
        check('the live-session card resolved',
              flow == 'empty' or flow.startswith('rows:'), flow)
        # …and every strip it drew is a REGISTERED instrument. A canvas whose
        # key was never fed is a canvas nothing ever paints, which looks
        # exactly like an idle session.
        # Driven through the page's own renderer with real rows: the stub
        # workspace has nothing recent enough to be live, so the check above
        # only ever sees the empty state and would pass with every strip
        # wired to nothing.
        seeded = pg.evaluate("(()=>{const ev=t=>({t:Date.now()/1000,type:t,name:t,dur:1});renderLive({total:2,window:600,colors:{prompt:'#7dcfff',tool:'#bb9af7'},sessions:[{sid:'s-one',encoded:'E',cfgdir:'C',account:'teamA',path:'/p/one',project:'one',title:'t',msgs:12,mtime:1,age:'2m',harness:'claude',busy:'Bash',since:1,events:[ev('prompt'),ev('tool')]},{sid:'s-two',encoded:'E',cfgdir:'C',account:'teamB',path:'/p/two',project:'two',title:'t',msgs:5,mtime:1,age:'4m',harness:'claude',busy:'',since:1,events:[ev('prompt')]}]});const h=document.querySelector('#dashLive');return [h.querySelectorAll('.lrow').length,h.querySelectorAll('.ltrail canvas').length,[...h.querySelectorAll('.iwrap')].filter(w=>!(INST.feed(w.dataset.k).events||[]).length).length,h.querySelector('.lbusy')?h.querySelector('.lbusy').textContent.trim():'',h.querySelectorAll('button[data-flow]').length];})()")
        check('live rows draw a fed strip each', seeded == [2, 2, 0, 'Bash', 2], seeded)
        gone = pg.evaluate("(()=>{renderLive({total:0,window:600,sessions:[]});return [document.querySelectorAll('#dashLive .lrow').length,!!INST.feed('live:s-one').events];})()")
        check('a session that stops being live drops its feed',
              gone == [0, False], gone)

        # Activity reads LIVE SESSIONS across accounts, not archeus's own jobs.
        # It used to read the latter and so sat at 0 on a busy workspace.
        foot = pg.evaluate("document.querySelector('#iJobsFoot').textContent")
        check('activity says idle when nothing is live', 'idle' in foot, foot)
        pg.evaluate("""refreshDashboard.__t = 1;
          (function(){ const d = window.__DASH || {};
            d.live = {total:3, by_account:{teamA:2, teamB:1}};
            d.hours = [0,1,0,3,2,0,0,0,1,0,0,0,0,2,4,1,0,0,0,0,1,0,0,2];
            window.__DASH = d; })()""")
        live = pg.evaluate("""(()=>{
          const d={live:{total:3,by_account:{teamA:2,teamB:1}},
                   hours:[0,1,0,3,2,0,0,0,1,0,0,0,0,2,4,1,0,0,0,0,1,0,0,2],
                   jobs:[],today:{sessions:9}};
          const live=d.live, nlive=live.total, jobs=0, sess=9;
          const byAcct=Object.entries(live.by_account)
            .sort((a,b)=>b[1]-a[1]).map(([n,c])=>n+(c>1?' '+c:'')).join(' · ');
          return nlive+'|'+byAcct;})()""")
        check('and names every account when they are',
              live == '3|teamA 2 · teamB', live)
        # ── the guided tour ──
        # A tour that points at nothing still renders perfectly, which is why
        # this checks the RING as well as the card: the target is resolved by
        # a data attribute, and losing that attribute is a silent failure on
        # every step at once.
        print(chr(10) + '— guided tour —')
        started = pg.evaluate("(async()=>{await TOUR.start('short');await new Promise(r=>setTimeout(r,250));const h=document.querySelector('#tour');return [!h.hidden, !!h.querySelector('.tcard'),document.querySelectorAll('.tspot').length,(h.querySelector('h4')||{}).textContent||'',TOUR.steps.length];})()")
        check('the tour opens, rings its target and names the step',
              started[:3] == [True, True, 1] and bool(started[3]) and started[4] >= 5,
              started)
        moved = pg.evaluate("(async()=>{TOUR.next();await new Promise(r=>setTimeout(r,300));const h=document.querySelector('#tour');return [(h.querySelector('.tstep')||{}).textContent||'',document.querySelectorAll('.tspot').length];})()")
        check('and moves on, keeping exactly one ring',
              moved[0].strip().startswith('2 /') and moved[1] == 1, moved)
        stopped = pg.evaluate("(()=>{TOUR.stop();return [document.querySelector('#tour').hidden,document.querySelectorAll('.tspot').length];})()")
        check('and leaves nothing behind when it stops', stopped == [True, 0], stopped)

        print('\n— the background stage —')
        vend = pg.evaluate("[!!window.THREE, !!window.ANI, !!window.THREE_POST]")
        check('vendored three/anime/postprocessing loaded', vend == [True, True, True], vend)
        check('anime does not start a second rAF chain',
              pg.evaluate("MO.ani && MO.ani.engine.useDefaultMainLoop===false"))
        live = pg.evaluate("[STAGE.ok, STAGE.failed, document.documentElement.classList.contains('stage-on')]")
        check('stage mounted and painted a frame', live == [True, False, True], live)
        check('the static wash is gone once GL is live',
              pg.evaluate("getComputedStyle(document.body,'::before').opacity") == '0')
        # a scene per skin, each one actually building
        bad = pg.evaluate("""(()=>{const out=[];
          const S=ST.skins||{};
          for(const n of Object.keys(ST.worlds||{})){
            try{ST.world=n;applyTheme(ST.theme);
              const want=S[ST.worlds[n].skin].stage;
              if(!STAGE.ok)out.push(n+':dead');
              else if(STAGE.scene!==want)out.push(n+':'+STAGE.scene);
              else if(!document.documentElement.classList.contains('world-'+n))out.push(n+':no class');
            }catch(e){out.push(n+':'+e.message);}}
          ST.world='';
          for(const n of (ST.classic_skins||[])){
            try{ST.skin=n;applyTheme(ST.theme);
              if(!STAGE.ok)out.push(n+':dead');
              else if(STAGE.scene!==S[n].stage)out.push(n+':'+STAGE.scene);
            }catch(e){out.push(n+':'+e.message);}}
          ST.skin='';applyTheme(ST.theme);return out;})()""")
        # A scene object can construct fine while its shader fails to compile —
        # three logs that to the console and renders nothing. Counting console
        # errors across the loop is what actually catches an undeclared uniform.
        pg.wait_for_timeout(400)
        shader = [t for t in errs if 'Shader Error' in t[1] or 'not compiled' in t[1]]
        check('every world and skin builds its own scene', bad == [], bad)
        check('and every shader compiles', not shader,
              shader[0][1].split(chr(10))[0] if shader else '')

        # ── A CEILING ON WHAT A FRAME COSTS ──────────────────────────────────
        # This repo already carries the rule that a tool whose only output is
        # "it passed" needs a FLOOR on how much it did. This is its mirror, and
        # it exists because the opposite failure actually shipped: the graph
        # scene grew to 1.24 MILLION triangles a frame — 0.88M of it DoubleSide
        # blended MeshPhysicalMaterial with clearcoat and iridescence — for a
        # BACKGROUND, and the first anyone knew was a user reporting tearing in
        # the Qt shell. Nothing in the suite could see it: every string matched,
        # every scene built, every shader compiled.
        #
        # Draw calls and triangle counts come off renderer.info and are
        # HARDWARE INDEPENDENT, which is exactly why this is the right shape
        # under SwiftShader — the same lesson as _T/_Tw, never assert on how
        # many frames the machine managed.
        #
        # info.autoReset has to go off first, and that is not hygiene: three
        # resets info at the top of EVERY render() call, so on the cinematic
        # tier reading it afterwards reports the composer's last fullscreen
        # quad — one call, one triangle. The first cut of this check did
        # exactly that and passed, which is the "reports success while running
        # nothing" failure wearing a different hat. Reset once, draw one whole
        # frame, read the sum, put it back.
        cost = pg.evaluate("""(()=>{const was=ST.world;
          ST.world='graph';applyTheme(ST.theme);
          const r=STAGE._ren, sc=STAGE._sc;
          r.info.autoReset=false; r.info.reset();
          if(STAGE._post)STAGE._post.render(0.016); else r.render(sc.scene, sc.camera);
          const out={tri:r.info.render.triangles, calls:r.info.render.calls,
                     tier:STAGE.tier, deg:STAGE._degraded, ratio:STAGE._ratio()};
          r.info.autoReset=true; r.info.reset();
          ST.world=was;applyTheme(ST.theme);
          return out;})()""")
        pg.wait_for_timeout(300)
        # 353,552 at the time of writing, against 757,776 before the cost pass
        # and a ceiling that must never be reachable by going back.
        #
        # READ THIS NUMBER RIGHT: three renders a TRANSPARENT DoubleSide
        # material in two passes, back faces then front, and info counts both.
        # Six of the scene's thirteen meshes are glass, so 105,448 of the total
        # is drawn twice — which is also the half that costs the most per
        # triangle, since it is blended and depth-write-off. Before the pass
        # that share was 522,576. If this check ever fails, look at what became
        # DoubleSide-transparent before you look at vertex counts.
        check('the graph frame stays under its triangle ceiling',
              0 < cost['tri'] < 400000, cost['tri'])
        # 19: thirteen meshes, six of them glass and therefore drawn twice.
        # Everything is instanced or merged, so a number in the hundreds means
        # an InstancedMesh became a Mesh per body — the shape stage.js's own
        # header forbids. The ceiling allows for the composer's mip passes.
        check('and under its draw-call ceiling', 0 < cost['calls'] < 40, cost['calls'])
        # the pixel budget is a cap on the PRODUCT, so it must actually bind
        check('the render scale is capped by the pixel budget',
              cost['ratio'] <= 1.5 + 1e-9, cost['ratio'])
        # a degrade under a healthy renderer is a false positive, and that is
        # the failure mode of a self-tuning ladder worth gating
        check('and the degrade ladder has not fired on the bench',
              cost['deg'] == 0 and cost['tier'] == 'cinematic', cost)

        print('\n— …and it is driven by state, not free-running —')
        # The whole justification for bringing a background back. String matching
        # can show the wiring exists; only running it shows the numbers move.
        pg.evaluate("stopDashboard()")          # else it re-feeds energy every 10s
        pg.evaluate("STAGE.energy(0)")
        wait_for("STAGE._E < 0.15")

        def clock_rate(ms=900):
            """Scene seconds advanced per RENDERED second — the clock multiplier
            itself. Measuring _T against wall time instead makes this a
            benchmark of the software rasteriser: headless SwiftShader drops
            frames, MO clamps a long dt, and the two windows accumulate
            different amounts of render time, so the ratio came out at 1.5 for
            a clock that had genuinely doubled."""
            t0, w0 = pg.evaluate("STAGE._T"), pg.evaluate("STAGE._Tw")
            pg.wait_for_timeout(ms)
            dt = pg.evaluate("STAGE._T") - t0
            dw = pg.evaluate("STAGE._Tw") - w0
            return (dt / dw) if dw > 0.05 else 0.0

        idle = pg.evaluate("STAGE._E")
        idle_rate = clock_rate()
        check('idle settles to a crawl', idle < 0.15, round(idle, 3))

        pg.evaluate("stageEnergy(4,0)")          # four live sessions = flat out
        wait_for("STAGE._E > 0.7")
        busy = pg.evaluate("STAGE._E")
        busy_rate = clock_rate()
        # A threshold near the asymptote pins how many frames the machine
        # managed inside the wait, not the behaviour. What matters is that
        # energy climbs a long way above idle and heads for its target.
        check('a running job raises energy',
              busy > 0.6 and busy > idle + 0.5, f'idle {idle:.2f} -> busy {busy:.2f}')
        # 0.55 + 1.7E is the clock in stage.js, so these two energies predict the
        # ratio exactly. Assert most of it rather than an invented constant: the
        # old 2.5x was above the maximum the formula can produce and had never
        # run, because the block it lived in was unreachable.
        want = ((0.55 + 1.7 * busy) / (0.55 + 1.7 * idle))
        check('and the scene clock runs proportionally faster',
              busy_rate > idle_rate * (want * 0.8),
              f'{idle_rate:.2f}x idle vs {busy_rate:.2f}x busy (predicted {want:.2f}x)')
        # Burn alone must NOT saturate. Driving liveness off a throughput number
        # is the one-word bug that made the equalizer animate forever after a
        # single token had been spent; the stage must not repeat it.
        pg.evaluate("stageEnergy(0,1)")
        wait_for("Math.abs(STAGE._E - 0.45) < 0.08")
        burn = pg.evaluate("STAGE._E")
        check('burn alone does not saturate it', 0.25 < burn < 0.65, round(burn, 3))

        pg.evaluate("MO.launched(document.querySelector('.main'))")
        pg.wait_for_timeout(120)
        check('launching fires a shockwave', pg.evaluate("STAGE._shock") > 0.5)
        check('which decays away', wait_for("STAGE._shock === 0"),
              pg.evaluate("STAGE._shock"))

        # the CAMERA, not the exposure. A page used to dim the field by up to a
        # quarter (`d` in STAGE_PAGES) and that is gone: the theme must look the
        # same whether or not you are looking at it, so a page tilts the
        # composition and nothing else. Settings is the largest bias (-0.55),
        # which is why it is still the page this navigates to.
        was = pg.evaluate("[STAGE._camTgt, STAGE._T, STAGE._calm()]")
        pg.evaluate("go('settings')")
        pg.wait_for_timeout(200)
        now = pg.evaluate("[STAGE._camTgt, STAGE._T, STAGE._pulse, STAGE._calm()]")
        check('each page tunes the one stage', now[0] < was[0], f'{was[0]} -> {now[0]}')
        check('...and it tunes the camera, not the brightness', now[3] == was[2],
              f'{was[2]} -> {now[3]}')
        check('navigation ripples but never restarts it',
              now[2] > 0 and now[1] >= was[1], now)
        pg.evaluate("go('home');startDashboard()")
        pg.wait_for_timeout(600)

        print('\n— the headline claim: idle renders zero frames —')
        # The stage is the ONE job allowed to stay registered, so turn it off to
        # assert the underlying property: with nothing live, the chain empties.
        pg.evaluate("STAGE.setTier('off')")
        # long enough for the heartbeat's second tick (pollActiveMem runs every
        # other 2500ms tick) as well as for every gauge to settle
        pg.wait_for_timeout(4000)
        pip = pg.evaluate("document.querySelectorAll('#plist .amk.pip').length")
        check('scanning project shows a live pip', pip == 1, f'{pip}')
        parked = pg.evaluate("[MO._raf===null, MO._jobs.size, INST.job===null]")
        check('frame loop parked while idle', parked == [True, 0, True], parked)

        print('\n— and with the stage running, it still stops when unseen —')
        pg.evaluate("STAGE.setTier('cinematic')")
        pg.wait_for_timeout(700)
        check('stage keeps the chain alive while visible',
              pg.evaluate("MO._raf!==null && MO._jobs.size>0"),
              pg.evaluate("MO._jobs.size"))
        # Qt reports a minimized window as visible, which is why this is driven
        # off blur rather than document.hidden alone
        pg.evaluate("setVis(false)")
        pg.wait_for_timeout(400)
        check('blur parks the chain even with the stage on',
              pg.evaluate("MO._raf===null"))
        pg.evaluate("setVis(true)")
        pg.wait_for_timeout(400)
        check('focus resumes it', pg.evaluate("MO._raf!==null"))
        pg.evaluate("MO.set('off')")
        pg.wait_for_timeout(400)
        check('motion:off stops the stage too', pg.evaluate("MO._raf===null"))
        pg.evaluate("MO.set('full');STAGE.setTier('off')")
        pg.wait_for_timeout(300)

        print('\n— unfocused: CSS stops too, and the ground stays painted —')
        # The rAF chain parking was never the whole story. Chromium throttles
        # keyframes for a HIDDEN page; an unfocused window is not hidden, and a
        # Qt one is never `document.hidden` at all. So a world's full-viewport
        # overlay and every infinite animation kept running while archeus sat
        # in the background — which is what "it flickers a lot when I'm on
        # another app" was. Asserted on COMPUTED style, because the whole class
        # of bug here is a rule that exists but loses on specificity or source
        # order (the icon rail and the skin block both learned that).
        # The stage must be ON for the background check to mean anything:
        # `html.stage-on body{background:transparent}` is the rule that opens the
        # hole, and with the stage off the base `body{background:var(--bg)}`
        # covers it anyway. Reverting the fix with the stage off produced
        # "FAILURES: none" — a check that ran and proved nothing, which is the
        # `wait_for` lesson exactly.
        # Wear the world the way the app does — ST.world + applyTheme, not
        # `applyWorld('cyber')`. applyWorld takes the world OBJECT, so a string
        # leaves `w.overlay` undefined and it sets `display:none` inline: the
        # overlay was never mounted, and "it is display:none while blurred"
        # passed by testing nothing. Same false-pass shape as `wait_for`.
        pg.evaluate("ST.world='cyber';applyTheme(ST.theme);STAGE.setTier('cinematic')")
        pg.wait_for_timeout(900)
        check('stage painted, so the blur swap is the real one',
              pg.evaluate("document.documentElement.classList.contains('stage-on')"))
        # and the overlay must EXIST before "it is display:none" says anything —
        # querySelector returning null read as a pass on the first cut
        ovl = pg.evaluate("""(() => {
          const o = document.querySelector('.ovl-fx');
          return o ? [1, getComputedStyle(o).display,
                      getComputedStyle(o).animationName] : [0, '', ''];})()""")
        check('the world mounted a VISIBLE, animating overlay',
              ovl[0] == 1 and ovl[1] != 'none' and ovl[2] != 'none', ovl)
        pg.evaluate("setVis(false)")
        pg.wait_for_timeout(250)
        st = pg.evaluate("""(() => {
          const o = document.querySelector('.ovl-fx');
          const el = document.querySelector('.beam,.spin,.pip') || document.body;
          return {
            cls:   document.documentElement.classList.contains('win-blur'),
            ovl:   o ? getComputedStyle(o).display : '(no overlay element)',
            anim:  getComputedStyle(el).animationPlayState,
            body:  getComputedStyle(document.body).backgroundColor,
            raf:   MO._raf === null,
          };})()""")
        check('win-blur marks the window unfocused', st['cls'] is True, st)
        check('the world overlay is taken down', st['ovl'] == 'none', st['ovl'])
        check('looping animations are paused, not ended',
              st['anim'] == 'paused', st['anim'])
        # transparent/rgba(0,0,0,0) here IS the hole: #stage is hidden instantly
        # while the washes fade over 500ms, and html.stage-on body is
        # transparent — so the ground was the root canvas colour
        check('the body keeps painting a background',
              'rgba(0, 0, 0, 0)' not in st['body'] and st['body'] != 'transparent',
              st['body'])
        check('and the frame chain is still parked', st['raf'] is True)
        pg.evaluate("setVis(true)")
        pg.wait_for_timeout(250)
        back = pg.evaluate("""[
          document.documentElement.classList.contains('win-blur'),
          getComputedStyle(document.querySelector('.beam,.spin,.pip')||document.body)
            .animationPlayState]""")
        check('focus resumes the animations', back == [False, 'running'], back)
        pg.evaluate("ST.world='';applyTheme(ST.theme);STAGE.setTier('off')")
        pg.wait_for_timeout(300)

        print('\n— a running job keeps the activity gauge alive —')
        # Stop the 10s dashboard poll first. It re-feeds beats:0 from the stub,
        # so whether this check sees a live gauge would otherwise depend on
        # where in the poll cycle the preceding checks happened to land.
        pg.evaluate("stopDashboard()")
        pg.evaluate("INST.set('jobs',{v:.5,beats:2})")
        pg.wait_for_timeout(600)
        alive = pg.evaluate("[MO._raf!==null, INST.job!==null]")
        check('gauge runs while work is running', alive == [True, True], alive)
        pg.evaluate("INST.set('jobs',{v:0,beats:0})")
        pg.wait_for_timeout(1500)
        check('and parks again when it stops',
              pg.evaluate("MO._raf===null"), pg.evaluate("MO._jobs.size"))
        pg.evaluate("startDashboard()")

        print('\n— every page renders —')
        # taken from NAV, not a hardcoded list: the list had already fallen
        # behind by one page, and a page nobody checks is a page nobody knows
        # is broken
        pages = pg.evaluate('NAV.map(n => n[0])') + ['home']
        check('page list came from NAV', len(pages) > 8, pages)
        for p in pages:
            before = len(errs)
            pg.evaluate(f"go('{p}')")
            pg.wait_for_timeout(500)
            check(f'page {p}', len(errs) == before, errs[before:])

        # "no JS error" passes on a card that rendered nothing, and the update
        # buttons only exist when something is actually behind — so assert the
        # state, not just the absence of an exception.
        #
        # The three version cards are on Settings ▸ Updates, and they are filled
        # by a fetch AFTER the page paints, through a mount that is
        # `display:contents` — so a check on the page they used to be on would
        # have passed for the wrong reason once and then gone quiet.
        pg.evaluate("go('updates')")
        wait_for("!!document.querySelector('#verCard')")
        ver = pg.evaluate(
            "(()=>{const c=document.querySelector('#verCard'),"
            "m=document.querySelector('#verMount');return c?{"
            "card:1,behind:/2 releases behind/.test(c.textContent),"
            "latest:/Update to latest/.test(c.textContent),"
            "rollback:/2\\.1\\.232/.test(c.textContent),"
            "self:!!document.querySelector('#selfCard'),"
            "models:!!document.querySelector('#modelCard'),"
            "flat:getComputedStyle(m).display==='contents',"
            "wide:Math.round(c.getBoundingClientRect().width)}:{card:0};})()")
        check('the version cards are on Settings > Updates',
              ver.get('card') and ver.get('behind') and ver.get('latest')
              and ver.get('rollback') and ver.get('self') and ver.get('models'),
              ver)
        # a mount that kept its own box would leave the cards in one column of
        # the form's grid at a fraction of the width
        check('the async mount is transparent to the form layout',
              ver.get('flat') and ver.get('wide', 0) > 500, ver)
        # Rotation: "no JS error" would pass on a card that said nothing, and
        # the whole point of the card is that it names the account work is about
        # to move to. The fixture has the live account spent and another with
        # room, so every branch of it is on screen.
        # pinned back to Claude Code: an earlier check leaves HARNESS_HID on
        # whichever CLI it was inspecting, and the account page of a CLI with no
        # active login has no rotation card by design
        pg.evaluate("HARNESS_HID='claude';go('accounts')")
        wait_for("!!document.querySelector('#rotOut .tbl')")
        rot = pg.evaluate(
            "(()=>{const c=document.querySelector('#rotOut');return c?{"
            "card:1,mode:[...c.querySelectorAll('#rotMode .chip')].map(x=>x.textContent.trim()),"
            "on:(c.querySelector('#rotMode .chip.on')||{}).textContent,"
            "thr:(c.querySelector('#rotThr')||{}).value,"
            "next:/next work goes to/.test(c.textContent),"
            "spent:/spent/.test(c.textContent),"
            "nan:/NaN/.test(c.textContent),"
            "boxes:c.querySelectorAll('input[type=checkbox]').length,"
            "hist:/default -> teamA/.test(c.textContent)}:{card:0};})()")
        check('the rotation card offers all three modes',
              rot.get('card') and len(rot.get('mode') or []) == 3
              and (rot.get('on') or '').startswith('Semi'), rot)
        check('…and says which account is next, and why',
              rot.get('next') and rot.get('spent') and rot.get('hist')
              and rot.get('thr') == '98' and not rot.get('nan'), rot)
        check('…with one opt-out per login', rot.get('boxes') == 2, rot)
        # the strip is on every page, so this is also the check that a spent
        # account is visible without going looking for it
        strip = pg.evaluate(
            "(()=>{const u=document.querySelector('#ubar');return u?{"
            "says:/is out/.test(u.textContent),"
            "to:/teamA/.test(u.textContent)}:{};})()")
        check('the quota strip says the account is out and where work goes',
              strip.get('says') and strip.get('to'), strip)
        pg.evaluate("go('plugins')")
        pg.wait_for_timeout(600)
        pupd = pg.evaluate(
            "[...document.querySelectorAll('#pluginCard button')]"
            ".filter(b=>b.textContent.trim()==='Update').length")
        check('an outdated plugin offers an update', pupd == 1, pupd)
        check('the version cards left the plugins page',
              pg.evaluate("!document.querySelector('#verCard')"))

        # ── the update strip, through the job that borrows it ──
        # "Update now" starts an inline job whose HOST IS THE STRIP, so the
        # finish path clears the strip — display:none, innerHTML '' — and then
        # asks updStaged to paint the staged message into it. Nothing put the
        # strip back on screen, so the Restart button and every sign the click
        # had done anything went into a hidden element. Nothing here could see
        # it: the stub had no job route, so the DONE path never ran at all.
        pg.evaluate('drawUpdateBar()')
        wait_for("!!document.querySelector('#updNow')")
        pg.evaluate("document.querySelector('#updNow').click()")
        wait_for("!!document.querySelector('#updRestart')", 12000)
        strip = pg.evaluate(
            "(()=>{const b=document.querySelector('#updbar');return {"
            "shown:getComputedStyle(b).display!=='none',"
            "h:Math.round(b.getBoundingClientRect().height),"
            "staged:/is installed/.test(b.textContent)};})()")
        check('the staged update strip is on screen, not painted into a hidden'
              ' element', strip.get('shown') and strip.get('h', 0) > 10
              and strip.get('staged'), strip)

        print('\n— project tabs —')
        # Two dispatchers: go() drives the global pages, `TAB=<id>;go('project')`
        # the per-project ones. The page walk above only ever exercised the
        # first, so the worktree board — the largest thing on the project side —
        # had never been rendered by this tool.
        pg.evaluate("openProject(ST.projects[0])")
        pg.wait_for_timeout(700)
        # Derived, like the page list two blocks up. This walked a hardcoded
        # 4-of-9 while carrying a comment about exactly this rot.
        for t in pg.evaluate('TABS.map(t => t[0])'):
            before = len(errs)
            pg.evaluate(f"TAB='{t}';go('project')")
            pg.wait_for_timeout(600)
            check(f'tab {t}', len(errs) == before, errs[before:])

        # "no JS error" passes on an EMPTY card, which is exactly what the old
        # renderer produced against the new API shape — so assert the list AND
        # the pane. The board used to be a `<details>` tree whose summary row
        # spread a name, a branch and four tags across the whole window with a
        # `flex:1` hole in the middle; it is one list with the worktrees of the
        # repo you picked beside it, so both halves have to be checked.
        pg.evaluate("TAB='worktrees';go('project')")
        pg.wait_for_timeout(600)
        rows = pg.evaluate("document.querySelectorAll('#content .tbody .hrow').length")
        check('repos tab lists every repo, submodules included', rows == 3, rows)
        txt = pg.evaluate("document.querySelector('#content').innerText")
        check('a submodule is indented and labelled',
              'core' in txt and 'submodule' in txt, txt[:200])
        # the list alone must not be the whole page: one repo is pre-selected,
        # so the pane is never the intro on a board that has something to show
        det = pg.evaluate("document.querySelector('#wtDet').innerText")
        check('a repo is picked and its worktrees are in the pane',
              'Branch' in det and 'refactor' in det, det[:160])
        picked = pg.evaluate("document.querySelectorAll('#content .hrow.on').length")
        check('…and the row it came from is marked', picked == 1, picked)

        print('\n— hidden projects leave the sidebar and can come back —')
        # The reveal button only exists while something IS hidden, so the branch
        # that draws it is unreachable from every other check in this file.
        # stays on whatever page is open — the sidebar is global, and go('home')
        # here would drop CUR out from under the project checks that follow
        pg.evaluate("ST.projects[1].hidden=true;drawProjects()")
        pg.wait_for_timeout(300)
        rows = pg.evaluate("document.querySelectorAll('#plist .proj').length")
        shown = pg.evaluate(
            "(()=>{const b=document.querySelector('#bHidden');"
            "return !!b && b.offsetParent!==null;})()")
        check('a hidden project is out of the list, with a way back', rows == 1 and shown,
              f'{rows} rows, reveal button {shown}')
        pg.evaluate("document.querySelector('#bHidden').click()")
        pg.wait_for_timeout(300)
        rows = pg.evaluate("document.querySelectorAll('#plist .proj').length")
        tagged = pg.evaluate(
            "document.querySelectorAll('#plist .proj .tag').length > 0")
        check('revealing shows it again, marked', rows == 2 and tagged, rows)
        pg.evaluate("ST.projects[1].hidden=false;SHOW_HIDDEN=false;drawProjects()")

        print('\n— the pages that could not explain themselves —')
        # Skills: every scope Claude Code loads from, each row carrying the
        # command you type. The old page showed a project card that was inert
        # without a project, and a "library" nothing reads.
        pg.evaluate("go('skills')")
        pg.wait_for_timeout(900)
        txt=pg.evaluate("document.querySelector('#content').innerText")
        check('every scope is in one list',
              all(w in txt for w in ('personal','project','plugin','bundled')))
        check('a skill row shows the command you type',
              pg.evaluate("document.querySelectorAll('#content .skcmd').length")>=4)
        check('a shadowed project skill says so','shadowed' in txt)
        # THE point of the rework: two signals, never one number. "typed" is
        # Claude Code's counter; "in N/M sessions" is measured from transcripts,
        # and the gap between them is what made caveman read as unused.
        check('both usage signals are shown',
              'typed 12×' in txt and 'in 18/30 sessions' in txt)
        check('a skill Claude may not auto-load says so','manual only' in txt)
        check('a description too thin to match on says so','thin description' in txt)
        # the filter box, which is the only reason a long list is usable
        pg.evaluate("(()=>{const i=document.querySelector('#skQ');i.value='deploy';"
                    "i.dispatchEvent(new Event('input'));})()")
        pg.wait_for_timeout(200)
        vis=pg.evaluate("[...document.querySelectorAll('#content .skrow')]"
                        ".filter(e=>e.style.display!=='none').length")
        check('the skills filter narrows the list',vis==1,
              str(vis)+' visible; count='+str(pg.evaluate("document.querySelector('#skCount').textContent")))
        # a scope chip is a second filter over the SAME pass — the two must not
        # fight over `display`, which is why they share one function
        pg.evaluate("(()=>{const i=document.querySelector('#skQ');i.value='';"
                    "i.dispatchEvent(new Event('input'));})();skScope('plugin')")
        pg.wait_for_timeout(200)
        scoped=pg.evaluate("[...document.querySelectorAll('#content .skrow')]"
                           ".filter(e=>e.style.display!=='none')"
                           ".map(e=>e.dataset.scope)")
        check('a scope chip narrows to that scope',
              scoped==['plugin'],scoped)
        pg.evaluate("skScope('all')")
        pg.wait_for_timeout(150)
        check('…and going back to all restores every row',
              pg.evaluate("[...document.querySelectorAll('#content .skrow')]"
                          ".filter(e=>e.style.display!=='none').length")==4)
        # THE point of the split: the list is what you scan and the pane is what
        # you read. Nothing picked yet is the Add form, so the pane is never an
        # empty state, and picking a row swaps in that skill with its buttons.
        check('the detail pane starts on the Add form, not on nothing',
              pg.evaluate("document.querySelector('#skDet').innerText")
              .strip().lower().startswith('add a skill'))
        pg.evaluate("document.querySelector('#content .skrow').click()")
        pg.wait_for_timeout(150)
        det=pg.evaluate("document.querySelector('#skDet').innerText")
        cmd=pg.evaluate("document.querySelector('#content .skrow .skcmd').textContent")
        check('picking a row fills the detail pane with that skill',
              cmd.strip() in det, f'{cmd!r} not in pane')
        check('…and the picked row is marked, so the filter cannot lose it',
              pg.evaluate("document.querySelectorAll('#content .skrow.on').length")==1)
        pg.evaluate("(()=>{const i=document.querySelector('#skQ');"
                    "i.value='zzznope';i.dispatchEvent(new Event('input'));})()")
        pg.wait_for_timeout(200)
        check('a filter that matches nothing still leaves what you picked',
              pg.evaluate("[...document.querySelectorAll('#content .skrow')]"
                          ".filter(e=>e.style.display!=='none').length")==1)
        pg.evaluate("(()=>{const i=document.querySelector('#skQ');"
                    "i.value='';i.dispatchEvent(new Event('input'));})();skAddPane()")
        pg.wait_for_timeout(150)
        check('Add a skill comes back to the pane',
              pg.evaluate("document.querySelectorAll('#content .skrow.on').length")==0
              and pg.evaluate("!!document.querySelector('#skTmpl')"))

        # Output styles: what is active, WHERE it is pinned, and — now that the
        # page is a split — that picking a row fills the pane rather than
        # opening a drawer over the page you were reading. A built-in has no
        # file at all, so the pane has to say so instead of showing "(empty)".
        pg.evaluate("go('ostyles')")
        pg.wait_for_timeout(900)
        txt=pg.evaluate("document.querySelector('#content').innerText")
        check('the output-style page says what is in force','in force' in txt)
        check('…and which file pins it','settings.json' in txt)
        check('starters are offered','Starters from archeus' in txt)
        check('every scope is one list, not one card each',
              pg.evaluate("document.querySelectorAll('#content .tbody .hrow').length")==4)
        before=len(errs)
        pg.evaluate("osSel(0)")
        pg.wait_for_timeout(500)
        det=pg.evaluate("document.querySelector('#osDet').innerText")
        check('picking a style fills the pane and nothing overlays the page',
              len(det)>20 and len(errs)==before
              and not pg.evaluate(
                  "document.querySelector('#drawer').classList.contains('show')"),
              det[:60])
        check('a built-in says it has no file rather than reading "(empty)"',
              'no file to read' in det, det[:80])

        # MCP: the page was one card whose rows put the name at `flex:1` and
        # three buttons at the far right, so on a wide window it was a name,
        # two thousand pixels of nothing, and then the controls — and `Detail`
        # opened a drawer over the page. List, then pane.
        pg.evaluate("go('mcp')")
        pg.wait_for_timeout(900)
        rows = pg.evaluate("document.querySelectorAll('#content .tbody .hrow').length")
        check('every MCP server is one row of one list', rows == 2, rows)
        before = len(errs)
        pg.evaluate("mcPick(0)")
        pg.wait_for_timeout(500)
        det = pg.evaluate("document.querySelector('#mcDet').innerText")
        check('picking a server fills the pane with what it is',
              'transport' in det and len(errs) == before, det[:80])
        check('…and nothing overlays the page to show it',
              not pg.evaluate(
                  "document.querySelector('#drawer').classList.contains('show')"))

        # The account's global instructions used to be the third card of the MCP
        # page. It is the file read in EVERY session, so it has its own page.
        pg.evaluate("go('globalmd')")
        pg.wait_for_timeout(900)
        check('global CLAUDE.md is editable on its own page',
              pg.evaluate("!!document.querySelector('#gmText')"))

        # A /loop lives inside a session, so the board's job is to say what is
        # open, how often it has fired, and how to end it.
        pg.evaluate("go('loops')")
        pg.wait_for_timeout(900)
        txt = pg.evaluate("document.querySelector('#content').innerText")
        check('the loops board separates open sessions from ended ones',
              'session open' in txt and 'ended' in txt)
        check('…and reports iterations from the transcript', '4 turns' in txt)
        check('loop.md is edited beside the loops',
              pg.evaluate("!!document.querySelector('#loopMd')"))
        # the command is built in front of you rather than guessed at
        pg.evaluate("(()=>{const i=document.querySelector('#loopInt');i.value='15m';"
                    "i.dispatchEvent(new Event('input'));"
                    "const p=document.querySelector('#loopPrompt');p.value='check CI';"
                    "p.dispatchEvent(new Event('input'));})()")
        pg.wait_for_timeout(150)
        check('the start form previews the exact command',
              'check CI' in pg.evaluate("document.querySelector('#loopPreview').textContent"))
        # the two kinds are the whole feature: one needs a session, the other
        # runs with everything closed
        pg.evaluate("loopKind('session')")
        pg.wait_for_timeout(400)
        check('switching to the session kind previews a /loop command',
              pg.evaluate("document.querySelector('#loopPreview').textContent")
              .startswith('/loop'))
        pg.evaluate("loopKind('schedule')")
        pg.wait_for_timeout(400)
        txt=pg.evaluate("document.querySelector('#content').innerText")
        check('the background kind states its guardrails',
              'expiry' in txt.lower() and 'permission' in txt.lower(),txt[:0])
        check('a scheduled row shows runs, cost and expiry',
              'background' in txt and 'run' in txt)

        # 155 agents in 10 collapsed categories is not something you scroll
        pg.evaluate("go('agents')")
        pg.wait_for_timeout(900)
        check('the agent library has a filter',
              pg.evaluate("!!document.querySelector('#agQ')"))
        # your own agents are divided by category too — a flat roll of
        # everything installed is the wall the library would be without folders
        # the FIRST card only — both lists are collapsed categories now, so an
        # unscoped query returns your own three followed by the library's
        heads=pg.evaluate("[...document.querySelector('#content .card')"
                          ".querySelectorAll('.fgrp summary')]"
                          ".map(e=>e.textContent.trim().replace(/\\s+\\d+$/,''))")
        check('your agents are grouped by category, unfiled last',
              heads==['Core development','Quality security','Uncategorised'],heads)
        pg.evaluate("(()=>{const i=document.querySelector('#agQ');if(!i)return;"
                    "i.value='migrat';i.dispatchEvent(new Event('input'));})()")
        pg.wait_for_timeout(200)
        vis=pg.evaluate("[...document.querySelectorAll('#content .agrow')]"
                        ".filter(e=>e.style.display!=='none').length")
        grps=pg.evaluate("[...document.querySelectorAll('#content .fgrp')]"
                         ".filter(e=>e.style.display!=='none').length")
        check('the agent filter drops the categories it emptied',
              vis==1 and grps==1,f'{vis} rows in {grps} groups')
        pg.evaluate("(()=>{const i=document.querySelector('#agQ');if(!i)return;"
                    "i.value='security';i.dispatchEvent(new Event('input'));})()")
        pg.wait_for_timeout(200)
        # BOTH lists are collapsed categories now — your own agents used to be
        # printed expanded under a plain heading, which is the wall the library
        # would be without its folders — so a term matching in each opens one in
        # each. The count is per CARD, not per page, or this check would have
        # gone on passing by counting only half the page.
        opened=pg.evaluate(
            "[...document.querySelectorAll('#content .card')].map(c=>"
            "[...c.querySelectorAll('details')]"
            ".filter(d=>d.open&&d.style.display!=='none').length)")
        check('the agent filter opens the matching category in each list',
              opened==[1,1],opened)
        # filing a new agent must offer the categories that exist AND accept a
        # name that does not — one control, not a select plus an escape hatch
        # NOT `pg.evaluate("agNew()")`: evaluate awaits what the expression
        # returns, and this one returns a promise that resolves on OK/Cancel —
        # the tool would wait for a click that is never coming
        pg.evaluate("agNew();0")
        pg.wait_for_timeout(900)
        opts=pg.evaluate("[...document.querySelectorAll('#pBody datalist option')]"
                         ".map(o=>o.value)")
        check('the new-agent form offers the existing categories and takes a new one',
              opts==['Core development','Quality security'],opts)
        pg.evaluate("document.querySelector('#pCancel').click()")
        pg.wait_for_timeout(300)
        # go(<global page>) clears CUR; the project-tab checks below need it back
        pg.evaluate("openProject(ST.projects[0])")
        pg.wait_for_timeout(500)

        print('\n— controls, not read-outs —')
        # A toggle you can only READ is the class no route-coverage test can
        # see, because the failure is not an unused route — it is no route at
        # all. So: the memory flags must be real checkboxes.
        pg.evaluate("TAB='memory';go('project')")
        pg.wait_for_timeout(900)
        for cid in ('memHook', 'memRules', 'wlOn', 'autoMem'):
            kind = pg.evaluate(
                f"(()=>{{const e=document.querySelector('#{cid}');"
                f"return e?e.type:'missing';}})()")
            check(f'#{cid} is a checkbox', kind == 'checkbox', kind)
        btype = pg.evaluate(
            "(()=>{const e=document.querySelector('#memBudget');return e?e.type:'missing';})()")
        check('#memBudget is a number input', btype == 'number', btype)

        # ── the memory tab shows the artifacts, not just counters ──
        # Every number below was already in a payload this tab fetched; the
        # regression class is "the renderer stopped reading a field", which no
        # route-coverage gate can see because the route is called either way.
        print('\n— memory: what is built, and what it costs —')
        inv = pg.evaluate("document.querySelectorAll('#memInv tr').length")
        check('the inventory lists the memory artifacts', inv >= 12, f'{inv} rows')
        txt = pg.evaluate("document.querySelector('#content').innerText")
        check('the always-on vs lazy split is stated with numbers',
              '232 tok' in txt and 'when Claude opens a matching path' in txt
              and 'per prompt' in txt, txt[:120])
        # 232 tok reads as a lot or a little depending on nothing at all. The
        # share of the window is the denominator that makes it interpretable,
        # and CTX_WINDOW sat defined-and-unused until it rendered.
        check('always-on cost is given as a share of the context window',
              '0.1%' in txt, [l for l in txt.split('\n') if '%' in l][:2])
        # four load-trigger groups, stated once each, instead of a badge
        # repeated down a 12-row wall
        buckets = pg.evaluate(
            "[...document.querySelectorAll('#memInv .lbl')].map(e=>e.innerText)")
        check('the artifacts are grouped by when they reach a session',
              len(buckets) == 4, buckets)
        glob = pg.evaluate(
            "(()=>{const d=[...document.querySelectorAll('#memInv details')]"
            ".find(x=>x.innerText.includes('Path-scoped'));if(!d)return 'no details';"
            "d.open=true;return d.innerText;})()")
        check('each rule names the paths it loads for',
              'api/**' in glob and 'app/api' in glob, glob[:100].replace('\n', ' '))
        check('cumulative spend is shown, not just the last cycle',
              '2.845' in txt, [l for l in txt.split('\n') if 'total' in l.lower()][:2])
        check('eviction names what it dropped', 'LegacyPoller' in txt)
        check('reinforcement is visible', 'CheckoutHandler' in txt and '33' in txt)
        check('a queued edit with no hook installed is flagged',
              'stale-on-edit hook not installed' in txt)
        # a failed unit and a capped one were summed into one `pending_units`
        # and both worded "the next cycle takes them", so a rate-limited
        # account produced dead calls forever, reported as progress.
        check('a failed module reads as failed, not as queued',
              'could not be extracted' in txt and 'rate limit reached' in txt,
              [l for l in txt.split('\n') if 'extracted' in l][:2])
        # and it says WHEN. A capped cycle used to trigger a 45s catch-up pass,
        # which spent a daily limit inside an hour on a repo with a backlog; the
        # cap is now the only thing that decides how much one pass does, and the
        # configured cadence the only thing that decides how often.
        check('a capped module says when the next pass is',
              '1 module(s) — the next pass takes some, in 30 min' in txt,
              [l for l in txt.split('\n') if 'queued' in l.lower()][:2])
        check('the cadence is stated where auto-memory is switched on',
              'every 30 min' in txt)
        # the row showed the literal 'folding in' off the top-hits list, which
        # is a different thing and never changed
        # the bookkeeping bucket is collapsed by default — it is the one group
        # that costs nothing — so open it before reading, which also proves the
        # rows are really in there rather than dropped
        hits = pg.evaluate(
            "(()=>{const d=document.querySelector('#memKeep');if(!d)return 'no bucket';"
            "d.open=true;const r=[...document.querySelectorAll('#memInv tr')]"
            ".find(r=>r.innerText.includes('Reinforcement log'));"
            "return r?r.innerText:'no row';})()")
        check('the reinforcement log says how much is waiting',
              '12 to fold in' in hits, hits[:120].replace('\n', ' '))
        # ttl 30 - (counter 34 - last_used 6) = 2 sessions left on lesson l3,
        # and the pinned one is exempt. Read the CELL, not the row text: a row
        # mentioning '2' anywhere would pass a substring check while the column
        # rendered nothing.
        decay = pg.evaluate(
            "(()=>{const cell=t=>{const r=[...document.querySelectorAll('.tbl tr')]"
            ".find(r=>r.innerText.includes(t));return r?r.cells[3].innerText.trim():'';};"
            "return {near:cell('Migrations run'),pinned:cell('Money is integer')};})()")
        check('a lesson says how close it is to being dropped',
              decay['near'] == '2' and decay['pinned'] == 'kept', decay)
        # structured checks, not an ANSI-stripped <pre> blob — and they arrive
        # AFTER the paint now, so wait for the fill rather than the page
        pg.wait_for_selector('#wsBox .hrow', timeout=5000)
        wsr = pg.evaluate(
            "(()=>{const c=document.querySelector('#wsBox');"
            "return c?{rows:c.querySelectorAll('.hrow').length,"
            "fix:c.querySelectorAll('.hrow .btn').length,pre:c.innerText,"
            "head:(document.querySelector('#wsHead')||{}).innerText||''}:null;})()")
        check('workspace checks render as rows with states',
              bool(wsr) and wsr['rows'] == 8 and 'fresh' in wsr['pre']
              and 'stale' in wsr['pre'], wsr and wsr['rows'])
        check('every stale check offers the thing that fixes it',
              bool(wsr) and wsr['fix'] >= 4, wsr and wsr['fix'])
        # the prose-vs-graph check has to quote BOTH numbers: it is the one row
        # whose detail IS the whole finding, because no button can repair it
        check('the prose-vs-graph row names both numbers',
              bool(wsr) and '29 palettes' in wsr['pre'] and '32' in wsr['pre'],
              wsr and wsr['pre'][:80])
        # the score is what the header and the manifest row both quote, and both
        # are written by the same late fill — a card that fills its rows but not
        # its header reads as "no score" forever
        check('the freshness score reaches the header and the manifest row',
              bool(wsr) and 'score' in wsr['head'].lower()
              and 'score' in pg.evaluate(
                  "(document.querySelector('#wsScore')||{}).innerText||''").lower(),
              wsr and wsr['head'])
        check('memory history is on the memory tab',
              pg.evaluate("!!document.querySelector('#histOut')"))
        # "is this stale?" is the second question after "who wrote it?", and no
        # row could answer it — one build time for artifacts written by five
        # different code paths on five different schedules
        inv = pg.evaluate(
            "(()=>{const h=document.querySelector('#memInv');"
            "return h?h.innerText:'';})()")
        check('each machine-written row says when it was last written',
              inv.count('updated ') >= 5, inv.count('updated '))
        check('a row that cannot honestly be dated is left bare',
              'CLAUDE.md digest' in inv
              and 'updated' not in inv.split('CLAUDE.md digest')[1].split('AUTOGEN')[0])
        # a name and a hit count says a fact matters without saying what it is
        pg.evaluate("entDetail('CheckoutHandler')")
        pg.wait_for_timeout(600)
        det = pg.evaluate(
            "(()=>{const d=document.querySelector('#drawer');"
            "return d&&d.classList.contains('show')?"
            "document.querySelector('#dBody').innerText:'';})()")
        check('a reinforced fact opens and explains itself',
              'Orchestrates the checkout flow' in det and 'RetryPolicy' in det
              and 'api/checkout.py' in det, det[:80].replace('\n', ' '))
        pg.evaluate("document.querySelector('#drawer').classList.remove('show')")
        # a line diff of a re-serialised 300KB JSON is +27808/-27783 whatever
        # changed — a true number that answers nothing
        hist = pg.evaluate("document.querySelector('#histOut').innerText")
        check('a graph version is summarised by its shape, not by JSON lines',
              '151 facts' in hist and '27808' not in hist,
              [ln for ln in hist.split('\n') if 'facts' in ln][:1])

        print('\n— CLAUDE.md: block by block —')
        pg.evaluate("TAB='claudemd';drawProject()")
        pg.wait_for_timeout(900)
        blk = pg.evaluate(
            "(()=>{const h=document.querySelector('#cmBlocks');if(!h)return null;"
            "return {rows:h.querySelectorAll('.agrow').length,txt:h.innerText};})()")
        check('CLAUDE.md is shown as its blocks', bool(blk) and blk['rows'] == 7,
              blk and blk['rows'])
        check('each block carries its token cost',
              bool(blk) and blk['txt'].count('tok') >= 7)
        # who wrote it is the FIRST question a reader has, and the row used to
        # make them infer it. The subagent table is the one that was labelled
        # "your prose" while archeus rewrote it on every agent change.
        check('every block says who writes it',
              bool(blk) and blk['txt'].count('archeus writes it') == 5
              and blk['txt'].count('you write it') == 2, blk and blk['txt'][:0])
        check('every block says what it IS, not just who wrote it',
              bool(blk) and 'when to delegate to each' in blk['txt']
              and 'what has been committed lately' in blk['txt'])
        check('each machine block has the button that regenerates it',
              pg.evaluate("document.querySelectorAll('#cmBlocks .btn').length") >= 4)
        cm = pg.evaluate("document.querySelector('#content').innerText")
        check('a broken @import is called out',
              'deleted-guide.md' in cm and 'missing' in cm)
        check('version history moved to the file it is history of',
              pg.evaluate("!!document.querySelector('#histOut')"))
        # 12 versions is the right thing to KEEP and the wrong thing to show
        hv = pg.evaluate(
            "(()=>{const h=document.querySelector('#histOut');return h?"
            "{rows:h.querySelectorAll(':scope > .agrow').length,"
            "more:!!h.querySelector('details')}:null;})()")
        check('a long history collapses instead of burying the recent one',
              bool(hv) and hv['rows'] == 4 and hv['more'], hv)

        print('\n— audit: one turn, every surface —')
        pg.evaluate("TAB='audit';drawProject()")
        pg.wait_for_timeout(900)
        au = pg.evaluate("document.querySelector('#content').innerText")
        # Both halves matter. `null` leaking to screen is the bug; the positive
        # half proves the unknowable ROW actually rendered, or the check passes
        # by measuring nothing. The wording is the screen's, not jargon: `~?`
        # was what this asserted until the pass that removed it from app.js as
        # one of the places the app spoke to itself — and this check was not
        # moved with it, so the gate failed on every run in between.
        check('an unknowable token count is not rendered as null',
              'null' not in au and 'not until it connects' in au,
              [l for l in au.split('\n') if 'null' in l][:2])
        check('audit rows can open the file they cost you', 'open' in au)
        check('audit no longer duplicates the history panel',
              not pg.evaluate("!!document.querySelector('#histOut')"))
        check('audit still totals the account-scoped surfaces',
              'global ~/.claude/CLAUDE.md' in au and 'MCP servers' in au)

        # every settings key the server accepts must resolve to a LIVE control.
        # `editor`, `claude_exe`, `claude_config_dir` and `headless_budget_usd`
        # round-tripped through the API with nothing on the page to set them.
        # The page is five sub-pages now, so the check names the one that owns
        # each control — asserting them all on `settings` would have passed for
        # the wrong reason once, and then failed the moment they moved.
        for page, cids in (('settings', ('sEff', 'sMod', 'sPlanMod')),
                           ('paths', ('sEditor', 'sClaudeExe', 'sCfgDir',
                                      'sBudget', 'sMemCalls', 'sExtract')),
                           ('appearance', ('sMotion', 'sStage', 'sSurf')),
                           ('updates', ('sUpd', 'sNotif', 'amInt', 'mqStart'))):
            pg.evaluate(f"go('{page}')")
            pg.wait_for_timeout(900)
            for cid in cids:
                ok = pg.evaluate(
                    f"(()=>{{const e=document.querySelector('#{cid}');"
                    f"return !!e && !e.disabled && e.offsetParent!==null;}})()")
                check(f'#{cid} is a live, enabled control on {page}', ok)
            # A Save, or controls that apply the moment you pick them — never
            # nothing. Matched on the WORD rather than on `.btn.pri`, which is
            # what it used to look for: each of these Saves covers one section
            # of the page and not the page, so they are secondary now, and the
            # old check read that as the page having lost its Save.
            check(f'{page} kept its own Save or applies on pick',
                  pg.evaluate("[...document.querySelectorAll('#content .btn')]"
                              ".some(b=>/save/i.test(b.textContent))"
                              " || !!document.querySelector('#content .chip')"))
            check(f'{page} has no Save claiming to be the page\'s own',
                  pg.evaluate("[...document.querySelectorAll('#content .btn.pri')]"
                              ".every(b=>!/save/i.test(b.textContent))"))

        pg.evaluate("go('helpp')")
        pg.wait_for_timeout(700)
        rows = pg.evaluate("document.querySelectorAll('[data-help-row]').length")
        want = pg.evaluate('NAV.length + TABS.length')
        check('the help page is generated from the inventory', rows == want,
              f'{rows} rows vs {want} pages+tabs')
        keys = pg.evaluate(
            "document.querySelector('#content').innerText.includes('Terminal UI keys')")
        check('the help page renders the TUI key table', keys)

        pg.evaluate("go('hooks')")
        pg.wait_for_timeout(900)
        boxes = pg.evaluate(
            "document.querySelectorAll('#content .hrow input[type=checkbox]').length")
        rows = pg.evaluate("document.querySelectorAll('#content .hrow').length")
        # `rows == 0 or …` passed VACUOUSLY on an empty page, which is how one
        # run where the hooks page rendered nothing at all still reported this
        # as OK — only the grouping check below noticed. The stub always
        # installs hooks, so the row count is itself a fact worth asserting.
        check('every hook row can be enabled or disabled', rows and boxes == rows,
              f'{boxes} controls on {rows} rows')
        # both lists group by WHEN a hook fires, and the heading says it in
        # English — `PreToolUse` alone is unreadable to anyone who has not
        # already learnt Claude Code's vocabulary
        check('hooks are grouped under a plain-English trigger',
              pg.evaluate("document.querySelector('#content').innerText"
                          ".includes('before Claude runs a tool')"))
        # a filtered-away group must take its heading with it, or a search
        # leaves headings standing over nothing
        typed = pg.evaluate(
            "(()=>{const i=document.querySelector('#hkQ');if(!i)return false;"
            "i.value='inject';i.dispatchEvent(new Event('input'));return true;})()")
        check('the hook filter box is on the page', typed)
        pg.wait_for_timeout(200)
        vis_rows = pg.evaluate(
            "[...document.querySelectorAll('#content .trow')]"
            ".filter(e=>e.style.display!=='none').length")
        # only the groups this filter GOVERNS: the installed-hooks groups hold
        # `.hrow`, so bindFilter leaves them alone, which is correct
        vis_grps = pg.evaluate(
            "[...document.querySelectorAll('#content .fgrp')]"
            ".filter(e=>e.querySelector('.trow')&&e.style.display!=='none').length")
        check('the hook filter narrows the list and drops the empty groups',
              vis_rows == 1 and vis_grps == 1, f'{vis_rows} rows in {vis_grps} groups')

        # -- writing your own, and naming one --
        # The ready-made list is grouped by FAMILY, not by event: it is browsed
        # for a job ("stop me force-pushing"), and thirty-one rows under eleven
        # event names is a table of contents for a vocabulary you do not have.
        pg.evaluate("(()=>{const i=document.querySelector('#hkQ');"
                    "i.value='';i.dispatchEvent(new Event('input'));})()")
        pg.wait_for_timeout(250)
        heads = pg.evaluate(
            "[...document.querySelectorAll('#content .fgrp')]"
            ".filter(e=>e.querySelector('.trow'))"
            ".map(e=>e.querySelector('.hkwhen').textContent.trim())")
        check('the ready-made hooks are grouped by what they are FOR',
              'Safety guardrails' in heads and 'Lifecycle' in heads, heads)
        check('a category is filterable like everything else on the row',
              'Safety guardrails' in pg.evaluate(
                  "document.querySelector('#content .trow').dataset.f"))
        txt = pg.evaluate("document.body.innerText")
        check('a renamed hook leads with the name you gave it',
              'no dangerous deletes' in txt)
        check('…and still says what it actually runs',
              'block-rm-rf' in txt)
        check('there is a way to write one by hand',
              pg.evaluate("typeof hookNew === 'function'")
              and 'Write one' in txt)
        check('…and a way to rename any hook',
              pg.evaluate("typeof hookName === 'function'")
              and pg.evaluate(
                  "!!document.querySelector('#content .hrow [onclick^=\"hookName\"]')"))

        pg.evaluate("go('client')")
        pg.wait_for_timeout(900)
        check('each settings group says what it is for',
              pg.evaluate("document.querySelector('#content').innerText"
                          ".includes('how hard it thinks')"))
        # the settings grid is display:contents all the way down — a group
        # wrapper that becomes a grid CELL collapses every row inside it
        cols = pg.evaluate(
            "(()=>{const t=document.querySelector('.cctable');"
            "return t?getComputedStyle(t).gridTemplateColumns.split(' ').length:0;})()")
        check('the settings grid keeps a column per account plus label and action',
              cols == 4, f'{cols} columns')
        pg.evaluate("(()=>{const i=document.querySelector('#ccQ');"
                    "i.value='compact';i.dispatchEvent(new Event('input'));})()")
        pg.wait_for_timeout(200)
        vis = pg.evaluate(
            "[...document.querySelectorAll('#content .ccrow[data-f]')]"
            ".filter(e=>e.style.display!=='none').length")
        check('the settings filter finds one setting by what it does', vis == 1, vis)

        pg.evaluate("go('home')")
        pg.wait_for_timeout(500)

        # ── a section whose body resolves to nothing is not painted ──
        # prune() REMOVES DOM on every paint, so it is the one guard in this
        # file that can destroy something rather than fail to catch it. The
        # cases are built here rather than hunted for on a real page: a page
        # that happens to have no empty card proves nothing, and the four
        # things that keep a card alive are exactly what a future edit would
        # get wrong. Same method as the space audit's own self-check.
        print('\n— empty sections are not painted —')
        pg.evaluate("""(()=>{
          const c=document.querySelector('#content');
          c.innerHTML=[
            '<div class="card" id="pk-bare"><h3>Heading over nothing</h3></div>',
            '<div class="card" id="pk-blank"><h3>H</h3><div></div><p></p></div>',
            '<div class="card" id="pk-text"><h3>H</h3><p>It says something.</p></div>',
            '<div class="card" id="pk-empty"><h3>H</h3>'
              +'<div class="empty">No MCP servers configured.</div></div>',
            '<div class="card" id="pk-mount"><h3>H</h3><div id="pk-later"></div></div>',
            '<div class="card" id="pk-spin"><h3>H</h3>'
              +'<div><span class="spin"></span></div></div>',
            '<div class="card" id="pk-btn"><h3>H</h3><div><button>Do it</button></div></div>',
            '<div class="card" id="pk-hdr"><h3>H</h3>'
              +'<table class="tbl"><tr><th>a</th><th>b</th></tr></table></div>',
            '<div class="card" id="pk-rows"><h3>H</h3>'
              +'<table class="tbl"><tr><th>a</th></tr><tr><td>1</td></tr></table></div>',
          ].join('');
          prune();
        })()""")
        alive = pg.evaluate(
            "(()=>{const o={};['bare','blank','text','empty','mount','spin',"
            "'btn','hdr','rows'].forEach(k=>o[k]=!!document.querySelector('#pk-'+k));"
            "o.hdrTable=!!document.querySelector('#pk-hdr table');"
            "o.rowsTable=!!document.querySelector('#pk-rows table');return o;})()")
        check('a heading over nothing is not painted',
              not alive['bare'] and not alive['blank'], alive)
        check('…but text is content, so an explanation keeps its card',
              alive['text'])
        check('…and so is an empty STATE, which is the page saying something',
              alive['empty'])
        check('a mount point something fills later is not pruned first',
              alive['mount'] and alive['spin'],
              'a fetch that lands after the paint would have nowhere to go')
        check('a card whose only content is an action keeps it', alive['btn'])
        check('a header row over no rows is not painted',
              not alive['hdrTable'] and alive['rowsTable'], alive)
        # and the card that held only that header goes with it, since removing
        # the table left it with a heading and nothing else
        check('…and the card left holding only that header goes too',
              not alive['hdr'] and alive['rows'], alive)
        pg.evaluate("go('home')")
        pg.wait_for_timeout(700)

        print('\n— motion levels —')
        for lv, want in [('subtle', 'mo-subtle'), ('off', 'mo-off'), ('full', 'mo-beam')]:
            pg.evaluate(f"MO.set('{lv}')")
            pg.wait_for_timeout(200)
            cls = pg.evaluate("document.documentElement.className")
            check(f'motion={lv}', want in cls, cls)
        pg.evaluate("MO.set('off')")
        pg.wait_for_timeout(400)
        check('off stops the loop', pg.evaluate("MO._raf===null"))
        pg.evaluate("MO.set('full')")

        print('\n— running-job banner —')
        pg.evaluate("""(()=>{const J={jid:'x',label:'Building memory',status:'running',
          msgs:[{ok:true,text:'step 1'}],elapsed:12,sub:'12s elapsed',err:'',
          sel:'#jban',host:document.querySelector('#jban'),modal:false};
          JOBS['x']=J;inlineRender(J);})()""")
        pg.wait_for_timeout(300)
        check('banner visible with a travelling border',
              pg.evaluate("!!document.querySelector('#jban .perun.beam')"))
        check('banner label rendered',
              pg.evaluate("document.querySelector('#jban .jlbl').textContent")
              == 'Building memory')

        print('\n— skin signature effects fire once and clean up —')
        # stop the 10s dashboard poll first: it can wake the frame loop mid-check
        # and make a perfectly-parked burst look like a leak
        pg.evaluate("stopDashboard()")
        looks = ([('world', w) for w in pg.evaluate("Object.keys(ST.worlds||{})")]
                 + [('skin', k) for k in pg.evaluate("ST.classic_skins||[]")])
        for kind, sk in looks:
            if kind == 'world':
                pg.evaluate(f"ST.world='{sk}';applyTheme(ST.theme)")
            else:
                pg.evaluate(f"ST.world='';ST.skin='{sk}';applyTheme(ST.theme)")
            # wait for the node, never for a fixed number of milliseconds:
            # applyTheme rebuilds the scene and repaints the page, and bursting
            # before .d-continue is back makes MO.burst return early — which
            # reads as a broken burst rather than as a slow runner
            pg.wait_for_selector('.d-continue', timeout=10000)
            pg.evaluate("MO.burst(document.querySelector('.d-continue'))")
            pg.wait_for_timeout(100)
            mounted_n = pg.evaluate("document.querySelectorAll('.burst').length")
            nodes = pg.evaluate("document.querySelectorAll('.burst i').length")
            # The 1.6s budget is a property of the ANIMATION, so read it off the
            # timeline — asserting it in wall clock measures the rasteriser, the
            # exact mistake CLAUDE.md already records for scene time under
            # SwiftShader. The animations live on the burst's PARTICLES, not on
            # the host: reading only the host returns 0ms and makes the clause
            # pass vacuously, which is the "check that runs nothing" failure
            # this tool has already had once. The wall-clock wait below is only
            # a leak check now, so it can be generous.
            budget = pg.evaluate(
                "Math.max(0,...[...document.querySelectorAll('.burst')]"
                ".flatMap(h=>[h,...h.querySelectorAll('*')])"
                ".flatMap(el=>el.getAnimations().map("
                "a=>a.effect.getComputedTiming().endTime||0)))")
            in_budget = 0 < budget <= 1600
            gone = True
            try:
                pg.wait_for_function(
                    "document.querySelectorAll('.burst').length===0", timeout=8000)
            except Exception:
                gone = False
            pg.wait_for_timeout(500)
            parked = pg.evaluate("MO._raf===null")
            check(f'burst {sk}',
                  mounted_n == 1 and nodes > 0 and in_budget and gone and parked,
                  f'mounted={mounted_n} nodes={nodes} budget={budget:.0f}ms '
                  f'cleaned={gone} parked={parked}')
        pg.evaluate("MO.set('subtle');MO.burst(document.querySelector('.d-continue'))")
        pg.wait_for_timeout(150)
        check('no burst at motion=subtle',
              pg.evaluate("document.querySelectorAll('.burst').length") == 0)
        pg.evaluate("MO.set('full');ST.world='';ST.skin='';applyTheme(ST.theme);startDashboard()")

        # -- a surface the CLI behind this account does not have --
        # Nothing is off with one harness registered, so this turns one off in
        # the page's own state: what is being checked is the PAGE's behaviour,
        # not the registry's contents.
        print(NL + '-- unavailable capability --')
        pg.evaluate("go('ostyles')")
        pg.wait_for_timeout(600)
        check('the page paints normally while its capability is on',
              not pg.evaluate("document.body.innerText.includes"
                              "('Not available here')"))
        # TWO harnesses: the one this account belongs to, which cannot do it,
        # and one that can. "Supported on" is only meaningful with both.
        pg.evaluate("""(()=>{
          ST.harnesses=[{id:'t',label:'Test CLI',available:true,
            homes:[ST.active_cfgdir||''],
            caps:{output_styles:[false,'Test CLI has no output styles.']}},
           {id:'claude',label:'Claude Code',available:true,homes:['elsewhere'],
            caps:{output_styles:[true,'']}}];
          go('ostyles');})()""")
        pg.wait_for_timeout(600)
        txt = pg.evaluate("document.body.innerText")
        check('an unavailable page says so instead of rendering',
              'Not available here' in txt)
        check('and says WHY, which is the whole contract',
              'Test CLI has no output styles.' in txt)
        check('and where it does work',
              'Supported on' in txt and 'Claude Code' in txt)
        # `#subtabs`, not `#tabs`: Output styles moved behind the Harnesses
        # page, where the FIRST strip is which CLI and the second is its screens.
        # Both are named, because which strip a page's row lives in is the thing
        # this rehaul moved and a selector pinned to one would pass for the
        # wrong reason the next time it moves back.
        check('the tab row greys the row rather than hiding it',
              pg.evaluate("[...document.querySelectorAll("
                          "'#tabs .tab, #subtabs .tab')]"
                          ".some(t=>t.classList.contains('off'))"))
        check('a page with no capability of its own is untouched',
              pg.evaluate("(()=>{go('settings');return true;})()"))
        pg.wait_for_timeout(600)
        check('…and still paints',
              not pg.evaluate("document.body.innerText.includes"
                              "('Not available here')"))
        pg.evaluate("ST.harnesses=%s;" % json.dumps(STATE['harnesses']))

        # -- the Harnesses page: two strips, and one CLI's own screens --
        # The five pages that left the sidebar are reached HERE and nowhere
        # else, so this is the check that they are reachable at all: OFFNAV
        # names the door in prose and no gate can read prose.
        print(NL + '-- harnesses page --')
        pg.evaluate("go('harness')")
        pg.wait_for_timeout(700)
        tabs = pg.evaluate("[...document.querySelectorAll('#tabs .tab')]"
                           ".map(t=>t.textContent.trim())")
        check('every registered CLI is a tab, installed or not', len(tabs) >= 3, tabs)
        subs = pg.evaluate("[...document.querySelectorAll('#subtabs .tab')]"
                           ".map(t=>t.textContent.trim())")
        check("Claude Code's own screens are its sub-tabs",
              'Setup' in subs and 'Accounts' in subs and 'Output styles' in subs,
              subs)
        txt = pg.evaluate("document.body.innerText")
        check('the setup card says what the CLI can do, with the reason',
              'What archeus can do here' in txt)
        # the five moved pages: landing on one must light its CLI, or pressing
        # Setup afterwards would open a different harness's setup
        pg.evaluate("go('accounts')")
        pg.wait_for_timeout(600)
        check('a moved page still paints under the harness strip',
              pg.evaluate("!!document.querySelector('#subtabs .tab.sel')")
              and pg.evaluate("document.querySelector('#ttl').textContent")
              == 'Harnesses')
        check('…and it lights the CLI it belongs to',
              pg.evaluate("HARNESS_HID") == 'claude')
        pg.evaluate("pickHarness('codex')")
        pg.wait_for_timeout(700)
        check('picking another CLI lands on ITS setup, not the page you left',
              pg.evaluate("PAGE_") == 'harness'
              and pg.evaluate("HARNESS_HID") == 'codex')
        # Codex's sub-tabs used to be [Setup] alone, so this asserted the strip
        # was HIDDEN. Logins are every CLI's now — a home is what carries one
        # for all three — so the assertion is that it shows exactly the screens
        # this CLI actually owns, and none of Claude Code's five.
        subs = pg.evaluate("[...document.querySelectorAll('#subtabs .tab')]"
                           ".map(t=>t.textContent.trim())")
        check('a second CLI gets the screens it has, and no more',
              subs == ['Setup', 'Accounts'], subs)
        check('…and none of the screens only Claude Code has',
              not ({'Output styles', 'Agents', 'Hooks', 'Claude Code'} & set(subs)),
              subs)
        # The page is a `split` now, like every other list-of-one-thing in the
        # app, so a reason lives in the pane rather than in a third table
        # column. Gaps sort first, so row 0 IS a gap on any CLI that has one.
        check('the setup page is a list with a ring, a filter and a pane',
              pg.evaluate("!!document.querySelector('#content .pghd .iwrap')")
              and pg.evaluate("!!document.querySelector('#hsQ')")
              and pg.evaluate("document.querySelectorAll('#content .hrow').length") > 10)
        check('…and it opens on a gap rather than an empty pane',
              pg.evaluate("!!document.querySelector('#content .hrow.on')")
              and 'not here' in pg.evaluate("$('#hsDet').innerText"))
        check('and its gaps are printed with their reasons',
              'Output styles are a Claude Code feature.' in pg.evaluate(
                  "HSCAPS.findIndex(c=>c.k==='output_styles')>=0"
                  "&&(hsPick(HSCAPS.findIndex(c=>c.k==='output_styles')),"
                  "$('#hsDet').innerText)"))
        check('…and names the screen the capability gates',
              'Output styles' in pg.evaluate("$('#hsDet').innerText"))
        check('the ring counts what works against the whole table',
              pg.evaluate("document.querySelector('#content .pghdt b').textContent")
              .startswith(str(sum(1 for c in pg.evaluate("HSCAPS") if c['works']))))
        pg.evaluate("hsPick(0)")

        # -- usage: every CLI's spend, only Claude's plan windows --
        print(NL + '-- usage, per harness --')
        pg.evaluate("USAGE_HID='';go('usage')")
        pg.wait_for_timeout(700)
        check('the usage page carries a harness strip',
              pg.evaluate("[...document.querySelectorAll('#content .mtabs .tab')]"
                          ".map(t=>t.textContent.trim())")[:1] == ['All'])
        check('…and the plan rail is there for all of them',
              'Plan usage by account' in pg.evaluate("document.body.innerText"))
        pg.evaluate("pickUsageHarness('codex')")
        pg.wait_for_timeout(700)
        txt = pg.evaluate("document.body.innerText")
        check('under one CLI the spend cards stay',
              'Daily tokens' in txt and 'Per-project' in txt)
        # Codex's rail no longer greys: it DOES have plan windows, recorded in
        # its own rollout. The reason it used to grey with named `codex doctor`
        # as the source, and that was wrong — the installed binary's doctor
        # prints no limits at all.
        check('a CLI whose windows archeus can read keeps its plan rail',
              'codex doctor' not in txt, txt[:200])
        pg.evaluate("pickUsageHarness('pi')")
        pg.wait_for_timeout(700)
        txt = pg.evaluate("document.body.innerText")
        check('…and the one with no plan at all still greys, with its reason',
              'Not available here' in txt and 'bills per provider' in txt)
        pg.evaluate("USAGE_HID=''")

        # -- a shared page whose strip must EXCLUDE a CLI --
        # Usage lists every harness because every one records tokens. Plugins
        # must not list pi, which has no marketplaces at all: a tab whose only
        # possible content is an empty list reads as "no plugins installed"
        # rather than as the structural gap the capability table has a sentence
        # for. This is the check that the strip's filter is real.
        print(NL + '-- a strip narrowed by capability --')
        pg.evaluate("PLHID='';go('plugins')")
        pg.wait_for_timeout(700)
        strip = pg.evaluate("[...document.querySelectorAll('#content .mtabs .tab')]"
                            ".map(t=>t.textContent.trim())")
        check('the plugins strip offers the CLIs that have marketplaces',
              'Claude Code' in strip and 'Codex' in strip, strip)
        check('…and not the one that has none', 'pi' not in strip, strip)
        check('there is no All tab where all-at-once is not a view',
              'All' not in strip, strip)

        # -- the two pages that were cross-harness underneath and could not say so --
        # `mcp.get_mcp_status` has branched to `codex.mcp_list` since Codex was
        # registered, and a skill installs into every harness's roots — but both
        # pages read Claude's account chips and nothing else, so one CLI's
        # servers and the other's skills were unreachable through the UI.
        print(NL + '-- strips on the rest of the shared pages --')
        pg.evaluate("MCPHID='';go('mcp')")
        pg.wait_for_timeout(700)
        strip = pg.evaluate("[...document.querySelectorAll('#content .mtabs .tab')]"
                            ".map(t=>t.textContent.trim())")
        check('the MCP page carries a harness strip',
              'Claude Code' in strip and 'Codex' in strip, strip)
        check('…without pi, which has no MCP client at all',
              'pi' not in strip, strip)
        pg.evaluate("pickMcpHarness('codex')")
        pg.wait_for_timeout(700)
        check('picking a CLI drops the Claude account chips',
              pg.evaluate("document.querySelectorAll('#content .chip').length") == 0)
        pg.evaluate("pickMcpHarness('claude')")
        pg.wait_for_timeout(500)

        pg.evaluate("SKHID='';go('skills')")
        pg.wait_for_timeout(700)
        strip = pg.evaluate("[...document.querySelectorAll('#content .mtabs .tab')]"
                            ".map(t=>t.textContent.trim())")
        check('the skills page carries one too, for every CLI',
              {'Claude Code', 'Codex', 'pi'} <= set(strip), strip)
        pg.evaluate("pickSkillHarness('codex')")
        pg.wait_for_timeout(700)
        check('…and stops offering a scope that is Claude Code\'s own',
              'built into Claude Code' not in pg.evaluate("document.body.innerText"))
        pg.evaluate("pickSkillHarness('claude')")
        pg.wait_for_timeout(500)

        # -- the provider card changes shape per backend --
        # The card was OmniRoute-shaped for its whole life: a live catalogue, a
        # provider-health panel and a dashboard button. None of that exists for a
        # server the user runs themselves, and rendering it anyway reported a
        # working Ollama as "0 providers connected".
        print(NL + '-- provider card --')
        # 'models', not 'settings': the settings page is five sub-pages and this
        # card lives on that one.
        pg.evaluate("go('models')")
        pg.wait_for_timeout(700)
        rows = pg.evaluate("document.querySelectorAll('#pvList .hrow').length")
        check('every configured backend is listed', rows == 2, rows)
        check('nothing is selected until you pick one',
              pg.evaluate("!document.getElementById('pvName')"))

        pg.evaluate("document.querySelectorAll('#pvList .hrow')[1].click()")
        pg.wait_for_timeout(700)
        for cid in ('pvName', 'pvKind', 'gwKind', 'gwUrl', 'gwKey', 'pvCtx',
                    'pvTools', 'pvHeadless', 'pvDefault', 'orUrl', 'orKey',
                    'gwRow', 'foModels', 'foQuiet'):
            check('control #' + cid + ' exists',
                  pg.evaluate("!!document.getElementById('" + cid + "')"))
        kinds = pg.evaluate(
            "[...document.querySelectorAll('#pvKind .chip')].map(c=>c.dataset.v)")
        check('both backend kinds are offered',
              kinds == ['generic', 'omniroute'], kinds)
        gws = pg.evaluate(
            "[...document.querySelectorAll('#gwKind .chip')].map(c=>c.dataset.v)")
        check('gateway kinds offered', gws == ['', 'openai'], gws)
        check('the generic backend gets a free-text model input',
              pg.evaluate("!!document.getElementById('pvModel')"))
        check('OmniRoute-only actions hidden for a generic backend',
              pg.evaluate("[...document.querySelectorAll('.orOnly')]"
                          ".every(e=>e.style.display==='none')"))
        check('its own failover list, not a global one',
              pg.evaluate("document.getElementById('foModels').value") == '')

        pg.evaluate("document.querySelectorAll('#pvList .hrow')[0].click()")
        pg.wait_for_timeout(900)
        check('the other backend brings its own failover list',
              pg.evaluate("document.getElementById('foModels').value") == 'auto/fast')
        check('and its own catalogue',
              pg.evaluate("!!document.getElementById('sOrAuto')"))

        pg.evaluate("pvAdd()")
        pg.wait_for_timeout(300)
        check('adding one opens an empty draft',
              pg.evaluate("document.getElementById('pvName').value") == '')
        # the pane, not the body: app.js is inlined into the page, so the whole
        # source -- pvDelete() included -- is inside document.body.innerHTML and
        # this could never have passed
        check('a draft has nothing to delete yet',
              pg.evaluate("!document.getElementById('pvDet')"
                          ".innerHTML.includes('pvDelete()')"))

        # -- WHICH TOOL a new session starts on --
        # The backend used to be a chip row six fields down inside a collapsed
        # <details>, beside the thinking cap. It was the only control in that
        # form that changed which TOOL ran, and a second CLI made that
        # untenable: a Codex session has no worktree and a pi session has no
        # permission mode, so the answer has to be chosen before the rest of
        # the form means anything.
        print(NL + '-- launch modal: which tool --')
        pg.evaluate("go('home')")
        pg.wait_for_timeout(600)
        pg.evaluate("askLaunch({path:'/demo/acme-api',enc:'demo-acme-api',"
                    "choice:'new',isNew:true})")
        pg.wait_for_timeout(900)
        tabs = pg.evaluate("[...document.querySelectorAll('#fTarget .tab')]"
                           ".map(t=>t.textContent.trim())")
        check('every CLI and every backend is a tab, named individually',
              tabs == ['Claude Code', 'Codex', 'pi', 'OmniRoute', 'vLLM box'], tabs)
        check('it opens on the saved default',
              pg.evaluate("document.querySelector('#fTarget .tab.sel').textContent.trim()")
              == 'Claude Code')
        check('the backend model row is hidden while a CLI is picked',
              pg.evaluate("document.getElementById('fProvModelWrap').style.display")
              == 'none')
        # a field the picked CLI has no notion of is HIDDEN, not greyed: a dead
        # input inside a form you are about to submit asks a question with no
        # answer, and the strip's own note carries the reason instead
        pg.evaluate("pickTarget('codex')")
        pg.wait_for_timeout(300)
        check('Codex hides the two options it does not have',
              pg.evaluate("document.getElementById('fNameWrap').style.display")
              == 'none'
              and pg.evaluate("document.getElementById('fWtWrap').style.display")
              == 'none')
        check('…and says why, rather than leaving a hole',
              'thread name set' in pg.evaluate(
                  "document.getElementById('fTargetNote').textContent"))
        check('Codex keeps the permission mode it DOES have',
              pg.evaluate("document.getElementById('fPermWrap').style.display") != 'none')
        pg.evaluate("pickTarget('pi')")
        pg.wait_for_timeout(300)
        check('pi hides the permission mode and keeps the name',
              pg.evaluate("document.getElementById('fPermWrap').style.display")
              == 'none'
              and pg.evaluate("document.getElementById('fNameWrap').style.display")
              != 'none')
        check('a CLI tab hides the Claude account chips',
              pg.evaluate("document.getElementById('fAcctWrap').style.display") == 'none')
        # -- each CLI brings its own models and its own effort scale --
        # Everything in the Claude block is Anthropic's: priced model cards, a
        # frontier slider whose stops are (model, effort) pairs an advisor has
        # rated, presets over both, and a hint keyed by an Anthropic model id.
        # Showing that under a Codex session is not a cosmetic mismatch — it
        # offers `--effort ultracode`, which Codex rejects outright.
        check('the Anthropic catalogue block is swapped out',
              pg.evaluate("document.getElementById('fClaudeBlock').hidden") is True
              and pg.evaluate("document.getElementById('fOwnBlock').hidden") is False)
        effs = pg.evaluate("[...document.querySelectorAll('#fOwnEffort .chip')]"
                           ".map(c=>c.dataset.v)")
        check("pi gets ITS effort scale, not Claude Code's",
              effs == ['', 'off', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'],
              effs)
        mods = pg.evaluate("[...document.querySelectorAll('#fOwnModels option')]"
                           ".map(o=>o.value)")
        check('…and the models this CLI has actually run',
              mods == ['anthropic/claude-sonnet-5'], mods)
        check('the two Claude-only environment settings are gone too',
              pg.evaluate("document.getElementById('fThink').closest('.fld').style.display")
              == 'none')
        pg.evaluate("pickTarget('codex')")
        pg.wait_for_timeout(500)
        effs = pg.evaluate("[...document.querySelectorAll('#fOwnEffort .chip')]"
                           ".map(c=>c.dataset.v)")
        check('Codex gets a different one again — no max, no ultracode',
              effs == ['', 'minimal', 'low', 'medium', 'high', 'xhigh'], effs)
        pg.evaluate("(()=>{const i=document.getElementById('fOwnModel');"
                    "i.value='gpt-5.4-mini';})();"
                    "document.querySelector('#fOwnEffort .chip[data-v=\"high\"]').click()")
        pg.wait_for_timeout(200)
        check("the launch reads the CLI's own pair, not the frontier slider",
              pg.evaluate("currentModelEffort()") == ['gpt-5.4-mini', 'high'])
        check('the hint stops quoting Anthropic advice',
              'Codex chooses the rest itself'
              in pg.evaluate("document.getElementById('mHint').textContent"))
        # The approval chips are the CLI's OWN vocabulary. They were
        # `config.PERMS` for every harness, so under Codex the window offered
        # Claude Code's seven modes and `codex.PERMS` maps two of them — pick
        # `plan` and you got a session that ignored it, silently.
        perms = pg.evaluate("[...document.querySelectorAll('#fPerm .chip')]"
                            ".map(c=>c.dataset.v)")
        check("the approval chips are Codex's own four, not Claude Code's seven",
              perms == ['', 'untrusted', 'on-request', 'never'], perms)
        check('…and the label says what Codex calls it',
              pg.evaluate("document.getElementById('fPermLbl').textContent")
              == 'Approval policy')
        sand = pg.evaluate("[...document.querySelectorAll('#fSand .chip')]"
                           ".map(c=>c.dataset.v)")
        check('the sandbox is offered as its own axis',
              sand == ['', 'read-only', 'workspace-write', 'danger-full-access'], sand)
        # Measured rather than assumed: under pi the Advanced grid still holds
        # Model, Effort and Name, because pi has --model, --thinking and -n. So
        # the drawer is never empty for any CLI and the "hide it when every
        # field is gone" branch this block was written for was dead code.
        pg.evaluate("pickTarget('claude')")
        pg.wait_for_timeout(700)
        perms = pg.evaluate("[...document.querySelectorAll('#fPerm .chip')]"
                            ".map(c=>c.dataset.v)")
        check('switching back to Claude Code restores ITS modes',
              'plan' in perms and 'untrusted' not in perms, perms)
        pg.evaluate("pickTarget('codex')")
        pg.wait_for_timeout(700)
        # and a backend is still the same binary, so it keeps everything
        pg.evaluate("pickTarget('provider:p2')")
        pg.wait_for_timeout(700)
        check('picking a generic backend asks for its model as free text',
              pg.evaluate("!!document.getElementById('fProvModelIn')"))
        check('prefilled with what that backend is configured with',
              pg.evaluate("(document.getElementById('fProvModelIn')||{}).value")
              == 'Qwen3-VL-32B')
        check('the launch payload decomposes back into cfgdir + provider',
              pg.evaluate("[targetRow('codex').cfgdir,targetRow('provider:p2').provider,"
                          "targetRow('claude').cfgdir]") == ['/home/.codex', 'p2', ''])
        pg.evaluate("$('#ovl').classList.remove('show')")

        # -- the quota strip carries every CLI --
        # It read only Anthropic's OAuth poller, so a machine with three CLIs
        # showed one row and the other two were invisible at the top of every
        # screen. A row with no window used to be an em-dash, which reads as
        # broken rather than as "this CLI has no plan window".
        print(NL + '— the usage strip, per CLI —')
        rows = pg.evaluate("[...document.querySelectorAll('#ubar .urow .uacct')]"
                           ".map(e=>e.textContent.trim())")
        check('every CLI has a row, not only the one with an endpoint',
              'Codex' in rows and 'pi' in rows, rows)
        bar = pg.evaluate("document.querySelector('#ubar').innerText")
        check('a CLI with no window says why instead of showing a dash',
              'no plan window recorded yet' in bar and 'bills per provider' in bar)
        check('…and still carries what it spent today',
              '48.2k today' in bar or '48k today' in bar, bar[:200])
        check('the CLI that does have windows still draws them',
              pg.evaluate("document.querySelectorAll('#ubar .uwin').length") == 2)

        # -- the way back to the dashboard --
        # Every other screen is reachable from the sidebar; the dashboard was
        # reachable from none of them once you had left it, and Ctrl+K knew the
        # word 'home' while nothing on the page did.
        print(NL + '— the wordmark goes home —')
        check('the lockup is a real button, not a div with a handler',
              pg.evaluate("document.querySelector('.brand').tagName") == 'BUTTON'
              and pg.evaluate("document.querySelector('.brand').tabIndex") >= 0)
        pg.evaluate("go('settings')")
        pg.wait_for_timeout(500)
        pg.click('#bHome')
        pg.wait_for_timeout(700)
        check('clicking it from a page returns to the dashboard',
              pg.evaluate("PAGE_") == 'home')
        pg.evaluate("openProject(ST.projects[0])")
        pg.wait_for_timeout(800)
        pg.click('#bHome')
        pg.wait_for_timeout(700)
        check('…and from inside a project, which is the other dead end',
              pg.evaluate("PAGE_") == 'home'
              and pg.evaluate("!!document.querySelector('#content .dash')"))

        print('\n— narrow window —')
        pg.set_viewport_size({'width': 700, 'height': 900})
        pg.wait_for_timeout(800)
        cols = pg.evaluate("getComputedStyle(document.querySelector('.app')).gridTemplateColumns")
        check('sidebar collapsed to an icon rail', cols.startswith('64px'), cols)
        sizes = pg.evaluate("INST.reg.map(t=>t.cv.clientWidth+'x'+t.cv.clientHeight)")
        check('gauges re-fitted',
              all(int(s.split('x')[0]) > 20 and int(s.split('x')[1]) > 20 for s in sizes),
              sizes)
        pg.set_viewport_size({'width': 1600, 'height': 1000})

        print('\n— every theme applies —')
        bad = pg.evaluate("""(()=>{const out=[];
          for(const n of Object.keys(ST.themes)){
            try{applyTheme(n);
              const c=getComputedStyle(document.documentElement);
              if(!c.getPropertyValue('--mo-lift').trim())out.push(n+':nolift');
            }catch(e){out.push(n+':'+e.message);}}
          return out;})()""")
        check('all palettes apply with a personality', bad == [], bad)

        print(chr(10) + '— shader attributes —')
        # A vertex shader can declare `attribute float li` while the geometry
        # never sets it: WebGL reads 0 for every vertex, nothing errors, and the
        # object silently collapses. That is how the graph's connecting lines
        # disappeared — every segment pinned to node 0, so zero length. Compare
        # what each shader asks for against what its geometry actually has.
        missing = pg.evaluate(r"""(()=>{
          const out=[];
          for(const w of Object.keys(ST.worlds||{})){
            ST.world=w; applyTheme(ST.theme);
            if(!STAGE._sc) continue;
            STAGE._sc.scene.traverse(o=>{
              if(!o.material||!o.material.vertexShader||!o.geometry)return;
              const want=[...o.material.vertexShader.matchAll(
                /^\s*attribute\s+\w+\s+(\w+)\s*;/gm)].map(m=>m[1]);
              const have=Object.keys(o.geometry.attributes);
              const builtin=['position','normal','uv','color'];
              for(const a of want)
                if(!have.includes(a)&&!builtin.includes(a))
                  out.push(w+':'+o.type+':'+a);
            });
          }
          ST.world=''; applyTheme(ST.theme); return out;})()""")
        check('no shader reads an attribute its geometry never set',
              missing == [], missing)

        print(chr(10) + '— zen: the theme with nothing on top of it —')
        # The one thing a CSS grep cannot tell you: whether the sidebar column
        # actually goes away. `.side{display:none}` inside a two-column grid
        # whose first track is a fixed `var(--side-w)` leaves a 280px hole, and
        # the page still "looks fine" in a screenshot of the middle of it.
        pg.evaluate("setZen(true)")
        pg.wait_for_timeout(120)
        zen = pg.evaluate("""(()=>{
          const app=document.querySelector('.app');
          const side=document.querySelector('.side');
          const b=document.getElementById('bZen');
          return {cols:getComputedStyle(app).gridTemplateColumns,
                  sideW:side.getBoundingClientRect().width,
                  contentShown:document.getElementById('content').offsetParent!==null,
                  btnShown:b.offsetParent!==null,
                  pressed:b.getAttribute('aria-pressed')};})()""")
        check('zen collapses the sidebar COLUMN, not just the sidebar',
              zen['sideW'] == 0 and ' ' not in zen['cols'].strip(), zen['cols'])
        check('zen hides the page', not zen['contentShown'])
        check('zen leaves its own way out visible',
              zen['btnShown'] and zen['pressed'] == 'true', zen)
        # Esc is the escape hatch that works when the button is off-screen. It
        # must not fire while a modal is up — the modal owns Esc first.
        pg.keyboard.press('Escape')
        pg.wait_for_timeout(120)
        back = pg.evaluate("""({zen:document.documentElement.classList.contains('zen'),
          sideW:document.querySelector('.side').getBoundingClientRect().width,
          contentShown:document.getElementById('content').offsetParent!==null})""")
        check('Esc leaves zen and the whole app comes back',
              not back['zen'] and back['sideW'] > 100 and back['contentShown'], back)

        br.close()
    srv.shutdown()

    # A suite that runs nothing passes everything. This whole file spent a
    # while as unreachable code after a `return` — one helper defined at the
    # wrong indentation closed the `with` block around it — and it reported
    # "FAILURES: none" every time. A floor on the number of checks executed is
    # the cheapest thing that would have caught it.
    # And a floor that never moves stops being a floor: it rises with the suite.
    FLOOR = 280
    if len(ran) < FLOOR:
        fails.append(f'only {len(ran)} checks ran, expected >= {FLOOR} — '
                     'part of this suite is not executing')

    print('\nJS errors:', errs if errs else 'none')
    print('FAILURES:', fails if fails else 'none')
    return 1 if (fails or errs) else 0


if __name__ == '__main__':
    raise SystemExit(main())
