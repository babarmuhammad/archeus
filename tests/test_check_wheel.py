"""tools/check_wheel.py refuses every way a wheel can ship the SPA wrong
(p3.5b design gate §10 P2) — checked on synthetic wheels, so the gate is
watched failing without a Node build."""

import importlib.util
import os
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location('check_wheel',
                                              os.path.join(ROOT, 'tools', 'check_wheel.py'))
check_wheel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_wheel)

S = 'archeus/api/static/'
INDEX = ('<!doctype html><script type="module" src="/assets/app-1.js"></script>'
         '<link rel="stylesheet" href="/assets/app-2.css">')
GOOD = {S + 'index.html': INDEX, S + 'assets/app-1.js': 'x', S + 'assets/app-2.css': 'y',
        'archeus/__init__.py': ''}


def _wheel(tmp_path, files):
    p = tmp_path / 'archeus-0-py3-none-any.whl'
    with zipfile.ZipFile(p, 'w') as z:
        for name, body in files.items():
            z.writestr(name, body)
    return str(p)


def test_a_good_wheel_passes(tmp_path):
    assert check_wheel.check_archive(_wheel(tmp_path, GOOD)) == ['app-1.js', 'app-2.css']


@pytest.mark.parametrize('change,why', [
    ({S + 'index.html': None}, 'no archeus/api/static/index.html'),
    ({S + 'assets/app-2.css': None}, 'references assets the wheel lacks'),
    ({S + 'assets/app-1.js.map': '{}'}, 'sources, maps or node_modules'),
    ({'archeus/api/static/src/App.tsx': ''}, 'sources, maps or node_modules'),
    ({'clients/app/node_modules/react/index.js': ''}, 'sources, maps or node_modules'),
    ({'archeus/api/.gitignore': '/static/'}, 'sources, maps or node_modules'),
    ({S + 'index.html': '<link href="/assets/app-2.css">'}, 'references no script'),
    ({S + 'index.html': INDEX + '<script>alert(1)</script>'}, 'inline script'),
])
def test_every_broken_wheel_is_refused(tmp_path, change, why):
    files = dict(GOOD)
    for k, v in change.items():
        if v is None:
            files.pop(k)
        else:
            files[k] = v
    with pytest.raises(AssertionError, match=why):
        check_wheel.check_archive(_wheel(tmp_path, files))


def test_node_is_taken_off_path(tmp_path):
    bin_ = tmp_path / 'nodebin'
    bin_.mkdir()
    (bin_ / ('node.exe' if os.name == 'nt' else 'node')).write_text('')
    env = check_wheel.without_node({'PATH': os.pathsep.join([str(bin_), str(tmp_path)])})
    assert env['PATH'] == str(tmp_path)
