"""Terminal output is an injection boundary (p17-design-gate §10): no string
from Core may reach the terminal able to set its title, write the clipboard,
move the cursor, clear or hide text, reorder it, or forge a prompt. The only
escape sequences a frame may hold are the TUI's own colour codes."""

import re

import pytest

from archeus.cli.tui import screens as SC
from archeus.cli.tui.view import Style, clean, clean_lines
from claude_sessions import render

from .conftest import SGR, app_on, mission, plain, settled
from .test_acceptance import _StubApp

PAYLOADS = {
    'osc title': '\x1b]0;owned\x07',
    'osc clipboard': '\x1b]52;c;cHduZWQ=\x1b\\',
    'osc unterminated': '\x1b]8;;http://evil\x07link',
    'csi erase': '\x1b[2J\x1b[H',
    'csi cursor': '\x1b[10;1H',
    'sgr conceal': '\x1b[8m',
    'dcs': '\x1bPq#0;2;0;0;0\x1b\\',
    'c1 csi': '\x9b2J',
    'c1 osc': '\x9d0;owned\x9c',
    'bare esc': '\x1bc',
    'bell and backspace': '\x07\x08\x08',
    'carriage return': 'fake prompt\r[Y] Approve',
    'bidi override': '\u202eevil\u202c',
    'bidi isolate': '\u2066x\u2069',
}
FOREIGN = re.compile('[\x00-\x08\x0b-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]')


def inert(frame):
    """Nothing but text and the TUI's own SGR colour codes."""
    joined = '\n'.join(frame)
    return not FOREIGN.search(SGR.sub('', joined).replace('\n', ''))


@pytest.mark.parametrize('name', sorted(PAYLOADS))
def test_clean_removes_every_control_sequence(name):
    out = clean('before' + PAYLOADS[name] + 'after')
    assert '\x1b' not in out and not FOREIGN.search(out), (name, out)
    assert out.startswith('before') and out.endswith('after')


def test_clean_keeps_text_and_makes_one_line():
    assert clean('a\tb') == 'a    b'
    assert clean('line one\nline two') == 'line one line two'
    assert clean_lines('one\ntwo') == ['one', 'two']
    assert clean('修复 ✓ ok') == '修复 ✓ ok'


def test_core_text_through_the_styler_is_cleaned_and_our_own_is_not():
    st = Style(True, 'dark', False)
    assert '\x1b]' not in st.t('\x1b]0;x\x07title', 'text')
    assert st.t('\x1b[8mx').count('\x1b') == 0


def test_a_hostile_mission_title_and_objective_reach_no_frame_whole(core):
    bad = ''.join(PAYLOADS.values())
    mid = mission(core, 'Title ' + bad, objective='Objective ' + bad)
    settled(core, mid, 'COMPLETED')
    app = app_on(core, style=Style(True, 'dark', False))
    for route in ({'view': 'now'}, {'view': 'work'},
                  {'view': 'object', 'kind': 'mission', 'id': mid, 'tab': 'outcome'},
                  {'view': 'object', 'kind': 'mission', 'id': mid, 'tab': 'relations'}):
        app.go(route)
        frame = app.frame()
        assert inert(frame), route
    app.go({'view': 'work'})
    assert 'Title' in plain(app), 'the title is shown, only inert'


