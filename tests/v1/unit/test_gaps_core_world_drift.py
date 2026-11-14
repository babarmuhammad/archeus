"""T-753: the ten highest-risk uncovered branches of archeus/core/world/drift.py.

Fail-closed and denial paths first — the violation list capped at `MAX_LISTED`
while `violation_count` keeps the true size, every constraint that cannot be
checked becoming `unchecked` and never `satisfied`, the `violated()` gate that
`core/application/world.py` turns findings into drift status — then the
boundary values (a pin that is a prefix and not a release, the first
version-like token, files no layer names, imports inside one layer), then the
error paths that must be a reason naming what is missing or moved rather than
a silent pass.

drift.py is a pure function of a payload and constraint dicts and never
touches the OS, so there is no seam to fake: the fixtures are the plain dicts
of the drift section of tests/v1/unit/test_world_units.py (`kno_%026d` ids,
repository-relative ASCII paths, explicit data), no test shells out, nothing
is platform-skipped, and every assertion holds the same on Linux and Windows.
`fnmatchcase` is case-sensitive by contract on both platforms, so the one
near-miss assertion that relies on case does not rely on the OS.
"""

import pytest

from archeus.core.world import drift


def _c(kind, spec, i=1, v=1, statement='do not look both ways'):
    return {'id': 'kno_%026d' % i, 'version': v, 'statement': statement,
            'constraint': None if kind is None else {'kind': kind, 'spec': spec}}


def _payload(files=(), edges=(), dependencies=(), truncated=False):
    return {'files': list(files), 'edges': [list(e) for e in edges],
            'dependencies': [dict(d) for d in dependencies],
            'truncated': truncated}


# ── fail-closed and denial paths ────────────────────────────────────────────

def test_the_violation_list_is_capped_at_twenty_but_the_count_is_not():
    edges = [['src/m%02d.py' % i, 'bad/x%02d.py' % i] for i in range(25)]
    edges += [['other/y.py', 'bad/zz.py'], ['src/ok.py', 'good/g.py']]   # decoys
    (f,) = drift.evaluate(_payload(edges=edges),
                          [_c('forbid_dependency', {'from': 'src/*', 'to': 'bad/*'})])
    assert f['status'] == 'violated'
    assert f['violation_count'] == 25                      # the true size survives
    assert len(f['violations']) == drift.MAX_LISTED == 20  # only the list is capped
    assert f['violations'][0] == ['src/m00.py', 'bad/x00.py']
    assert f['violations'][-1] == ['src/m19.py', 'bad/x19.py']
    assert f['reason'] == '25 import(s) break it'          # the count quoted is the whole
    assert drift.violated([f]) is True


def test_findings_do_not_depend_on_the_edge_order():
    want = [['app/a.py', 'bad/x.py'], ['app/b.py', 'bad/x.py'], ['app/c.py', 'bad/x.py']]
    c = _c('forbid_dependency', {'from': 'app/*', 'to': 'bad/*'})
    (a,) = drift.evaluate(_payload(edges=want), [c])
    (b,) = drift.evaluate(_payload(edges=list(reversed(want))), [c])
    assert a == b                                # the walk's order must not be visible
    assert a['violations'] == [list(e) for e in want]
    assert all(isinstance(v, list) for v in a['violations'])   # plain JSON data
    assert a['reason'] == b['reason'] == '3 import(s) break it'


@pytest.mark.parametrize('kind,spec,reason', [
    (None, None, 'prose: cannot check automatically'),
    ('doc_matches_code', {'doc': 'docs/*.md', 'code': 'app/**'},
     'doc_matches_code: cannot check automatically'),
    ('teleport', {'anything': 1}, 'teleport: cannot check automatically'),
], ids=['prose', 'doc', 'unknown-kind'])
def test_what_cannot_be_checked_is_never_reported_satisfied(kind, spec, reason):
    # even on a broken, truncated graph an undecidable constraint is `unchecked`
    # with a reason, never `satisfied` and never a crash (§6.4: nothing assumed)
    p = _payload(files=['app/gone.py'], edges=[['app/core/m.py', 'app/api/v.py']],
                 truncated=True)
    (f,) = drift.evaluate(p, [_c(kind, spec, statement='keep it clean')])
    assert f['status'] == 'unchecked'
    assert f['reason'] == reason
    assert f['kind'] == kind
    assert f['constraint_id'] == 'kno_%026d' % 1
    assert f['constraint'] == 'keep it clean'
    assert f['violations'] == [] and f['violation_count'] == 0
    assert drift.violated([f]) is False          # unchecked is not drift


