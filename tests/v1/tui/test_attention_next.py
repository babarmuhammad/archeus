"""T-1097: one key walks the items that wait on you, in Attention's own order."""

from archeus.cli.tui import app as A
from archeus.cli.tui import client as C
from archeus.cli.tui.view import Style

from .conftest import plain, press


class _Core:
    def __init__(self, items):
        self.items = items

    def get(self, path):
        data = {'/v1/attention': {'items': self.items, 'count': len(self.items)},
                '/v1/sync': {'client': {'scopes': []}}}
        if path in data:
            return data[path], 1
        raise C.CoreError(404, 'not_found')


def _item(kind, rid, reason, since):
    return {'kind': kind, 'ref': {'kind': kind, 'id': rid}, 'state': 'X', 'reason_code': 'x',
            'reason': reason, 'mission_id': None, 'project_id': None, 'since': since}


ITEMS = [_item('mission', 'msn_1', 'first reason', '2026-11-01T10:00:00Z'),
         _item('mission', 'msn_2', 'second reason', '2026-11-02T10:00:00Z'),
         _item('automation', 'aut_1', 'third reason', '2026-11-01T09:00:00Z')]


def _app(items=ITEMS):
    app = A.App(_Core(items), Style(), size=lambda: (100, 9), stream=False)
    app.signal('stream_open')
    return app


def _focused(app):
    return next(x for x in plain(app).splitlines() if x.startswith('›'))


def test_g_opens_the_first_item_then_each_press_moves_on_then_wraps():
    app = _app()
    press(app, 'g')
    assert app.route == {'view': 'attention'} and 'Attention item 1 of 3' in plain(app)
    assert 'Planning asks you' in _focused(app)
    press(app, 'g')
    assert 'Attention item 2 of 3' in plain(app)
    press(app, 'g')
    assert 'Attention item 3 of 3' in plain(app)
    press(app, 'g')
    assert 'Attention item 1 of 3' in plain(app)


def test_g_scrolls_to_a_card_below_the_fold():
    app = _app()
    press(app, 'g', 'g', 'g')
    assert 'Automation suspended' in _focused(app)      # five body rows: only a moved focus shows it


def test_g_with_nothing_waiting_says_so_and_stays_put():
    app = _app([])
    app.go({'view': 'work'})
    press(app, 'g')
    assert app.route == {'view': 'work'} and 'Nothing waits on you.' in plain(app)


def test_g_is_documented_and_collides_with_no_other_key():
    from archeus.cli.tui._tables import DESTINATIONS, TABS
    app = _app()
    press(app, '?')
    assert 'g next item that needs you' in plain(app)
    taken = {d['tui'] for d in DESTINATIONS} | {t['key'] for t in TABS.values()}
    assert 'g' not in taken
    assert {'g', 'j', 'k', '[', ']'} <= set(A.RESERVED)


def test_g_when_core_cannot_be_read_says_so_not_that_nothing_waits():
    class Down(_Core):
        def get(self, path):
            if path == '/v1/attention':
                raise C.CoreError(503, 'unavailable')
            return super().get(path)
    app = A.App(Down([]), Style(), size=lambda: (100, 9), stream=False)
    app.signal('stream_open')
    app.go({'view': 'work'})
    press(app, 'g')
    assert 'Nothing waits on you.' not in plain(app) and app.status[2]
