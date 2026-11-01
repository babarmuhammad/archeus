from archeus.core.application import graph as G


def test_a_label_secret_split_by_an_invisible_character_is_still_redacted():
    out = G.clean_label('fix sk-1234\u200b5678abcd now')
    assert 'sk-1234' not in out and '5678abcd' not in out
    assert '[redacted]' in out


def test_the_two_directions_of_a_relation_are_two_edges():
    a, b = {'kind': 'knowledge_item', 'id': 'k1'}, {'kind': 'knowledge_item', 'id': 'k2'}
    fwd = {'from': a, 'to': b, 'field': 'relations.relates_to'}
    back = {'from': b, 'to': a, 'field': 'relations.relates_to'}
    assert G._edge_key(fwd) != G._edge_key(back)


def test_an_over_cap_file_inside_the_focus_is_never_an_outside_directory():
    payload = {'files': ['app/a.py', 'app/b.py', 'app/c.py', 'lib/x.py'],
               'edges': [['app/a.py', 'app/c.py'], ['app/a.py', 'lib/x.py']]}
    out = G._tree(payload, 'app', 1, 2)
    ends = {n['id'] for n in out['nodes'] if n.get('endpoint')}
    assert ends == {'outside:lib'}
    assert {(e['from']['id'], e['to']['id']) for e in out['edges']} == {
        ('app/a.py', 'outside:lib')}
    assert out['hidden'][0]['count'] == 1
