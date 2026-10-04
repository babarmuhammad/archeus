"""The `archeus gui` window in real QtWebEngine against a real Core
(p19-design-gate B8; testing-strategy §8 T5, its Qt half): the page lives in a
named persistent profile under `<ARCHEUS_HOME>/QtWebEngine/`, so a choice made
in one run is the page's in the next; the pre-load background is the OS
scheme's token; the tray offers Open, Pause all, Emergency stop and Quit, each
reaching the shell's own action, the Emergency stop only through a confirmation
whose default is Cancel (R13-01); the icon carries the attention colour only
while Attention's count is non-zero; closing the window hides it to the tray.

Each run is its own process (a restart is a new process), offscreen. Needs
PyQt6-WebEngine, which the CI client job does not install: without it the test
skips even under ARCHEUS_E2E. Mutation-verified by tools/mutate_p19.py."""

import json
import os
import subprocess
import sys
import time

import pytest

from archeus.cli import gui
from archeus.core import engine, ports, runtime
from v1.judge.http import TempCore

from .conftest import INDEX, need

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
CHILD = r'''
import json, sys
sys.path.insert(0, %(root)r)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
from archeus.cli import gui
from claude_sessions import gui_qt

mode, out_path = sys.argv[1], sys.argv[2]
calls, out = [], {}


class Spy(gui.Shell):
    def pause_all(self):
        calls.append('pause_all')
        return super().pause_all()

    def attention(self):
        n = super().attention()
        calls.append(['attention', n])
        return n

    @staticmethod
    def estop():
        calls.append('estop')
        return gui.estop()


shell, why = gui.attach(start=lambda: 'the test starts no Core')
assert why is None, why
shell.__class__ = Spy
LOOK = """(() => ({theme: document.documentElement.dataset.theme,
                 contrast: document.documentElement.dataset.contrast,
                 stored: localStorage.getItem('archeus-appearance'),
                 at: location.href}))()"""
SET = "localStorage.setItem('archeus-appearance', JSON.stringify({theme: 'dark', contrast: 'high'}))"


def ready(view, app):
    from PyQt6.QtCore import Qt
    page = view.page()
    prof = page.profile()
    out.update(off_the_record=prof.isOffTheRecord(), storage=prof.persistentStoragePath(),
               dark=app.styleHints().colorScheme() == Qt.ColorScheme.Dark,
               preload=page.backgroundColor().name())
    tray = app.findChildren(QSystemTrayIcon)[0]
    menu = tray.contextMenu()
    acts = {a.text(): a for a in menu.actions()}
    out['menu'] = list(acts)

    def pixel():
        return tray.icon().pixmap(32, 32).toImage().pixelColor(24, 24).name()

    def finish(looked):
        out['look'] = looked
        menu.aboutToShow.emit()                  # the menu opens: Attention is read
        out['icon_on_open'] = pixel()
        if mode == 'first':
            acts['Pause all'].trigger()
            page.runJavaScript(SET)
        else:
            win = view.window()
            win.close()                          # hides to the tray, reads Attention
            out['visible_after_close'] = win.isVisible()
            out['icon_on_hide'] = pixel()
            def answer(how):
                box = QApplication.activeModalWidget()
                out.setdefault('asked', []).append(
                    [box.windowTitle(), box.text(), box.defaultButton().text(),
                     [b.text() for b in box.buttons()]])
                if how == 'enter':                   # Enter takes the default
                    QTest.keyClick(box, Qt.Key.Key_Return)
                else:
                    next(b for b in box.buttons() if b.text() == 'Emergency stop').click()
            QTimer.singleShot(100, lambda: answer('enter'))
            acts['Emergency stop'].trigger()     # returns once the box is answered
            out['calls_after_enter'] = list(calls)
            QTimer.singleShot(100, lambda: answer('confirm'))
            acts['Emergency stop'].trigger()
        out['calls'] = list(calls)
        QTimer.singleShot(800, acts['Quit'].trigger)

    def poll():
        page.runJavaScript(LOOK, lambda v: finish(v) if v and v['theme'] and
                           'launch=' not in v['at'] else QTimer.singleShot(100, poll))
    poll()


out['rc'] = gui_qt.run_v1(shell, on_ready=ready)
with open(out_path, 'w') as f:
    json.dump(out, f)
'''


def _run(home, mode, tmp_path):
    out = os.path.join(str(tmp_path), 'qt-%s.json' % mode)
    env = dict(os.environ, ARCHEUS_HOME=str(home), QT_QPA_PLATFORM='offscreen')
    p = subprocess.run([sys.executable, '-c', CHILD % {'root': ROOT}, mode, out], env=env,
                       capture_output=True, text=True, timeout=180)
    assert os.path.exists(out), 'the Qt shell did not finish (%s):\n%s' % (
        p.returncode, p.stderr[-3000:])
    with open(out) as f:
        return json.load(f)


def test_the_window_keeps_its_profile_across_a_restart_and_the_tray_acts(archeus_home, tmp_path):
    try:
        import PyQt6.QtWebEngineWidgets  # noqa: F401
    except ImportError:
        pytest.skip('PyQt6-WebEngine is not installed')
    need(os.path.isfile(INDEX), 'the SPA is not built: npm ci && npm run build in clients/app')
    deploy = dict(engine.SKELETON_PLAN, tasks=[dict(engine.SKELETON_PLAN['tasks'][0],
                                                    action_classes=['deploy'])])
    tc = TempCore(archeus_home, ports=runtime.Ports(brain=ports.FixedPlanBrain(deploy))).start()
    try:
        first = _run(archeus_home, 'first', tmp_path)
        assert first['rc'] == 0
        assert first['off_the_record'] is False
        assert os.path.normcase(first['storage']) == os.path.normcase(gui.profile_dir())
        assert first['preload'] == gui.preload_bg(first['dark']).lower()
        assert first['menu'] == ['Open', 'Pause all', 'Emergency stop', 'Quit']
        assert first['look']['stored'] is None                    # nothing chosen yet
        assert first['icon_on_open'] != gui.attention_colour(first['dark']).lower()
        assert first['calls'] == [['attention', 0], 'pause_all']

        r = tc.http('POST', '/v1/missions', body={'title': 'Needs a person', 'objective': 'o',
                                                  'idempotency_key': 'qt-%f' % time.time()})
        mid, deadline = r.json()['id'], time.monotonic() + 30
        while tc.http('GET', '/v1/missions/' + mid).json()['state'] != 'APPROVAL_REQUIRED':
            assert time.monotonic() < deadline, 'the mission never asked'
            time.sleep(0.05)

        second = _run(archeus_home, 'second', tmp_path)               # the restart
        assert second['rc'] == 0
        assert json.loads(second['look']['stored']) == {'theme': 'dark', 'contrast': 'high'}
        assert (second['look']['theme'], second['look']['contrast']) == ('dark', 'high')
        attention = gui.attention_colour(second['dark']).lower()
        assert second['icon_on_open'] == attention == second['icon_on_hide']
        assert second['visible_after_close'] is False
        # R13-01: the tray asks first; Enter takes Cancel, only its own button stops
        assert second['calls_after_enter'] == [['attention', 1], ['attention', 1]]
        assert second['calls'] == [['attention', 1], ['attention', 1], 'estop']
        for title, text, default, buttons in second['asked']:
            assert (title, text, default) == ('Emergency stop', gui.ESTOP_CONFIRM, 'Cancel')
            assert sorted(buttons) == ['Cancel', 'Emergency stop']
        assert len(second['asked']) == 2
    finally:
        tc.stop(kill=True)
