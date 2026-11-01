"""T-329: the highest-risk uncovered branches of archeus/cli/tui/screens.py.

Fail-closed and denial paths first: a refused read must be named as refused and
not as still reading (Doc.load), a decided or ineligible approval must offer no
way to decide it (approval_card, chat_approval), a disarmed estop offers no
command, a settled mission's stop card and a stale change card are disabled,
the profile in force cannot be re-set and a retired rule offers no Retire, and
the automations, verification, mission, session, knowledge and execution
surfaces offer commands only where Core's machine is in the state that allows
one. Then the boundaries: PAGE = 50 on Work, the last 100 messages of a thread,
the last 200 events of an execution's output, Attention's limit of 3 on Now,
the last 20 runs of an automation. Then the empty lists, the pairing code's
expiry, the self-revoke signal, and the odd terminal widths 1, 3, 60 and 5000.

The seams are the ones tests/v1/tui/conftest.py uses (the whole transport
behind `app.core`, an injected Style, an injected clock, `size=lambda`,
`stream=False`), but behind the seam sits a scripted dict of answers instead
of a live TempCore: no process, no socket, no thread, nothing OS-specific —
the same bytes answer on Linux and on Windows.
"""

import copy
import datetime

import pytest

from archeus.cli._api import endpoints
from archeus.cli.tui import app as A
from archeus.cli.tui import client as C
from archeus.cli.tui import screens as SC
from archeus.cli.tui.view import Style

NOW_ISO = '2026-10-30T12:00:00Z'
NOW_MS = int(datetime.datetime(2026, 10, 30, 12, 0,
                               tzinfo=datetime.timezone.utc).timestamp() * 1000)
PAGE = 50          # screens.PAGE, kept as a literal so a change here fails loudly


class FakeCore:
    """The scripted Core behind `app.core`: reads answer from a dict, writes
    are recorded. An unscripted path answers (None, None) — the shape
    client.Core.get has while Core holds nothing, which Doc.load shows as
    'Reading…' and never as data."""

    def __init__(self, answers=None):
        self.answers = dict(answers or {})
        self.gets, self.posts = [], []

    def get(self, path):
        self.gets.append(path)
        if path in self.answers:
            v = self.answers[path]
            if isinstance(v, C.CoreError):
                raise v
            return copy.deepcopy(v), 5
        return None, None

    def post(self, path, body):
        self.posts.append((path, copy.deepcopy(body)))
        return {}


def make_app(answers=None, size=(100, 40)):
    core = FakeCore(answers)
    app = A.App(core, Style(False, 'dark', False), size=lambda: size,
                clock=lambda: NOW_MS / 1000.0, stream=False)
    app.signal('stream_open')     # conftest.app_on: the stream is explicit signals
    return app, core


def render(app, fn, *args, width=100, **kw):
    doc = SC.Doc(app, width)
    fn(app, doc, *args, **kw)
    return doc


def lines(doc):
    return [ln['text'] for ln in doc.lines]


def said(doc):
    return '\n'.join(lines(doc))


def all_acts(doc):
    """Screen-level commands (doc.act) and the row-bound ones (doc.add(acts=)))
    together: which list a command sits in is the screen's choice, the key
    handler of app.py reads both."""
    return list(doc.acts) + [a for ln in doc.lines for a in ln['acts']]


def keys(doc):
    return sorted({a['key'] for a in all_acts(doc)})


def act(doc, key):
    got = [a for a in all_acts(doc) if a['key'] == key]
    assert len(got) == 1, 'expected exactly one act %r in %r' % (key, keys(doc))
    return got[0]


def open_rows(doc, kind):
    return [ln for ln in doc.lines
            if ln['target'] and ln['target'][0] == 'open' and ln['target'][1] == kind]


def sync_view(cap='none', principal='p1', client_id='dev-me', origin='local'):
    return {'client': {'id': client_id, 'name': 'Terminal', 'origin': origin,
                       'principal_id': principal,
                       'scopes': ['observe', 'control', 'approve', 'admin'],
                       'capabilities': {'step_up': cap}},
            'core': {'instance': 'core-1'}, 'floor_seq': 0, 'head_seq': 5}


def mission_row(mid='m1', **over):
    m = {'id': mid, 'title': 'Ship it', 'objective': 'It ships', 'state': 'EXECUTING',
         'version': 2, 'updated_at': NOW_ISO, 'created_at': NOW_ISO,
         'success_criteria': [], 'requirements': [], 'resource_preferences': {}}
    m.update(over)
    return m


def approval_row(**over):
    a = {'id': 'ap1', 'kind': 'plan', 'state': 'PENDING', 'eligible': True,
         'eligible_why': None, 'step_up': False,
         'presented': {'scope': 'deploy v2', 'why': 'it touches prod',
                       'consequences': {'approve': 'it runs', 'reject': 'it does not'},
                       'what': [], 'against': {}, 'reusable': None},
         'action_hash': 'f' * 32, 'version': 4, 'expires_at': '2026-10-30T13:00:00Z',
         'decided_by': None, 'decided_at': None}
    a.update(over)
    return a


def attention_item(kind='automation', state='SUSPENDED', iid='a1', **over):
    i = {'kind': kind, 'state': state, 'ref': {'kind': kind, 'id': iid}, 'since': NOW_ISO}
    i.update(over)
    return i


# ── Doc.load: a refusal is a refusal, never a pending read ──────────────────

