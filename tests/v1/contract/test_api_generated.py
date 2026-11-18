"""The route table is the source of the API reference and the SPA's typed
client (api-and-realtime §1, p3.5b design gate §9, §10 I1–I2). Checked here,
in the Python job, so no Node is needed to know they are stale."""

import importlib.util
import os

import pytest

from archeus.api import routes

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))


def _tool():
    spec = importlib.util.spec_from_file_location(
        'gen_api_docs', os.path.join(ROOT, 'tools', 'gen_api_docs.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize('which', ['render_v1_reference', 'render_v1_client'])
def test_the_generated_files_are_current_and_deterministic(which):
    tool = _tool()
    path = tool.V1_REFERENCE if which == 'render_v1_reference' else tool.V1_CLIENT
    text = getattr(tool, which)()
    assert text == getattr(tool, which)(), 'two runs differ'
    on_disk = open(path, encoding='utf-8').read().replace('\r\n', '\n')
    assert on_disk == text, '%s is stale: run tools/gen_api_docs.py' % os.path.relpath(path, ROOT)


def test_a_route_added_without_regenerating_fails_the_check(monkeypatch):
    tool = _tool()
    extra = routes.Route('GET', '/v1/extra', routes.version, 'observe', None, None, 'Version')
    monkeypatch.setattr(routes, 'ROUTES', routes.ROUTES + (extra,))
    assert '/v1/extra' in tool.render_v1_reference()
    assert 'extra' in tool.render_v1_client()
    assert tool.main(['--check']) == 1


def test_every_route_and_type_reaches_both_outputs():
    tool = _tool()
    ref, ts = tool.render_v1_reference(), tool.render_v1_client()
    for r in routes.ROUTES:
        assert '`%s`' % r.path in ref, r.path
        if r.path.startswith('/v1/') and r.path != routes.STREAM:
            assert '%s: (' % tool._camel(r.handler.__name__) in ts, r.path
    from archeus.api import schemas
    for name in schemas.TYPES:
        assert 'export interface %s ' % name in ts and '### `%s`' % name in ref
