"""Regression tests for hostile-audit findings on archeus/cli/gui.py."""

from archeus.cli import gui
from archeus.cli.tui import client


class Own:
    def __init__(self, head):
        self.head = head

    def get(self, path):
        if 'after=' in path:
            raise client.CoreError(410, 'cursor_expired')
        return {'events': []}, self.head


def test_an_expired_cursor_resyncs_to_the_head_instead_of_going_silent():
    shell = gui.Shell({}, Own(head=7))
    assert shell.notices(99) == (7, [])