def test_load_shows_a_refusal_as_a_refusal_not_as_still_reading():
    # screens.py:110-115: data None WITH an error must render Core's refusal in
    # words; the reading hint (116) is only for data None without one.
    app, core = make_app({endpoints.health(): C.CoreError(403, 'scope_required',
                                                          {'scope': 'admin'})})
    doc = SC.Doc(app, 100)
    assert doc.load(endpoints.health(), 'the health') is None
    t = said(doc)
    assert 'The health is unavailable: ' in t
    assert 'This client does not hold the \u201cadmin\u201d scope.' in t
    assert 'Reading' not in t          # a hard error must not look like a pending read


def test_load_with_no_answer_yet_says_reading():
    # screens.py:116: data None WITHOUT an error is the 'Reading…' hint, so the
    # first paint of a slow read is visibly not an answer.
    app, core = make_app()
    doc = SC.Doc(app, 100)
    assert doc.load(endpoints.health(), 'the health') is None
    assert said(doc).strip().endswith('Reading the health\u2026')
    app2, _ = make_app({endpoints.health(): {'core': {'version': '1'}}})
    doc2 = SC.Doc(app2, 100)
    assert doc2.load(endpoints.health(), 'the health') == {'core': {'version': '1'}}
    assert lines(doc2) == []


# ── Attention's approval: no way to decide what cannot be decided ───────────

def test_approval_card_a_decided_plan_offers_no_way_to_decide():
    # screens.py:637-639 (state != PENDING -> the closed reason), 651/656 (both
    # decisions carry it as `disabled`), 659 (Request changes only while PENDING).
    a = approval_row(state='EXPIRED', decided_by='p-other', decided_at=NOW_ISO)
    app, core = make_app({endpoints.get_approval('ap1'): a, endpoints.sync(): sync_view()})
    doc = render(app, SC.approval_card, 'ap1')
    assert keys(doc) == ['A', 'R']                      # no 'C' although kind == plan
    assert act(doc, 'A')['disabled'] == 'This approval is expired.'
    assert act(doc, 'R')['disabled'] == 'This approval is expired.'
    assert 'on another client' in said(doc)             # screens.py:684-687


def test_approval_card_pending_not_eligible_is_disabled_with_the_reason():
    # screens.py:637-639 eligible False -> 'Not decidable now: <why>'; 661-662
    # request-changes exists but is itself disabled while not eligible.
    a = approval_row(eligible=False, eligible_why='core is draining')
    app, core = make_app({endpoints.get_approval('ap1'): a, endpoints.sync(): sync_view()})
    doc = render(app, SC.approval_card, 'ap1')
    assert keys(doc) == ['A', 'C', 'R']
    why = 'Not decidable now: core is draining.'
    assert act(doc, 'A')['disabled'] == why and act(doc, 'R')['disabled'] == why
    assert act(doc, 'C')['disabled'] == 'Not decidable now.'
    # the reason travels on the commands alone; the screen repeats nothing
    assert said(doc).count('core is draining.') == 0


def test_approval_card_step_up_without_a_pin_denies_only_the_approve():
    # screens.py:635-636: step_up with capability 'none' -> `cannot` is Core's
    # denial of approving only; rejecting must stay enabled (655: reject is
    # disabled by not_eligible alone).
    a = approval_row(kind='action', step_up=True)
    app, core = make_app({endpoints.get_approval('ap1'): a,
                          endpoints.sync(): sync_view(cap='none')})
    doc = render(app, SC.approval_card, 'ap1')
    assert keys(doc) == ['A', 'R']
    assert act(doc, 'A')['disabled'] == ('This client has no PIN: it cannot satisfy '
                                         'a step-up.')
    assert act(doc, 'R')['disabled'] is None


def test_approval_card_step_up_with_a_pin_asks_it_and_sends_it():
    # screens.py:646 (needs_pin adds the field) and 648-650 (decide echoes
    # action_hash and expected_version, and forwards only filled extras).
    a = approval_row(step_up=True)
    app, core = make_app({endpoints.get_approval('ap1'): a,
                          endpoints.sync(): sync_view(cap='pin')})
    doc = render(app, SC.approval_card, 'ap1')
    approve = act(doc, 'A')
    assert [f[0] for f in approve['fields']] == ['step_up']
    assert approve['disabled'] is None
    approve['run']('key-1', {'step_up': '1234'})
    assert core.posts[-1] == (endpoints.decide_approval('ap1'), {
        'decision': 'approve', 'action_hash': a['action_hash'],
        'expected_version': a['version'], 'idempotency_key': 'key-1', 'step_up': '1234'})


def test_chat_approval_whose_row_is_gone_shows_a_line_and_no_commands():
    # screens.py:412-415: an approval card in the thread whose row Core no
    # longer has is named, and offers nothing (a dead link, not a live button).
    app, core = make_app()
    doc = render(app, SC.card, {'id': 'msg1'}, 0,
                 {'ref': {'kind': 'approval', 'id': 'ap9'}, 'type': 'approval'})
    assert '[approval] approval ap9' in said(doc)
    assert all_acts(doc) == []


