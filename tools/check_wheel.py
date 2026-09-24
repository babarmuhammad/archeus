"""Check a built wheel carries the V1 SPA, and that the INSTALLED package
serves it with no Node anywhere (p3.5b design gate §9, §18.2, §10 P2).

    py tools/check_wheel.py dist/archeus-X.whl                    # the archive only
    py tools/check_wheel.py dist/archeus-X.whl --python VENV_PY   # and the install

The source tree always has the files, which is why only the built artefact
can prove anything: a package-data glob that matches nothing is silent, and
this repository has shipped an empty directory that way before.
"""

import os
import re
import subprocess
import sys
import tempfile
import zipfile

STATIC = 'archeus/api/static/'
REFS = re.compile(r'(?:src|href)="/assets/([^"]+)"')

RUN = r'''
import json, os, shutil, socket, sys, tempfile, urllib.request
os.environ['ARCHEUS_HOME'] = os.path.join(tempfile.mkdtemp(), 'home')
assert shutil.which('node') is None, 'node is on PATH: the check must run without it'
from archeus.api import server
from archeus.core import runtime
assert 'site-packages' in server.STATIC_DIR, 'not the installed package: ' + server.STATIC_DIR
s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
core = runtime.Core(port=port).start()
try:
    def get(path):
        r = urllib.request.urlopen('http://127.0.0.1:%d%s' % (port, path), timeout=10)
        return r.status, dict(r.headers), r.read()
    status, headers, body = get('/')
    assert status == 200 and b'not built' not in body, 'the installed Core has no SPA'
    assert "script-src 'self'" in headers['Content-Security-Policy']
    for name in json.loads(sys.argv[1]):
        status, headers, data = get('/assets/' + name)
        assert status == 200 and data, name
        if name.endswith('.js'):
            assert headers['Content-Type'].startswith('text/javascript'), headers
    print('the installed Core serves the SPA without Node:', len(json.loads(sys.argv[1])),
          'assets')
finally:
    core.stop()
'''


def check_archive(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        bad = [n for n in names if n.endswith(('.map', '.ts', '.tsx', '/.gitignore'))
               or 'node_modules' in n or n.startswith('clients/')]
        assert not bad, 'the wheel ships sources, maps or node_modules: %s' % bad[:5]
        assert STATIC + 'index.html' in names, 'the wheel has no %sindex.html' % STATIC
        html = z.read(STATIC + 'index.html').decode('utf-8')
    refs = sorted(set(REFS.findall(html)))
    assert any(r.endswith('.js') for r in refs), 'index.html references no script'
    missing = [r for r in refs if STATIC + 'assets/' + r not in names]
    assert not missing, 'index.html references assets the wheel lacks: %s' % missing
    assert not re.search(r'<script\b[^>]*>\s*[^<\s]', html), 'inline script in index.html'
    print('%s: index.html and its %d assets, no maps, sources or node_modules'
          % (os.path.basename(path), len(refs)))
    return refs


def without_node(env):
    keep = [d for d in env.get('PATH', '').split(os.pathsep)
            if d and not any(os.path.isfile(os.path.join(d, n))
                             for n in ('node', 'node.exe', 'npm', 'npm.cmd'))]
    return dict(env, PATH=os.pathsep.join(keep))


def main(argv):
    wheel = argv[0]
    refs = check_archive(wheel)
    if '--python' in argv:
        py = os.path.abspath(argv[argv.index('--python') + 1])    # it runs from elsewhere
        import json
        r = subprocess.run([py, '-c', RUN, json.dumps(refs)], cwd=tempfile.gettempdir(),
                           env=without_node(os.environ), capture_output=True, text=True,
                           timeout=120)
        sys.stdout.write(r.stdout)
        if r.returncode:
            sys.stderr.write(r.stderr)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