def _hostile_core():
    """Every kind of Core string the user named, hostile in every screen."""
    bad = ''.join(PAYLOADS.values())
    b = lambda s: s + bad           # noqa: E731
    m = {'id': 'msn_1', 'title': b('mission title'), 'objective': b('objective'),
         'state': 'EXECUTING', 'version': 1, 'updated_at': '2026-09-29T12:00:00Z',
         'project_id': 'prj_1', 'origin': 'conversation', 'context_package_id': 'ctx_1',
         'success_criteria': [{'text': b('criterion'), 'check': b('auto'), 'origin': 'inferred'}],
         'requirements': [{'text': b('req')}], 'resource_preferences': {},
         'context_package': {'id': 'ctx_1', 'as_of_seq': 1,
                             'budget': {'used_tokens': 1, 'limit_tokens': 2},
                             'items': [{'level': 'L0', 'type': b('type'), 'store': b('store'),
                                        'freshness': 'current', 'reason': b('reason'),
                                        'ref': {'kind': 'mission', 'id': 'msn_1'}}],
                             'excluded': [], 'conflicts': []}}
    task = {'id': 'tsk_1', 'key': 't1', 'title': b('task title'), 'kind': 'code_change',
            'state': 'RUNNING', 'depends_on': []}
    plan = {'id': 'pln_1', 'plan_version': 1, 'state': 'APPROVED', 'in_force': True,
            'current': True, 'summary': b('model-written summary'), 'tasks': [task],
            'waves': [['t1']], 'serialised': [], 'estimated_cost': 'low'}
    execution = {'id': 'exe_1', 'task_id': 'tsk_1', 'mission_id': 'msn_1', 'attempt': 1,
                 'state': 'RUNNING', 'harness_id': b('harness'), 'model': b('model'),
                 'account_id': b('account'), 'stop_reason': b('stop')}
    route = {'id': 'rte_1', 'subject': {'kind': 'task', 'id': 'tsk_1'}, 'purpose': b('purpose'),
             'result': 'blocked', 'explanation': b('routing explanation'),
             'harness_id': 'fake', 'candidates': [{'resource': b('cand'), 'reason': b('no')}]}
    data = {
        '/v1/sync': {'client': {'id': 'dev_1', 'scopes': ['observe', 'control', 'approve',
                                                          'admin'], 'origin': 'local',
                                'capabilities': {'step_up': 'local'}}},
        '/v1/missions': {'missions': [m]}, '/v1/missions/msn_1': m,
        '/v1/missions/msn_1/plan': {'plan': plan, 'versions': [plan]},
        '/v1/attention': {'count': 1, 'items': [
            {'kind': 'mission', 'state': 'PLANNING', 'ref': {'id': 'msn_1'},
             'reason': b('attention reason'), 'since': '2026-09-29T12:00:00Z'},
            {'kind': 'knowledge', 'state': 'CANDIDATE', 'ref': {'id': 'kn_1'},
             'reason': b('remember this'), 'reason_code': b('CODE')}]},
        '/v1/digest': {'count': 1, 'up_to_seq': 3, 'groups': [
            {'ref': {'kind': 'mission', 'id': 'msn_1'}, 'headline': b('headline'), 'count': 1}]},
        '/v1/ideas': {'ideas': [{'id': 'i', 'state': 'CAPTURED', 'title': b('idea')}]},
        '/v1/conversations/primary/messages': {'messages': [
            {'id': 'm1', 'author': 'archeus', 'text': b('model reply'), 'cards': [
                {'type': b('card'), 'ref': {'kind': b('kind'), 'id': b('id')}}]}]},
        '/v1/tasks/tsk_1/executions': {'executions': [execution]},
        '/v1/executions/exe_1': execution,
        '/v1/executions/exe_1/stream': {'available': True, 'truncated': False, 'events': [
            {'type': b('tool'), 'text': b('output tail')}]},
        '/v1/route-decisions?source=msn_1': {'route_decisions': [route]},
        '/v1/route-decisions/rte_1': route,
        '/v1/policy-decisions?mission=msn_1': {'policy_decisions': [
            {'id': 'pd_1', 'stage': b('stage'), 'decision': 'DENY', 'reason': b('policy reason')}]},
        '/v1/sessions?mission=msn_1': {'sessions': [{'id': 'ses_1', 'harness_id': b('h'),
                                                     'mode': b('mode')}]},
        '/v1/sessions/ses_1': {'id': 'ses_1', 'state': 'OPEN', 'harness_id': b('h'),
                               'mode': b('mode')},
        '/v1/knowledge/kn_1': {'id': 'kn_1', 'title': b('knowledge title'), 'text': b('text'),
                               'state': 'CONFIRMED', 'type': 'FACT', 'version': 1, 'chain': [],
                               'relations': [{'src_kind': 'knowledge_item', 'src_id': 'kn_1',
                                              'rel': b('relation label'), 'dst_kind': b('kind'),
                                              'dst_id': b('id'), 'confidence_tier': 'INFERRED'}]},
        '/v1/projects/prj_1': {'id': 'prj_1', 'name': b('project name'),
                               'root_paths': [b('C:\\files\\name')], 'repositories': [
                                   {'id': 'rep_1', 'kind': 'git', 'path': b('file path'),
                                    'architecture_state': 'CURRENT', 'findings': [
                                        {'constraint': b('constraint'), 'status': b('status'),
                                         'reason': b('why'), 'violations': [[b('a'), b('b')]]}]}]},
        '/v1/approvals/apr_1': {
            'id': 'apr_1', 'kind': 'plan', 'state': 'PENDING', 'eligible': True, 'version': 1,
            'mission_id': 'msn_1', 'action_hash': 'h' * 64, 'expires_at': b('never'),
            'presented': {'scope': b('scope'), 'why': b('why it asks'),
                          'what': [{'task': b('t'), 'title': b('title'), 'class': b('deploy'),
                                    'target': b('prod'), 'decision': b('ASK'), 'why': b('w')}],
                          'against': {'mission': {'title': b('m')},
                                      'plan': {'version': 1, 'summary': b('summary'),
                                               'summary_by': b('the planner')}},
                          'consequences': {'approve': b('it runs'), 'reject': b('it stops')},
                          'reusable': b('covers')}},
        '/v1/policies': {'user_profile': b('standard'), 'policy_version': b('v'),
                         'profiles': {b('careful'): {'read': {'decision': b('ALLOW')}}},
                         'rules': [{'id': 'r1', 'scope_level': b('user'),
                                    'action_class': b('exec'), 'decision': b('DENY')}]},
        '/v1/automations': {'automations': [
            {'id': 'aut_1', 'name': b('automation'), 'state': 'ENABLED', 'version': 1,
             'trigger': {'type': b('t')}, 'template': {'title': b('x')}}]},
        '/v1/automations/aut_1': {'runs': [{'id': 'run_1', 'state': 'SUCCEEDED', 'depth': 0,
                                            'reason': b('run reason'),
                                            'triggering_event_seq': 1}]},
        '/v1/harnesses': {'harnesses': [{'id': b('harness'), 'installed': True,
                                         'execution': True, 'calls': False,
                                         'enforcement': b('hook'),
                                         'models': [{'id': b('model')}]}]},
        '/v1/accounts': {'accounts': [{'id': 'acc_1', 'health': 'HEALTHY', 'label': b('label'),
                                       'harness_id': b('h'), 'auth_kind': b('oauth'),
                                       'usage': {'x': b('u')},
                                       'resource_policy': {'priority': 1, 'allocation_pct': 1,
                                                           'reserve_pct': 1,
                                                           'brain_reserve_pct': 1,
                                                           'fallback': b('fb')}}]},
        '/v1/route-decisions': {'route_decisions': [route]},
        '/v1/sessions': {'sessions': [{'id': b('ses'), 'state': 'OPEN', 'mode': b('mode'),
                                       'harness_id': b('h')}]},
        '/v1/sessions/ses_1/brief': {'as_of_seq': 1, 'mission': {'id': 'msn_1',
                                                                   'title': b('t'),
                                                                   'objective': b('o')},
                                     'changes': {'groups': [{'ref': {'kind': b('k'),
                                                                     'id': b('i')},
                                                             'headline': b('h'), 'count': 1}]},
                                     'context': {'missing_information': [b('missing')]}},
        '/v1/devices': {'devices': [{'id': 'dev_1', 'name': b('device'), 'state': 'ACTIVE',
                                     'host_label': b('host'), 'client_type': b('cli'),
                                     'platform': b('tui'), 'origin': 'local',
                                     'scopes': [b('observe')], 'expires_at': None,
                                     'capabilities': {'step_up': b('local')},
                                     'presence': {'state': 'connected', 'connections': 1,
                                                  'last_seen_at': None}}]},
        '/v1/health': {'core': {'version': b('1'), 'schema': b('s'), 'started_at': None},
                       'engine': {'state': b('e'), 'parked': 0},
                       'world': {'state': b('w')}, 'knowledge': {'state': b('k')},
                       'intent': {'state': b('i')}, 'plan': {'state': b('p')},
                       'policy': {'state': b('p')}},
        '/v1/plans/pln_1': plan,
        '/v1/verifications/ver_1': {'id': 'ver_1', 'state': 'FAILED', 'verifier': b('code'),
                                    'revision': b('rev'), 'checks': [
                                        {'name': b('check'), 'result': b('fail'),
                                         'detail': b('detail')}]},
    }
    data['/v1/attention']['items'].append({'kind': 'approval', 'state': 'PENDING',
                                           'ref': {'id': 'apr_1'}})
    data['/v1/sync']['client']['name'] = b('me')
    data['/v1/sync'].update(core={'instance': b('instance')}, floor_seq=0, head_seq=1)
    return _StubApp(data)