def test_chat_approval_already_decided_is_disabled_with_the_reason():
    # screens.py:418 ('This approval is %s.') and 437/440 (both Acts carry it).
    a = approval_row(kind='action', state='APPROVED')
    app, core = make_app({endpoints.get_approval('ap1'): a, endpoints.sync(): sync_view()})
    doc = render(app, SC.card, {'id': 'msg1'}, 0,
                 {'ref': {'kind': 'approval', 'id': 'ap1'}, 'type': 'approval'})
    assert keys(doc) == ['A', 'R']
    assert act(doc, 'A')['disabled'] == 'This approval is approved.'
    assert act(doc, 'R')['disabled'] == 'This approval is approved.'
    assert act(doc, 'A')['ident'] == 'card:msg1:0:a'


# ── the thread's own cards ───────────────────────────────────────────────────

def test_estop_card_disarmed_offers_no_command():
    # screens.py:340-341: armed False -> no Act at all; 346-348 says engaged.
    app, core = make_app({endpoints.status(): {'armed': False}})
    doc = render(app, SC.card, {'id': 'msg1'}, 0,
                 {'ref': {'kind': 'intent', 'id': 'i1'}, 'type': 'estop'})
    assert all_acts(doc) == []
    assert 'The emergency stop is engaged.' in said(doc)


def test_estop_card_with_no_status_answer_still_offers_the_stop():
    # screens.py:340: `or {}` then .get('armed', True) — no status yet is armed,
    # so the safety command is never lost to a cold read.
    app, core = make_app()
    doc = render(app, SC.card, {'id': 'msg1'}, 0,
                 {'ref': {'kind': 'intent', 'id': 'i1'}, 'type': 'estop'})
    assert keys(doc) == ['E']
    act(doc, 'E')['run']('key-1', {})
    assert core.posts[-1] == (endpoints.estop(), {'idempotency_key': 'key-1'})


@pytest.mark.parametrize('state,want', [
    ('EXECUTING', None), ('PAUSED', None), ('COMPLETED', 'This mission is completed.'),
], ids=('executing', 'paused', 'settled'))
def test_stop_card_is_disabled_for_a_mission_not_live(state, want):
    # screens.py:353 (live = state in EXECUTING/PAUSED) and 359-360: a settled
    # mission's stop says why in Core's own state word.
    app, core = make_app({endpoints.get_mission('m1'): {'id': 'm1', 'state': state,
                                                        'title': 'Old run'}})
    doc = render(app, SC.card, {'id': 'msg1'}, 0,
                 {'ref': {'kind': 'mission', 'id': 'm1'}, 'type': 'stop'})
    assert len(all_acts(doc)) == 1 and all_acts(doc)[0]['disabled'] == want
    assert 'Stop "Old run"' in said(doc)


def test_stop_card_of_a_mission_with_no_state_says_unknown():
    # screens.py:359-360: str(mi.get('state') or 'unknown').lower() — a row
    # missing its state is settled for this purpose, never offered as live.
    app, core = make_app({endpoints.get_mission('m1'): {'id': 'm1', 'title': 'Odd'}})
    doc = render(app, SC.card, {'id': 'msg1'}, 0,
                 {'ref': {'kind': 'mission', 'id': 'm1'}, 'type': 'stop'})
    assert all_acts(doc)[0]['disabled'] == 'This mission is unknown.'


def test_change_card_is_disabled_when_the_mission_was_reset_since():
    # screens.py:372-373 and 378: a mission-scoped setMissionResources whose
    # `based_on` is not the mission's current `since` is stale: disabled.
    card = {'ref': {'kind': 'mission', 'id': 'm1'}, 'type': 'change', 'scope': 'mission',
            'based_on': 'r1', 'says': 'route to the fast harness',
            'command': {'name': 'setMissionResources', 'id': 'm1',
                        'body': {'preferred_harnesses': ['fast']}}}
    app, core = make_app({endpoints.get_mission('m1'): {'id': 'm1',
                                                        'resource_preferences': {'since': 'r2'}}})
    doc = render(app, SC.card, {'id': 'msg1'}, 0, card)
    assert act(doc, 'P')['disabled'] == 'The mission\u2019s resources were set again since.'


def test_change_card_fresh_sends_core_own_body():
    # screens.py:372-379: not stale -> enabled, and the run posts the command's
    # own body with the idempotency key added (Core's body, never a rebuilt one).
    card = {'ref': {'kind': 'mission', 'id': 'm1'}, 'type': 'change', 'scope': 'mission',
            'based_on': 'r1', 'says': 'route to the fast harness',
            'command': {'name': 'setMissionResources', 'id': 'm1',
                        'body': {'preferred_harnesses': ['fast']}}}
    app, core = make_app({endpoints.get_mission('m1'): {'id': 'm1',
                                                        'resource_preferences': {'since': 'r1'}}})
    doc = render(app, SC.card, {'id': 'msg1'}, 0, card)
    assert act(doc, 'P')['disabled'] is None
    act(doc, 'P')['run']('key-1', {})
    assert core.posts[-1] == (endpoints.set_mission_resources('m1'),
                              {'preferred_harnesses': ['fast'], 'idempotency_key': 'key-1'})


def test_preferences_form_always_sends_all_four_lists_so_a_blank_one_clears_it():
    # G39: the route replaces every list; a blank field must be an explicit [], not a gap
    app, core = make_app()
    doc = render(app, SC.outcome, {'id': 'm1', 'objective': 'o'}, None)
    act(doc, 'F')['run']('k', {'preferred_accounts': 'a, b'})
    assert core.posts[-1] == (endpoints.set_mission_resources('m1'), {
        'idempotency_key': 'k', 'preferred_accounts': ['a', 'b'], 'forbidden_accounts': [],
        'preferred_harnesses': [], 'forbidden_harnesses': [], 'max_cost_band': None})


