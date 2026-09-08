import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox, run_flow, ESC

from claude_sessions import connections


def _mkfile(base, rel, content=''):
    p = os.path.join(base, rel.replace('/', os.sep))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(content)
    return p


def _ids(g):
    return {n['id'] for n in g['nodes']}


def _dep_set(g):
    return {(e['source'], e['target']) for e in g['dep_edges']}


def _by_id(g, nid):
    return next(n for n in g['nodes'] if n['id'] == nid)


# ── hierarchy ────────────────────────────────────────────────

def test_hierarchy_nodes_parent_totals(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    _mkfile(actual, 'lib/core.py', 'X=1\n')
    _mkfile(actual, 'lib/util.py', 'Y=2\n')
    _mkfile(actual, 'app/main.py', 'Z=3\n')
    g = connections.build_hierarchy(actual, folder)
    ids = _ids(g)
    assert 'root:' in ids and 'dir:lib' in ids and 'dir:app' in ids
    assert 'file:lib/core.py' in ids and 'file:app/main.py' in ids   # file leaves
    assert _by_id(g, 'dir:lib')['parent'] == 'root:'
    assert _by_id(g, 'file:lib/core.py')['parent'] == 'dir:lib'
    assert _by_id(g, 'dir:lib')['total_files'] == 2
    assert _by_id(g, 'root:')['total_files'] == 3       # whole tree counted


def test_file_dep_python(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    _mkfile(actual, 'lib/__init__.py', '')
    _mkfile(actual, 'lib/core.py', 'X=1\n')
    _mkfile(actual, 'app/main.py', 'from lib import core\n')
    g = connections.build_hierarchy(actual, folder)
    assert ('file:app/main.py', 'file:lib/core.py') in _dep_set(g)


def test_file_dep_csharp(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('cs')
    _mkfile(actual, 'core/A.cs', 'namespace App.Core { class A {} }\n')
    _mkfile(actual, 'web/B.cs', 'using App.Core;\nnamespace App.Web { class B {} }\n')
    g = connections.build_hierarchy(actual, folder)
    assert ('file:web/B.cs', 'file:core/A.cs') in _dep_set(g)


def test_file_dep_cpp(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('cpp')
    _mkfile(actual, 'src/main.cpp', '#include "../inc/util.h"\n')
    _mkfile(actual, 'inc/util.h', '#pragma once\n')
    g = connections.build_hierarchy(actual, folder)
    assert ('file:src/main.cpp', 'file:inc/util.h') in _dep_set(g)


def test_rank_and_top_repos(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    _mkfile(actual, 'big/a.py', 'x=1\n')
    _mkfile(actual, 'big/b.py', 'y=1\n')
    _mkfile(actual, 'small/c.py', 'z=1\n')
    g = connections.build_hierarchy(actual, folder)
    tops = connections.top_repos(g)
    assert tops and tops[0]['label'] == 'big'           # most files first


# ── cache ────────────────────────────────────────────────────

def test_cache_roundtrip(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    _mkfile(actual, 'a/x.py', 'x=1\n')
    g1 = connections.build_hierarchy(actual, folder)
    cache = os.path.join(actual, '.archeus', connections._CACHE_NAME)
    assert os.path.isfile(cache)
    g2 = connections.build_hierarchy(actual, folder)            # served from cache
    assert g2['meta']['signature'] == g1['meta']['signature']
    # adding a file changes the signature → fresh build
    _mkfile(actual, 'a/y.py', 'y=1\n')
    g3 = connections.build_hierarchy(actual, folder)
    assert g3['meta']['signature'] != g1['meta']['signature']
    assert g3['meta']['counts']['files'] == 2


# ── the cage ─────────────────────────────────────────────────

def test_the_cage_really_is_a_geodesic_icosahedron():
    """The cage's faces are DERIVED from adjacency rather than read off a
    hardcoded face list, so a wrong tolerance quietly builds a different solid —
    and a wrong-but-plausible cage is exactly what a string assertion cannot
    see. So run the real JS and count.

    42 vertices, 120 edges, and the degree histogram is the proof it is the
    right subdivision and not merely the right totals: the 12 original vertices
    keep degree 5, the 30 new edge midpoints have degree 6.

    Skips without node. Local runs have it; the pytest CI job does not, which is
    why the shape is also pinned by string in test_stage.py."""
    import json
    import shutil
    import subprocess
    import tempfile

    if not shutil.which('node'):
        import pytest
        pytest.skip('node not available')

    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'claude_sessions', 'connections.py'),
        encoding='utf-8').read()
    js = src[src.index('const PHI=1.6180339887;'):src.index('function drawCluster(')]
    js += """
console.log(JSON.stringify({v: DV.length, e: DE.length,
  unit: DV.every(v => Math.abs(Math.hypot(v[0],v[1],v[2]) - 1) < 1e-9),
  deg: (() => {const d = new Array(DV.length).fill(0);
    for (const [a,b] of DE) {d[a]++; d[b]++;}
    return [Math.min(...d), Math.max(...d), d.filter(x => x === 5).length];})()}));
"""
    fd, path = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(js)
        out = subprocess.run(['node', path], capture_output=True, text=True)
    finally:
        os.remove(path)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert got['v'] == 42 and got['e'] == 120, got
    assert got['unit'], 'a vertex is off the circumsphere'
    assert got['deg'] == [5, 6, 12], got


def test_the_cage_costs_enough_to_lower_the_dot_fallback():
    """120 strokes where the platonic solid was 30, plus a halo pass and an
    interior cloud, and a 2D canvas pays every one of them on the CPU. The
    threshold came down from 250 to 180 for that reason, and the interior is
    drawn only for the nodes big enough for it to read as structure."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'claude_sessions', 'connections.py'),
        encoding='utf-8').read()
    assert 'const dod=VARR.length<=180;' in src, 'the fallback did not come down'
    # gated on APPARENT size, not model radius. `r` is in graph units and the
    # view zooms, so `r >= 12` drew a 120-edge cage plus a 90-point cloud into
    # an 8px disc at low zoom — a solid burr — and skipped both on a hull
    # filling the screen at high zoom. `px` is `r * view.k`, which is the
    # number the decision is actually about.
    assert 'if(px>=44){' in src, 'the interior cloud is not gated on apparent size'
    # ONE gradient per cluster, never one per hull VERTEX. The distinction is
    # the whole cost: 42 vertices across 180 nodes is 7,500
    # createRadialGradient allocations a frame, which is what this rule exists
    # against. The lit centre is one per cluster and it genuinely needs a
    # gradient — a plasma core is white in the middle running out through the
    # cluster's own chord, and three flat discs cannot say that.
    dc = src.split('function drawCluster(')[1].split('function draw()')[0]
    assert dc.count('createRadialGradient(') <= 1, \
        'a gradient allocation per hull vertex'
    # ...and it is outside both vertex loops, which is what makes it one.
    for loop in ('for(const p of P)', 'for(const p of FP)'):
        i = dc.index(loop)
        assert 'createRadialGradient(' not in dc[i:dc.index('}', dc.index('{', i))], loop


# ── HTML ─────────────────────────────────────────────────────

def test_render_html_self_contained(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    _mkfile(actual, 'a/x.py', 'x=1\n')
    html = connections.render_html(connections.build_hierarchy(actual, folder))
    for needle in ('<canvas', 'const CODE', 'id="search"', 'expanded', 'id="fit"', 'drawCluster'):
        assert needle in html, needle
    assert 'http://' not in html and 'https://' not in html
    assert '<script src=' not in html


def test_render_html_escapes_injection(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    _mkfile(actual, 'a/x.py', 'x=1\n')
    g = connections.build_hierarchy(actual, folder)
    g['nodes'].append({'id': 'x', 'label': '</script><b>pwn', 'parent': 'root:',
                       'type': 'dir', 'own_files': 0, 'total_files': 0, 'repo': 'x',
                       'depth': 1, 'rank': 0})
    html = connections.render_html(g)
    assert '<\\/script>' in html
    assert html.count('</script>') == 1


def test_write_and_open(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    _mkfile(actual, 'a/x.py', 'x=1\n')
    g = connections.build_hierarchy(actual, folder)
    p = connections.write_graph_html(g, actual, folder)
    assert p and os.path.isfile(p)
    opened = []
    monkeypatch.setattr(os, 'startfile', lambda x: opened.append(x), raising=False)
    ok, err = connections.open_graph(p)
    assert ok is True and err == '' and opened == [p]


# ── TUI ──────────────────────────────────────────────────────

def test_connections_screen_renders(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    _mkfile(actual, 'a/x.py', 'x=1\n')
    monkeypatch.setattr(os, 'startfile', lambda x: None, raising=False)
    _res, cap, _ = run_flow(monkeypatch, ESC, connections.connections_screen,
                            actual, folder, 'alpha')
    assert 'ARCHITECTURE' in cap.plain
    assert 'Files' in cap.plain


def test_build_output_is_not_indexed(monkeypatch, tmp_path):
    """mkdocs writes `site/` and the walk had no reason to skip it, so build
    output became a memory unit — a paid Claude call and a rule file spent on
    generated JavaScript nobody edits."""
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    _mkfile(actual, 'src/app.py', 'x = 1\n')
    _mkfile(actual, 'site/assets/javascripts/bundle.js', 'var a=1;')
    g = connections.build_hierarchy(actual, folder)
    ids = _ids(g)
    assert 'dir:site' not in ids and not [i for i in ids if i.startswith('file:site/')], \
        'generated build output was indexed'
    assert 'dir:src' in ids
