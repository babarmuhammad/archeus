from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace

from archeus.core.domain import entities, ids
from archeus.core.execution import checkpoint
from archeus.core.execution.manager import ExecutionManager
from archeus.core.homes import Homes
from archeus.core.sessions import render


def test_checkpoint_artifact_and_prompt_project_before_render(archeus_home, monkeypatch):
    from archeus.infra.artifacts import store
    home = 'C:/T144/Live-only'
    homes = Homes([home], shorts=lambda _: None)
    cp = entities.Checkpoint(id=ids.new_id('checkpoint'), execution_id=ids.new_id('execution'),
        mission_id=ids.new_id('mission'), trigger='failure', objective=home,
        constraints=(home,), success_criteria=(home,),
        open_problems=('read ' + home + '/settings.json',), decisions=('use ' + home,))
    text = render.checkpoint(cp, homes)
    assert 'read its home/settings.json' in text and 'use its home' in text
    assert text.count(home) == 3
    raw = render.checkpoint(cp)
    cp = replace(cp, artifact_sha=store.put(raw.encode('utf-8')))
    assert checkpoint.text_of(cp, homes) == text
    assert store.get(cp.artifact_sha).decode('utf-8') == raw
    assert cp.open_problems == ('read ' + home + '/settings.json',)
    manager = ExecutionManager.__new__(ExecutionManager)
    manager.db = SimpleNamespace(read=lambda: nullcontext(object()))
    manager.registry = object()
    monkeypatch.setattr(checkpoint, 'of_execution', lambda conn, execution: cp)
    monkeypatch.setattr('archeus.core.execution.manager.rows.get', lambda *args: None)
    def live_homes(conn, registry, callers):
        assert registry is manager.registry
        return homes
    monkeypatch.setattr('archeus.core.execution.manager.resources.homes', live_homes)
    prompt, count = manager._continuation(SimpleNamespace(handoff_from=cp.execution_id), 'task\n')
    assert prompt == 'task\n\n' + text + '\n' and count == 1


def test_checkpoint_missing_artifact_stays_unavailable(archeus_home):
    cp = entities.Checkpoint(id=ids.new_id('checkpoint'), execution_id=ids.new_id('execution'),
        mission_id=ids.new_id('mission'), trigger='failure', artifact_sha='0' * 64)
    assert 'unavailable' in checkpoint.text_of(cp, Homes())