def test_change_card_policy_branch_posts_the_policy_route():
    # screens.py:384-387: any other command name goes to set_resource_policy
    # (cmd's own id) and is never stale-checked (stale is mission-scope only).
    card = {'ref': {'kind': 'resource', 'id': 'res1'}, 'type': 'change', 'scope': 'resource',
            'based_on': 'anything', 'says': 'raise the ceiling',
            'command': {'name': 'setResourcePolicy', 'id': 'res1', 'body': {'priority': 2}}}
    app, core = make_app()
    doc = render(app, SC.card, {'id': 'msg1'}, 0, card)
    assert act(doc, 'P')['disabled'] is None
    act(doc, 'P')['run']('key-1', {})
    assert core.posts[-1] == (endpoints.set_resource_policy('res1'),
                              {'priority': 2, 'idempotency_key': 'key-1'})


# ── Control / Autonomy ───────────────────────────────────────────────────────

POLICIES = {'user_profile': 'standard', 'policy_version': 'p' * 20,
            'profiles': {n: {'deploy': {'decision': 'deny' if n == 'careful' else 'allow'},
                             'write': {'decision': 'ask'}}
                         for n in ('careful', 'standard', 'autonomous')},
            'rules': [{'id': 'r1', 'scope_level': 'user', 'action_class': 'write',
                       'decision': 'deny', 'locked': True, 'retired_at': None},
                      {'id': 'r2', 'scope_level': 'user', 'action_class': 'deploy',
                       'decision': 'allow', 'locked': False, 'retired_at': '2026-10-01T00:00:00Z'}]}


def test_autonomy_the_profile_in_force_cannot_be_set_and_a_retired_rule_has_no_command():
    # screens.py:773 (the profile already in force is disabled) and 790-798 (a
    # retired rule gets no Retire Act and is marked retired; a locked one is marked).
    app, core = make_app({endpoints.get_policies(): copy.deepcopy(POLICIES)})
    doc = render(app, SC.autonomy)
    by_label = {a['label']: a for a in all_acts(doc)}
    assert by_label['Use standard']['disabled'] == 'This is the profile in force.'
    assert by_label['Use careful']['disabled'] is None
    retires = [a for a in all_acts(doc) if a['label'] == 'Retire']
    assert [a['ident'] for a in retires] == ['retire:r1']
    t = said(doc)
    assert 'retired' in t and 'locked' in t


def test_autonomy_simulation_is_shown_only_after_one_ran_and_promises_nothing():
    # screens.py:789-805: with no stored simulation the screen only hints (805);
    # the Simulate run sends target None for an empty target (793-794) and the
    # answer reaches the screen only through the stored view state (791 keep).
    app, core = make_app({endpoints.get_policies(): copy.deepcopy(POLICIES)})
    doc = render(app, SC.autonomy)
    assert 'The policy would decide' not in said(doc)
    assert '[W] asks the policy about one action; nothing is done.' in said(doc)
    sim = act(doc, 'W')
    sim['run']('key-1', {'class': 'deploy', 'target': ''})
    assert core.posts[-1] == (endpoints.simulate_policy(),
                              {'action': {'class': 'deploy', 'target': None}})
    sim['done']({'decision': 'DENY', 'reason': 'deploy needs you'}, {})
    doc2 = render(app, SC.autonomy)
    t = said(doc2)
    assert 'The policy would decide DENY: deploy needs you (nothing was done)' in t


# ── Control / Automations: the state machine decides the commands ────────────

def automation_row(state='ENABLED'):
    return {'id': 'a1', 'name': 'Nightly tidy', 'state': state, 'version': 3,
            'trigger': {'cron': '0 3 * * *'}, 'template': {'objective': 'tidy'},
            'max_depth': 2, 'rate_limit': 5, 'next_run_at': None, 'waiting': None}


@pytest.mark.parametrize('state,want', [
    ('ENABLED', ['D', 'X']), ('DISABLED', ['E', 'X']), ('DRAFT', ['E']),
    ('SUSPENDED', ['E']), ('ARCHIVED', []), ('PENDING_APPROVAL', []),
], ids=('enabled', 'disabled', 'draft', 'suspended', 'archived', 'awaiting'))
def test_automation_commands_exist_only_where_the_machine_allows_them(state, want):
    # screens.py:835-843: Disable only ENABLED, Enable only DRAFT/DISABLED/
    # SUSPENDED, Archive only ENABLED/DISABLED — an ARCHIVED or awaiting row
    # is offered nothing at all.
    app, core = make_app({endpoints.list_automations(): {'automations': [automation_row(state)]},
                          endpoints.get_automation('a1'): {'runs': []}})
    doc = render(app, SC.automations)
    assert keys(doc) == sorted(want)
    assert 'It has not fired yet.' in said(doc)         # screens.py:857-858


def test_automation_state_change_carries_the_expected_version():
    # screens.py:829-833: the closure binds this automation's own version, so a
    # stale screen cannot disable or archive by luck.
    app, core = make_app({endpoints.list_automations(): {'automations': [automation_row()]},
                          endpoints.get_automation('a1'): {'runs': []}})
    doc = render(app, SC.automations)
    act(doc, 'D')['run']('key-1', {})
    assert core.posts[-1] == (endpoints.set_automation_state('a1'),
                              {'action': 'disable', 'expected_version': 3,
                               'idempotency_key': 'key-1'})