def test_every_named_kind_of_core_string_is_inert_on_screen():
    """Titles, model-written text, file names, output tails, routing
    explanations, relationship labels and refusal messages (§10, clarification 11)."""
    app = _hostile_core()
    routes = [{'view': 'now'}, {'view': 'work'}, {'view': 'attention'},
              {'view': 'world', 'project': 'prj_1'}]
    routes += [{'view': 'object', 'kind': 'mission', 'id': 'msn_1', 'tab': t}
               for t in ('outcome', 'plan', 'now', 'why', 'relations')]
    routes += [{'view': 'object', 'kind': 'execution', 'id': 'exe_1', 'tab': 'output'},
               {'view': 'object', 'kind': 'route_decision', 'id': 'rte_1', 'tab': None},
               {'view': 'object', 'kind': 'knowledge_item', 'id': 'kn_1', 'tab': 'detail'},
               {'view': 'object', 'kind': 'knowledge_item', 'id': 'kn_1', 'tab': 'relations'},
               {'view': 'object', 'kind': 'session', 'id': 'ses_1', 'tab': 'brief'},
               {'view': 'object', 'kind': 'plan', 'id': 'pln_1', 'tab': 'detail'},
               {'view': 'object', 'kind': 'verification', 'id': 'ver_1', 'tab': 'detail'},
               {'view': 'object', 'kind': 'approval', 'id': 'apr_1', 'tab': None}]
    routes += [{'view': 'control', 'section': s} for s in ('autonomy', 'automations',
                                                           'resources', 'sessions',
                                                           'devices', 'about')]
    for r in routes:
        app.go(r)
        frame = app.frame()
        assert inert(frame), r
        assert any(render.strip_ansi(x).strip() for x in frame[3:]), ('nothing shown', r)


def test_a_refusal_message_from_core_is_inert_in_the_status_line():
    from archeus.cli.tui import client as C
    app = _hostile_core()
    app.go({'view': 'now'})
    app.frame()
    act = SC.Act('Z', 'Try', 'observe', lambda k, v: (_ for _ in ()).throw(C.CoreError(
        409, 'refused', {'why': 'no \x1b]52;c;cHduZWQ=\x07 \x1b[2J way'})))
    app.execute(act, {})
    assert inert(app.frame())
    assert 'no' in plain(app) and 'way' in plain(app)
