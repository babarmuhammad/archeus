"""G2 — context selection is explainable and provenance-aware."""

from .support import wait_for


def test_every_item_in_a_context_package_has_a_reason_and_a_source(client):
    m = client.create_mission(title='Context', objective='Anything with context')
    pkg = wait_for(lambda: client.get_mission(m['id']).get('context_package'))
    assert pkg['items']
    assert all(i['reason'] and i['source_kind'] for i in pkg['items'])
    assert pkg['budget']['used_tokens'] <= pkg['budget']['limit_tokens']