def test_automation_run_history_is_cut_to_the_last_twenty():
    # screens.py:859: list(reversed(runs[-20:])) — 25 runs show 20, newest first.
    runs = [{'id': 'r%d' % i, 'state': 'SUCCEEDED', 'triggering_event_seq': i,
             'depth': 1, 'reason': None} for i in range(25)]
    app, core = make_app({endpoints.list_automations(): {'automations': [automation_row()]},
                          endpoints.get_automation('a1'): {'runs': runs}})
    doc = render(app, SC.automations)
    shown = [x for x in lines(doc) if 'run on event' in x]
    assert len(shown) == 20
    assert 'run on event 24 ' in shown[0] and 'run on event 5 ' in shown[-1]


# ── Attention: verification, the limit of 3, the empty list ──────────────────

@pytest.mark.parametrize('state,human', [('AWAITING_HUMAN', True), ('ERROR', False)],
                         ids=('awaiting', 'broken'))
def test_verification_waits_only_for_a_human(state, human):
    # screens.py:701-720: Accept/Reject exist only while AWAITING_HUMAN; the
    # broken verifier (722-725) explains itself and offers nothing.
    item = attention_item(kind='verification', state=state, iid='v1',
                         reason='verifier crashed', mission_id='m1')
    app, core = make_app({endpoints.attention_items(): {'count': 1, 'items': [item]}})
    doc = render(app, SC.entry, item)
    assert keys(doc) == (['A', 'R'] if human else [])
    if human:
        act(doc, 'A')['run']('key-1', {'note': 'ok'})
        assert core.posts[-1] == (endpoints.decide_verification('v1'),
                                  {'decision': 'accept', 'note': 'ok',
                                   'idempotency_key': 'key-1'})
        assert 'Nothing deterministic could check this' in said(doc)
        assert [ln['target'] for ln in doc.lines
                if ln['target'] and ln['target'][2:3] == ('m1',)] == \
            [('open', 'mission', 'm1', 'evidence')]
    else:
        assert 'The verifier broke (verifier crashed)' in said(doc)


def test_attention_on_now_shows_three_and_offers_the_whole_list():
    # screens.py:590-596: the limit trims to 3, and only when the full list is
    # longer does the 'All N items' row appear (with len, not the shown count).
    items = [attention_item(iid='a%d' % i) for i in range(5)]
    app, core = make_app({endpoints.attention_items(): {'count': 5, 'items': items}})
    doc = render(app, SC.attention_items, limit=3)
    assert all_acts(doc) == []          # an automation entry is a link, not a button
    heads = [ln for ln in doc.lines
             if ln['target'] == ('go', {'view': 'control', 'section': 'automations'})]
    assert len(heads) == 3
    see = [ln for ln in doc.lines if 'All 5 items that wait on you' in ln['text']]
    assert len(see) == 1 and see[0]['target'] == ('go', {'view': 'attention'})


def test_attention_empty_says_nothing_waits():
    # screens.py:591: the empty list is named, and no 'All N' row appears.
    app, core = make_app({endpoints.attention_items(): {'count': 0, 'items': []}})
    doc = render(app, SC.attention_items)
    assert 'Nothing waits on you.' in said(doc)
    assert 'items that wait on you' not in said(doc)


# ── Now: the digest rows, including the new_messages fold ────────────────────

def test_now_digest_new_messages_fold_and_the_dismiss_key():
    # screens.py:259-261: a new_messages group is one row of words with no raw
    # conversation id and target go(now); 256-257: truncated says so; 253-255:
    # Dismiss posts the exact up_to_seq it displayed; 263-266 singular '1 event'.
    digest = {'count': 4, 'up_to_seq': 9, 'truncated': True,
              'groups': [{'ref': {'kind': 'conversation', 'id': 'conv-42'},
                          'headline': 'new_messages', 'count': 3},
                         {'ref': {'kind': 'mission', 'id': 'm1'},
                          'headline': 'completed', 'count': 1}]}
    app, core = make_app({endpoints.list_missions(): {'missions': []},
                          endpoints.attention_items(): {'count': 0, 'items': []},
                          endpoints.digest(): digest,
                          endpoints.get_mission('m1'): {'id': 'm1', 'title': 'Ship it'},
                          endpoints.list_messages('primary'): {'messages': []}})
    doc = render(app, SC.now)
    t = said(doc)
    assert 'Archeus is idle. Nothing needs you.' in t
    assert 'Since you last looked \u00b7 4 changes' in t
    assert 'Some older events are no longer kept' in t
    assert '3 new messages' in t and 'conv-42' not in t
    assert 'Ship it' in t and 'completed \u00b7 1 event' in t
    # screens.py:69-73 (Doc.add): a row whose ref changed since the last read
    # carries the thread's left edge instead of blanks.
    completed = [ln for ln in doc.lines if 'completed \u00b7 1 event' in ln['text']]
    assert completed[0]['text'].startswith('\u2502')
    fold = [ln for ln in doc.lines if '3 new messages' in ln['text']]
    assert fold[0]['target'] == ('go', {'view': 'now'})
    act(doc, 'D')['run']('key-1', {})
    assert core.posts[-1] == (endpoints.ack_digest(), {'up_to_seq': 9})


# ── Work: the group boundary at PAGE and the empty list ──────────────────────

