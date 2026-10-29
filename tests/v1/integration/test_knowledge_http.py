"""P6 over HTTP (p6-design-gate §9, N30–N33): the routes are thin — each runs
one application command or one query — so this checks only what the HTTP layer
adds: shapes, scopes, the default dry run, and that a refused request is a
400 or 404, never a 500."""

from archeus.core import ports, runtime
from archeus.harnesses.fake import FakeCaller
from v1.judge.http import TempCore
from v1.judge.support import FixtureRepo


def _core(archeus_home, callers=()):
    return TempCore(archeus_home, ports=runtime.Ports(
        callers=list(callers), preference=ports.FixedOwnCallPreference())).start()


def test_n30_the_terms_answer_is_admin_and_starts_unknown(archeus_home):
    tc = _core(archeus_home)
    try:
        got = tc.http('GET', '/v1/provider-terms').json()['provider_terms']
        assert {(t['id'], t['headless']) for t in got} == {('claude_code', 'unknown'),
                                                           ('pi', 'unknown')}
        r = tc.http('POST', '/v1/provider-terms/pi', body={'headless': 'permitted',
                                                          'idempotency_key': 't1'})
        assert r.status == 200 and r.json()['provider_terms']['headless'] == 'permitted'
        assert tc.http('POST', '/v1/provider-terms/pi', body={
            'headless': 'perhaps', 'idempotency_key': 't2'}).status == 400
    finally:
        tc.stop()


def test_n31_meeting_import_refuses_what_is_not_a_dated_file(archeus_home, tmp_path):
    tc = _core(archeus_home)
    try:
        undated = tmp_path / 'notes.md'
        undated.write_text('# Sync\n', encoding='utf-8')
        assert tc.http('POST', '/v1/meetings/import', body={
            'path': str(undated), 'idempotency_key': 'm1'}).status == 400
        assert tc.http('POST', '/v1/meetings/import', body={
            'path': str(tmp_path / 'missing.md'), 'idempotency_key': 'm2'}).status == 400
        ok = tc.http('POST', '/v1/meetings/import', body={
            'path': str(undated), 'held_at': '2026-09-01', 'idempotency_key': 'm3'})
        assert ok.status == 200 and ok.json()['meeting']['held_at'] == '2026-09-01'
    finally:
        tc.stop()


def test_n32_the_knowledge_lifecycle_and_forget_over_http(archeus_home, tmp_path):
    fake = FakeCaller('fake', replies={'knowledge_extraction': [{'parsed': {'entities': [
        {'name': 'core', 'kind': 'module', 'summary': 'The domain.'}]}}]})
    tc = _core(archeus_home, [fake])
    try:
        repo = FixtureRepo.create('layered-python', str(tmp_path))
        pid = tc.http('POST', '/v1/projects', body={'name': 'p', 'root_paths': [repo.path],
                                                    'idempotency_key': 'p1'}).json()[
            'project']['id']
        client = tc.client()
        from v1.judge import support
        support.idle = client._idle
        support.wait_for(lambda: client.list_knowledge(project_id=pid, state='CANDIDATE'))
        (item,) = client.list_knowledge(project_id=pid, state='CANDIDATE')
        dry = tc.http('POST', '/v1/knowledge/forget', body={
            'selector': {'ids': [item['id']]}, 'idempotency_key': 'f1'}).json()
        assert dry['dry_run'] and dry['changes'][0]['to'] == 'RETRACTED'
        c = tc.http('POST', '/v1/knowledge/%s/confirm' % item['id'],
                    body={'idempotency_key': 'c1'})
        assert c.status == 200 and c.json()['knowledge_item']['state'] == 'CONFIRMED'
        detail = tc.http('GET', '/v1/knowledge/%s' % item['id']).json()
        assert detail['chain'] == [item['id']]
        rds = tc.http('GET', '/v1/route-decisions?source=%s' % item['source_ref']['id'])
        assert [d['purpose'] for d in rds.json()['route_decisions']] == ['knowledge_extraction']
        assert tc.http('POST', '/v1/knowledge/%s/reject' % item['id'],
                       body={'idempotency_key': 'r1'}).status == 422   # not a CANDIDATE now
        assert tc.http('GET', '/v1/knowledge/kno_01J00000000000000000000000').status == 404
    finally:
        support.idle = None
        tc.stop()


def test_n33_the_cli_lists_and_gives_the_terms_answer(archeus_home, capsys):
    from archeus.cli import main as cli
    assert cli.main(['terms']) == 1                              # no Core: said so
    tc = _core(archeus_home)
    try:
        capsys.readouterr()
        assert cli.main(['terms']) == 0
        assert 'pi             headless unknown   rotation unknown' in capsys.readouterr().out
        assert cli.main(['terms', 'pi', 'permit', '--rotation', 'refuse']) == 0
        assert capsys.readouterr().out.strip() == 'pi: headless permitted, rotation refused'
        assert cli.main(['terms', 'pi', 'maybe']) == 2           # usage, nothing sent
    finally:
        tc.stop()