def test_one_finding_per_constraint_in_id_order_and_the_violated_gate():
    cs = [_c('doc_matches_code', {'doc': 'd'}, i=3),
          _c('module_exists', {'path': 'app/core/*.py'}, i=1),
          _c(None, None, i=2)]                   # given out of order on purpose
    fs = drift.evaluate(_payload(files=['app/core/models.py']), cs)
    assert [f['constraint_id'] for f in fs] == ['kno_%026d' % i for i in (1, 2, 3)]
    assert [f['status'] for f in fs] == ['satisfied', 'unchecked', 'unchecked']
    assert drift.violated(fs) is False           # satisfied + unchecked is not drift
    fs2 = drift.evaluate(_payload(files=['app/elsewhere/models.py']), cs)
    assert [f['status'] for f in fs2] == ['violated', 'unchecked', 'unchecked']
    assert drift.violated(fs2) is True           # one violation is drift among anything
    assert drift.violated([]) is False


def test_the_token_is_the_digest_of_exactly_the_id_version_pairs():
    token_a_b = '6d68c13494019ac9af328a9eb8ab1281a1f04d24d1410267d48aaed0ef4c58be'
    a = _c('module_exists', {'path': 'app/core/*.py'}, 1)
    b = _c(None, None, 2, 2)
    assert drift.token([a, b]) == drift.token([b, a]) == token_a_b
    # nothing but (id, version) enters the digest: a re-wording or a re-spec must
    # not make yesterday's assessment look stale...
    assert drift.token([dict(a, statement='re-worded'), b]) == token_a_b
    other = dict(a, constraint={'kind': 'framework_pinned', 'spec': {'package': 'x'}})
    assert drift.token([other, b]) == token_a_b
    # ... but a version bump names a different set, so a constraint edited after
    # the evaluation cannot pass for what it saw (§6.4)
    assert drift.token([dict(a, version=2), b]) != token_a_b
    # hostile: a half-formed entity fails closed — no silent identity for it
    with pytest.raises(KeyError):
        drift.token([{'id': 'kno_%026d' % 9}])
    with pytest.raises(KeyError):
        drift.token([{'version': 1}])


# ── boundary values ─────────────────────────────────────────────────────────

@pytest.mark.parametrize('version,status', [
    ('19', 'satisfied'),        # a release of 19
    ('19.3', 'satisfied'),      # a release of 19.3
    ('19.3.0', 'satisfied'),    # the version itself
    ('1', 'violated'),          # '19.3.0' starts with '1' but is not a 1.x release
    ('19.3.1', 'violated'),     # a different release of 19.3
    ('3.0', 'violated'),        # digits inside the version are not the version
])
def test_a_pin_is_the_version_itself_or_a_release_of_it(version, status):
    p = _payload(dependencies=[{'name': 'react', 'spec': '^19.3.0',
                                'manifest': 'package.json'}])
    (f,) = drift.evaluate(p, [_c('framework_pinned',
                                 {'package': 'react', 'version': version})])
    assert f['status'] == status, (version, f)


def test_only_the_first_version_like_token_counts_and_an_unpinned_spec_pins_nothing():
    p = _payload(dependencies=[
        {'name': 'liberty', 'spec': '>=2.0, ~=1.9.3', 'manifest': 'pyproject.toml'},
        {'name': 'loose', 'spec': None, 'manifest': 'pyproject.toml'},
        {'name': 'weird', 'spec': 'latest', 'manifest': 'pyproject.toml'}])
    (f,) = drift.evaluate(p, [_c('framework_pinned',
                                 {'package': 'liberty', 'version': '2.0'})])
    assert f['status'] == 'satisfied'            # the first token is '2.0'
    (f,) = drift.evaluate(p, [_c('framework_pinned',
                                 {'package': 'liberty', 'version': '1.9.3'}, i=2)])
    assert f['status'] == 'violated'              # no resolver: the later token is not it
    assert f['reason'] == "liberty is declared as '>=2.0, ~=1.9.3', not 1.9.3"
    (f,) = drift.evaluate(p, [_c('framework_pinned',
                                 {'package': 'loose', 'version': '1'}, i=3)])
    assert f['status'] == 'violated'              # a spec-less requirement pins nothing
    assert f['reason'] == "loose is declared as '(unpinned)', not 1"
    (f,) = drift.evaluate(p, [_c('framework_pinned',
                                 {'package': 'weird', 'version': '1'}, i=4)])
    assert f['status'] == 'violated'              # a spec without digits is not a pin