def many_missions(n):
    return [{'id': 'm%02d' % i, 'state': 'EXECUTING', 'title': 'Run %02d' % i,
             'updated_at': NOW_ISO} for i in range(n)]


def test_work_cuts_a_group_at_the_page_and_says_the_remainder():
    # screens.py:466-468: ms[:PAGE] rows, then 'N more not shown' for the rest.
    app, core = make_app({endpoints.list_missions(): {'missions': many_missions(51)}})
    doc = render(app, SC.work)
    assert len(open_rows(doc, 'mission')) == PAGE
    assert '1 more not shown.' in said(doc)
    assert 'Active \u00b7 51' in said(doc)


def test_work_shows_exactly_a_page_without_a_cut_hint():
    # screens.py:467: the hint fires only for len(ms) > PAGE, not for == PAGE.
    app, core = make_app({endpoints.list_missions(): {'missions': many_missions(50)}})
    doc = render(app, SC.work)
    assert len(open_rows(doc, 'mission')) == PAGE
    assert 'more not shown' not in said(doc)


def test_work_names_an_empty_list():
    # screens.py:456-457: the empty list is an instruction, not a blank screen.
    app, core = make_app({endpoints.list_missions(): {'missions': []}})
    doc = render(app, SC.work)
    assert 'No missions yet. Tell Archeus what you want on Now.' in said(doc)
    assert open_rows(doc, 'mission') == []


def test_group_of_trusts_the_machine_not_the_wait():
    # screens.py:440-444: a settled mission waiting-list entry is not 'needs'
    # (line 442), an unknown class falls to 'ended' (444), a plain one its class.
    assert SC.group_of({'id': 'm1', 'state': 'COMPLETED'}, {'m1'}) == 'done'
    assert SC.group_of({'id': 'm1', 'state': 'EXECUTING'}, {'m1'}) == 'needs'
    assert SC.group_of({'id': 'm1', 'state': 'PAUSED'}, set()) == 'paused'
    assert SC.group_of({'id': 'm1', 'state': 'WIDGET'}, set()) == 'ended'


# ── the conversation: the last 100 of a huge thread ──────────────────────────

def test_conversation_shows_the_last_100_and_says_the_rest_are_not_shown():
    # screens.py:291-296: shown = msgs[-100:], the count of the older ones is
    # named, and the oldest of the 150 is not on screen at all.
    msgs = [{'id': 'msg%03d' % i, 'author': 'user', 'text': 'run %03d' % i,
             'created_at': NOW_ISO} for i in range(150)]
    app, core = make_app({endpoints.list_messages('m1'): {'messages': msgs}})
    doc = render(app, SC.conversation, 'm1', 'Thread')
    assert '50 older messages are not shown.' in said(doc)
    assert lines(doc).count('  You  just now') == 100
    assert 'run 000' not in said(doc) and 'run 050' in said(doc)


def test_conversation_empty_names_itself_and_the_message_act_posts_the_text():
    # screens.py:294-295 (empty) and 284-288 (the Message act carries the typed
    # text to Core with the idempotency key, and says 'sent' only as `sent`).
    app, core = make_app({endpoints.list_messages('m1'): {'messages': []}})
    doc = render(app, SC.conversation, 'm1', 'Thread')
    assert 'No messages yet. Tell Archeus what you want: [M] Message.' in said(doc)
    act(doc, 'M')['run']('key-1', {'text': 'do the thing'})
    assert core.posts[-1] == (endpoints.post_message('m1'),
                              {'text': 'do the thing', 'idempotency_key': 'key-1'})


def test_conversation_marks_an_archeus_message_as_ai_generated():
    # screens.py:298-303: '(AI-generated)' rides only on author 'archeus'.
    msgs = [{'id': 'g1', 'author': 'archeus', 'text': 'hello', 'created_at': NOW_ISO}]
    app, core = make_app({endpoints.list_messages('m1'): {'messages': msgs}})
    doc = render(app, SC.conversation, 'm1', 'Thread')
    assert '(AI-generated)' in said(doc) and 'No messages yet' not in said(doc)


# ── the inspectors: commands only where Core's machine allows one ────────────

def test_inspector_of_an_unknown_kind_says_there_is_no_view():
    # screens.py:1077-1080: an unknown kind is named as unviewable and draws
    # nothing else — no invented row, no crash.
    app, core = make_app()
    doc = render(app, SC.inspector, 'widget', 'w1', None)
    assert 'This client has no view of a widget yet.' in said(doc)
    assert all_acts(doc) == [] and doc.lines[-1]['target'] is None


def test_inspector_falls_back_to_the_first_tab():
    # screens.py:1070: a tab the kind does not have becomes tabs[0]; for a
    # knowledge item that is 'detail', so the graph is never read.
    k = {'id': 'k1', 'title': 'Prefer fast', 'state': 'CONFIRMED', 'version': '3',
         'chain': ['k1'], 'text': 'prefer the fast harness', 'type': 'convention'}
    app, core = make_app({endpoints.get_knowledge('k1'): k})
    doc = render(app, SC.inspector, 'knowledge_item', 'k1', 'nonsense-tab')
    assert endpoints.world_graph(focus='knowledge_item:k1', depth=1, limit=1000) \
        not in core.gets
    assert 'Prefer fast' in doc.title


