"""S10 — an event triggers an automation: a new model file -> a documentation
mission (SP15, IP-F; p14-design-gate §18). The inspection that finds the file
emits `repository.model_added` (D16); the automation asks for a mission, which
is then the normal loop's. The loop guard is test_s10b_loop_guard.py."""

from .support import wait_for


def test_a_new_model_file_creates_a_documentation_mission(client, rig):
    repo = rig.fixture_repo('layered-python')
    a = client.create_automation(
        name='document new models', project_id=repo.project_id,
        trigger={'type': 'repository.model_added', 'where': {'path': {'not_glob': 'tests/*'}}},
        template={'title': 'Document {payload.path}',
                  'objective': 'Write the documentation for the new model {payload.path}.'})
    client.set_automation_state(a['id'], 'enable')
    repo.commit('add Invoice model', {'billing/models/invoice.py': 'class Invoice: ...\n'})

    def made():
        return [m for m in client.list_missions(project_id=repo.project_id)
                if m['origin'] == 'automation']
    (m,) = wait_for(made)
    assert m['title'] == 'Document billing/models/invoice.py'
    (run,) = client.automation(a['id'])['runs']
    assert run['mission_id'] == m['id'] and run['depth'] == 1
    assert run['rationale']['where']['path']['value'] == 'billing/models/invoice.py'
