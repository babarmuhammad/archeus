"""P21 slice F (p21-design-gate D7): Core search over titles, under `observe`."""
from archeus.api import auth
from archeus.core.application import commands
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from v1.judge.http import request


def _put(tx, *, actor, entity):
    tx.insert(entity, actor=actor)
    tx.append(new_event('%s.created' % entity._ID, Ref(entity._ID, entity.id), actor))
    return entity.id


def _seed(tc):
    w = tc.core.db.writer
    put = lambda e: w.execute(_put, {'actor': tc.core.system, 'entity': e})
    for t in ('Ship the Login page', 'Fix billing'):
        assert tc.http('POST', '/v1/missions', body={
            'title': t, 'objective': 'o', 'idempotency_key': t}).status == 200
    put(entities.Project(id=ids.new_id('project'), workspace_id=ids.GLOBAL_WORKSPACE,
                         name='login-service'))
    put(entities.KnowledgeItem(id=ids.new_id('knowledge_item'), workspace_id=ids.GLOBAL_WORKSPACE,
                               type='FACT', title='Login uses OAuth', text='secret body'))


def test_F01_titles_holding_the_needle_case_ignored(tc):
    _seed(tc)
    r = tc.http('GET', '/v1/search?q=LOGIN')
    assert r.status == 200
    got = r.json()
    assert [m['title'] for m in got['missions']] == ['Ship the Login page']
    assert set(got['missions'][0]) == {'id', 'title', 'state', 'version'}
    assert [p['name'] for p in got['projects']] == ['login-service']
    assert got['knowledge'] == [{'id': got['knowledge'][0]['id'], 'title': 'Login uses OAuth'}]
    assert b'secret body' not in r.body                 # titles only, never a body


def test_F02_a_blank_or_long_needle_is_400(tc):
    for q in ('', '%20%20', 'x' * 201):
        r = tc.http('GET', '/v1/search?q=' + q)
        assert (r.status, r.json()['error']) == (400, 'invalid_request'), q


def test_F03_a_client_without_observe_reads_nothing(tc):
    _seed(tc)
    token = auth.new_token()
    tc.core.db.writer.execute(commands.register_device, {
        'actor': tc.core.system, 'name': 'no-observe', 'platform': 'web',
        'token_hash': auth.token_hash(token), 'scopes': ['control']})
    r = tc.http('GET', '/v1/search?q=login', token=token)
    assert (r.status, r.json()) == (403, {'error': 'scope_required', 'detail': {'scope': 'observe'}})
    r = request(tc.base_url, 'GET', '/v1/search?q=login')
    assert r.status == 401 and b'login' not in r.body.lower()