@pytest.mark.parametrize('state,want', [
    ('EXECUTING', ['F', 'P', 'S']), ('BLOCKED', ['F', 'R']),
    ('COMPLETED', ['F']), ('APPROVAL_REQUIRED', ['F']),
], ids=('executing', 'blocked', 'completed', 'awaiting-plan'))
def test_mission_inspector_commands_follow_the_machine(state, want):
    # screens.py:1109-1120: Pause only where 'pause' is a trigger, Resume only
    # for 'resume'/'unblock', Stop only EXECUTING/PAUSED; the routing-preferences
    # act always exists on Outcome.
    app, core = make_app({endpoints.get_mission('m1'): mission_row(state=state),
                          endpoints.get_mission_plan('m1'): None})
    doc = render(app, SC.inspector, 'mission', 'm1', 'outcome')
    assert keys(doc) == want
    if 'P' in want:
        act(doc, 'P')['run']('key-1', {})
        assert core.posts[-1] == (endpoints.pause_mission('m1'),
                                  {'expected_version': 2, 'idempotency_key': 'key-1'})
    if 'S' in want:
        assert isinstance(act(doc, 'S')['confirm'], str)


@pytest.mark.parametrize('state,want', [
    ('RUNNING', ['H', 'S']), ('STARTING', ['S']), ('PAUSING', ['S']),
    ('ENDED_OK', []), ('LOST', []),
], ids=('running', 'starting', 'pausing', 'ended', 'lost'))
def test_execution_inspector_commands_follow_the_machine(state, want):
    # screens.py:1464-1472: Stop for the four live states, Hand off only while
    # RUNNING — an ended attempt offers nothing.
    x = {'id': 'e1', 'attempt': 2, 'state': state, 'mission_id': 'm1',
         'harness_id': 'h1', 'model': 'opus', 'account_id': 'ac1'}
    app, core = make_app({endpoints.get_execution('e1'): x})
    doc = render(app, SC.inspector, 'execution', 'e1', 'relations')
    assert keys(doc) == want
    if 'S' in want:
        assert isinstance(act(doc, 'S')['confirm'], str)
        act(doc, 'S')['run']('key-1', {})
        assert core.posts[-1] == (endpoints.stop_execution('e1'), {'idempotency_key': 'key-1'})
    if 'H' in want:
        act(doc, 'H')['run']('key-1', {})
        assert core.posts[-1] == (endpoints.handoff_execution('e1'), {'idempotency_key': 'key-1'})


def test_execution_output_tails_a_huge_stream_and_jsons_an_odd_event():
    # screens.py:1480-1485: more than TAIL events show as the last TAIL with a
    # saying; an event with no text field is printed as JSON, not crash on KeyError.
    events = [{'type': 'msg', 'text': 'evt-%03d' % i} for i in range(250)]
    events.append({'type': 'weird'})
    app, core = make_app({endpoints.execution_stream('e1'): {'available': True,
                                                             'truncated': False,
                                                             'events': events},
                         endpoints.get_execution('e1'): {'id': 'e1', 'attempt': 1,
                                                         'state': 'ENDED_OK',
                                                         'mission_id': 'm1'}})
    doc = render(app, SC.inspector, 'execution', 'e1', 'output')
    t = said(doc)
    assert 'Showing the last 200 events.' in t
    assert 'evt-050' not in t and 'evt-051' in t   # the last 200 of 251
    assert len([x for x in lines(doc) if x.startswith('  msg  evt-')]) == 199
    assert '"type": "weird"' in t            # json.dumps(ev), screens.py:1484-1485


def test_execution_output_not_available_says_so():
    # screens.py:1476-1479: available False is a reason, not an empty list.
    app, core = make_app({endpoints.execution_stream('e1'): {'available': False,
                                                             'events': []},
                         endpoints.get_execution('e1'): {'id': 'e1', 'attempt': 1,
                                                         'state': 'ENDED_OK',
                                                         'mission_id': 'm1'}})
    doc = render(app, SC.inspector, 'execution', 'e1', 'output')
    assert 'No output yet' in said(doc)


@pytest.mark.parametrize('state,want', [('OPEN', ['C', 'H', 'R']), ('CLOSED', ['H', 'R']),
                                        ('LOST', ['H'])], ids=('open', 'closed', 'lost'))
def test_session_inspector_commands_follow_the_machine(state, want):
    # screens.py:1512-1519: Resume in every state but LOST (a closed session
    # reopens), Close only while OPEN, Hand off always (1520-1527).
    s = {'id': 's1', 'state': state, 'mode': 'chat', 'harness_id': 'h1',
         'account_id': 'ac1', 'lineage': [], 'targets': []}
    app, core = make_app({endpoints.get_session('s1'): s})
    doc = render(app, SC.session_insp, 'session', 's1', 'lineage')
    assert keys(doc) == want
    if 'C' in want:
        act(doc, 'C')['run']('key-1', {})
        assert core.posts[-1] == (endpoints.close_session('s1'), {'idempotency_key': 'key-1'})
    if 'R' in want:
        act(doc, 'R')['run']('key-1', {})
        path, body = core.posts[-1]
        assert path == endpoints.resume_session('s1')
        assert body['deliver_brief'] is True and body['idempotency_key'] == 'key-1'


@pytest.mark.parametrize('state,want', [('CANDIDATE', ['C', 'R']), ('CONFIRMED', ['X']),
                                        ('RETRACTED', []), ('SUPERSEDED', [])],
                         ids=('candidate', 'confirmed', 'retracted', 'superseded'))