def test_the_missing_package_the_multi_manifest_pin_and_the_reason_that_names_both():
    p = _payload(dependencies=[
        {'name': 'flask-login', 'spec': None, 'manifest': 'web/requirements.txt'},
        {'name': 'react', 'spec': '~18.0.0', 'manifest': 'web/package.json'},
        {'name': 'react', 'spec': '^19.3.0', 'manifest': 'docs/package.json'}])
    # a package missing from every manifest is a violation, and the reason names
    # it the way the payload spells it (norm_package, on the constraint's side too)
    (f,) = drift.evaluate(p, [_c('framework_pinned', {'package': 'Zope_Interface'})])
    assert (f['status'], f['reason']) == ('violated', 'zope-interface is not a dependency')
    (f,) = drift.evaluate(p, [_c('framework_pinned', {'package': 'Flask_Login'}, i=2)])
    assert f['status'] == 'satisfied'             # declared, and any version will do
    (f,) = drift.evaluate(p, [_c('framework_pinned',
                                 {'package': 'react', 'version': None}, i=3)])
    assert f['status'] == 'satisfied'             # `version: None` means "any pin"
    (f,) = drift.evaluate(p, [_c('framework_pinned',
                                 {'package': 'react', 'version': '19'}, i=4)])
    assert f['status'] == 'satisfied'             # ANY manifest pinning it is enough
    p2 = _payload(dependencies=[{'name': 'react', 'spec': None, 'manifest': 'a'},
                                {'name': 'react', 'spec': '~18.0.0', 'manifest': 'b'},
                                {'name': 'react', 'spec': '18.9', 'manifest': 'c'}])
    (f,) = drift.evaluate(p2, [_c('framework_pinned',
                                  {'package': 'react', 'version': '19'}, i=5)])
    assert f['status'] == 'violated'
    assert f['reason'] == "react is declared as '(unpinned), ~18.0.0, 18.9', not 19"


def test_files_outside_the_layers_and_imports_inside_one_layer_break_nothing():
    p = _payload(edges=[
        ['ui/a.py', 'api/b.py'],          # down the layers: fine
        ['api/b.py', 'api/c.py'],         # inside one layer: fine (needs `<`, not `<=`)
        ['core/c.py', 'tools/gen.py'],    # dst in no layer: cannot be judged, so fine
        ['scripts/x.py', 'core/c.py'],    # src in no layer: fine (it must not crash)
    ])
    (f,) = drift.evaluate(p, [_c('require_layering',
                                  {'layers': ['ui/**', 'api/**', 'core/**']})])
    assert (f['status'], f['reason'], f['violations'], f['violation_count']) == (
        'satisfied', None, [], 0)
    # the one edge that really does import UP is found, exactly once, and named
    p = _payload(edges=[['ui/a.py', 'api/b.py'], ['core/c.py', 'scripts/x.py'],
                        ['core/c.py', 'ui/a.py']])
    (f,) = drift.evaluate(p, [_c('require_layering',
                                 {'layers': ['ui/**', 'api/**', 'core/**']})])
    assert f['status'] == 'violated'
    assert f['violations'] == [['core/c.py', 'ui/a.py']]
    assert f['violation_count'] == 1
    assert f['reason'] == '1 import(s) break it'


# ── error paths: missing and moved, said with a reason ─────────────────────

def test_a_moved_file_is_a_missing_file_and_the_reason_names_the_pattern():
    c = _c('module_exists', {'path': 'app/core/*.py'})
    (f,) = drift.evaluate(_payload(files=['app/core/models.py', 'app/api/view.py']), [c])
    assert (f['status'], f['reason'], f['violations'], f['violation_count']) == (
        'satisfied', None, [], 0)
    # the file was moved sideways and renamed: near misses do not match the
    # pattern, and `fnmatchcase` is case-sensitive by contract on every platform
    moved = _payload(files=['App/Core/Models.py', 'app/corex/models.py',
                            'app/legacy/core/models.py', 'app/core/models.txt'])
    (f,) = drift.evaluate(moved, [c])
    assert f['status'] == 'violated'
    assert f['reason'] == 'no file matches app/core/*.py'
    assert f['violations'] == [] and f['violation_count'] == 0
    # an empty world is missing too: a walk that found nothing is not a pass
    (f,) = drift.evaluate(_payload(), [c])
    assert f['status'] == 'violated'