def test_knowledge_inspector_commands_follow_the_machine(state, want):
    # screens.py:1591-1604: Confirm/Reject only CANDIDATE, Retract only
    # CONFIRMED; a dead item offers nothing, with the version carried along.
    k = {'id': 'k1', 'title': 'Prefer fast', 'state': state, 'version': '3',
         'chain': ['k1'], 'text': 'prefer the fast harness', 'type': 'convention'}
    app, core = make_app({endpoints.get_knowledge('k1'): k})
    doc = render(app, SC.knowledge_insp, 'knowledge_item', 'k1', 'detail')
    assert keys(doc) == want
    if 'C' in want:
        act(doc, 'C')['run']('key-1', {})
        assert core.posts[-1] == (endpoints.confirm_knowledge('k1'),
                                  {'expected_version': 3, 'idempotency_key': 'key-1'})
    if 'X' in want:
        assert isinstance(act(doc, 'X')['confirm'], str)


# ── Control / Clients: self-revoke, pairing expiry ───────────────────────────

def device_row(did='dev-me', state='ACTIVE'):
    return {'id': did, 'host_label': 'laptop', 'name': did, 'client_type': 'tui',
            'platform': 'linux', 'origin': 'paired', 'state': state,
            'presence': {'state': 'connected', 'connections': 1},
            'scopes': ['observe', 'control'], 'capabilities': {'step_up': 'none'}}


def test_revoking_this_client_is_a_self_revoked_signal_and_nothing_else_is():
    # screens.py:959-962: `done` signals only when the revoked id is this
    # client's; another client's revoke must not sign this one out.
    app, core = make_app({endpoints.list_devices(): {'devices': [device_row('dev-me'),
                                                                 device_row('dev-other')]},
                          endpoints.sync(): sync_view(client_id='dev-me')})
    doc = render(app, SC.devices)
    by_ident = {a['ident']: a for a in all_acts(doc) if a['label'] == 'Revoke'}
    assert sorted(by_ident) == ['revoke:dev-me', 'revoke:dev-other']
    by_ident['revoke:dev-other']['done'](None, {})
    assert app.conn['conn'] == 'live'
    by_ident['revoke:dev-me']['done'](None, {})
    assert app.conn['conn'] == 'revoked'


def test_pairing_code_expiry_drops_the_stored_code():
    # screens.py:1007-1011: once the two minutes are gone the stored code is
    # popped from view state and the screen asks for a new one.
    app, core = make_app({endpoints.list_devices(): {'devices': []},
                          endpoints.sync(): sync_view()})
    app.ui['pairing'] = {'expires_in': 120, 'since': NOW_MS - 121000,
                         'scopes': ['observe', 'control', 'approve'], 'url': 'https://x/pair'}
    doc = render(app, SC.devices)
    assert 'pairing' not in app.ui
    assert '[P] makes a code that works once, for two minutes.' in said(doc)


def test_pairing_code_its_seconds_and_its_two_kinds_of_reach():
    # screens.py:1012-1020: a live code shows its remaining seconds and scopes;
    # with a url it says how to open it, without one it names the missing host.
    app, core = make_app({endpoints.list_devices(): {'devices': []},
                          endpoints.sync(): sync_view()})
    app.ui['pairing'] = {'expires_in': 120, 'since': NOW_MS - 30000,
                         'scopes': ['observe', 'control', 'approve'],
                         'url': 'https://core.example/pair'}
    doc = render(app, SC.devices)
    assert 'Valid for 90 s, once. Scopes: observe, control, approve' in said(doc)
    assert 'https://core.example/pair' in said(doc)
    assert 'The terminal shows no QR code' in said(doc)
    app.ui['pairing'] = {'expires_in': 120, 'since': NOW_MS - 30000,
                         'scopes': ['observe', 'control', 'approve']}
    doc2 = render(app, SC.devices)
    assert 'No remote host is configured' in said(doc2)


def test_a_paired_client_cannot_start_pairing():
    # screens.py:1004-1006: only the local client pairs; a paired one gets the
    # instruction and no [P] act.
    app, core = make_app({endpoints.list_devices(): {'devices': [device_row('dev-x')]},
                          endpoints.sync(): sync_view(origin='paired')})
    doc = render(app, SC.devices)
    assert 'Pairing a new client starts on the computer running Archeus.' in said(doc)
    assert 'P' not in keys(doc)


# ── odd terminal sizes ───────────────────────────────────────────────────────

@pytest.mark.parametrize('width', [1, 3, 60, 5000], ids=('w1', 'w3', 'w60', 'w5000'))
def test_screens_survive_odd_terminal_widths(width):
    # screens.py:106-108 and 116-121 (hint/para wrap to width-2 through
    # view.wrap's max(10, ...) floor) and every row builder: a width of 1 or
    # 5000 changes words, never raises.
    answers = {endpoints.list_missions(): {'missions': many_missions(2)},
               endpoints.attention_items(): {'count': 1, 'items': [attention_item()]},
               endpoints.list_messages('primary'): {
                   'messages': [{'id': 'g1', 'author': 'user',
                                 'text': 'x' * 300, 'created_at': NOW_ISO}]},
               endpoints.get_policies(): copy.deepcopy(POLICIES)}
    for fn in (SC.work, SC.attention, SC.autonomy):
        app, core = make_app(answers, size=(width, 40))
        doc = render(app, fn, width=width)
        assert doc.lines
        assert all(isinstance(ln['text'], str) for ln in doc.lines)
