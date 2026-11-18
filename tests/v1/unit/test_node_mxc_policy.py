"""T-238 — `compile_policy` policy-validation checks for the closed MXC seam.

Adapted by Qwen from the PV-20/T-196 draft (`test_node_mxc_policy_draft.py` and the
field-by-field note `PV20-mxc-policy-tests-qwen.md`) onto the seam that actually exists in
`archeus/node/mxc.py`. The citation tags below are the note's tags: `S:` = the pinned schema
guide lines the note cites, `P:` = the protocol note, `E:` = its examples, `F:` = the
feasibility file, **card** = a Core-side hardening rule the note itself adds, **INFERRED** =
a reasoning step from a pinned fact. What the note left UNKNOWN gets no test here; the two
cases that touch an UNKNOWN (a `cwd` inside a read-only grant, a `readonly` entry that is also
`denied`) are marked in their docstrings as claims about *this compiler's* gates, never about
what MXC would do.

These are compiler checks: `compile_policy` is data-to-data, so no container is created, no
native run happens, no process is spawned and no Windows API is called — the filesystem is
`tmp_path` and the only backends touched are the injected fakes the neighbouring
`test_node_mxc.py` uses. That file already pins the closed default document, the hardlink and
reparse scans, the proxy happy path, the native-disabled gate and the identity checks; this
file does not repeat them, it covers the per-field and cross-argument refusals.

The draft's Windows-shaped cases (drive-relative, drive-root, UNC spellings) are deliberately
absent: on this container's POSIX filesystem `os.path.isabs` rejects those strings as
relative, so they would pass without exercising the rule they name. They need the Windows pass
Claude runs; the report lists them.
"""

import json
import os
import re

import pytest

from archeus.node import mxc

# The refusal class the seam declares and its callers catch.
ERROR = mxc.MxcUnavailable

PATH_ARGS = ('workspace', 'cwd', 'readonly', 'denied')

BASE_ENV = {'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': 'C:\\pv20\\p\\config'}


def dirs(tmp_path):
    """The fixture tree: a workspace, a runtime folder, a config folder and a Core-private
    folder no grant may name. Nothing in it is a real MXC artifact."""
    made = {}
    for name in ('work', 'runtime', 'config', 'core-private'):
        (tmp_path / name).mkdir(exist_ok=True)
        made[name] = str(tmp_path / name)
    return made


def arguments(tmp_path, **changes):
    """One baseline call (note §"The seam under test"), varied by exactly one argument."""
    made = dirs(tmp_path)
    args = dict(workspace=made['work'], cwd=made['work'],
                command_line='cmd.exe /d /c echo fixture', env=dict(BASE_ENV),
                timeout_ms=1000)
    args.update(changes)
    return made, args


def compile_of(tmp_path, **changes):
    """Compile the varied baseline and return the `MxcPolicy` (not just `raw`)."""
    made, args = arguments(tmp_path, **changes)
    return mxc.compile_policy(**args)


def accepted(tmp_path, **changes):
    """A call the compiler must accept, returning the `MxcPolicy` itself (the launch-path
    cases below mutate it)."""
    made, args = arguments(tmp_path, **changes)
    try:
        policy = mxc.compile_policy(**args)
    except ERROR as err:            # this call must pass, so a refusal is an assertion failure
        raise AssertionError('compile_policy refused (%s): %r' % (err, sorted(changes))) from err
    assert isinstance(policy, mxc.MxcPolicy), 'compile_policy returned %r' % type(policy)
    assert isinstance(policy.raw, dict), 'MxcPolicy.raw must be a dict'
    # The interface calls `raw` a validated, serialisable JSON object (interface:14-16) and
    # the launcher consumes it as a policy file, so nothing in it may lack a JSON spelling.
    assert json.loads(json.dumps(policy.raw, allow_nan=False)) == policy.raw
    return policy


def compiled(tmp_path, **changes):
    """As `accepted`, but returns `MxcPolicy.raw`."""
    return accepted(tmp_path, **changes).raw


def refused(tmp_path, match, exc=ERROR, **changes):
    """A call the compiler must refuse. `match` is the wording of the branch the case names,
    so a compiler that refuses everything for the wrong reason does not pass either."""
    made, args = arguments(tmp_path, **changes)
    with pytest.raises(exc, match=match):
        mxc.compile_policy(**args)


def vary(tmp_path, match, arg, value):
    """Refuse `arg=value`. A list argument gets the value as its only entry, so the
    per-entry path rules run without changing the shape of the argument."""
    if arg in ('readonly', 'denied'):
        return refused(tmp_path, match, **{arg: (value,)})
    return refused(tmp_path, match, **{arg: value})


def fs(raw, key):
    return raw['filesystem'][key]


def net(raw, section, key):
    return raw['network'][section][key]


def all_keys(node):
    """Every key name anywhere in the document, for the forbidden-field scans."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key)
            for nested in all_keys(value):
                yield nested
    elif isinstance(node, (list, tuple, set)):
        for value in node:
            for nested in all_keys(value):
                yield nested


def make(tmp_path, name, kind='dir'):
    path = tmp_path / name
    if kind == 'dir':
        path.mkdir(parents=True, exist_ok=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('synthetic')
    return str(path)


def link_at(path, target, maker, reason):
    """Create a link at `path`, or skip. A skipped case is honest; one that passes because the
    host refused to build the link is not (F:57 leaves the symlink case open)."""
    try:
        maker(str(target), str(path))
    except (OSError, AttributeError, NotImplementedError) as err:
        pytest.skip('this host refuses to create the %s (%s)' % (reason, err))
    return str(path)


# ── must pass: nothing dropped, nothing invented (no widening of a grant) ─────────────


def test_grant_lists_are_exactly_the_named_paths(tmp_path):
    """Rows `readwritePaths`/`readonlyPaths`/`deniedPaths` (S:213-215, S:394, S:396): Core's
    lists *are* the policy's lists — every named entry carried, nothing added, nothing
    folded away. A policy that grants a directory the caller never named is the widening this
    pins: dropping the comprehension over `readonly`/`denied`, or seeding `readwritePaths`
    from anything but `workspace`, fails it."""
    made = dirs(tmp_path)
    spawn = make(tmp_path, 'spawn-config')
    raw = compiled(tmp_path, readonly=(made['runtime'], spawn), denied=(made['core-private'],))
    assert fs(raw, 'readwritePaths') == [made['work']]
    assert fs(raw, 'readonlyPaths') == [made['runtime'], spawn]
    assert fs(raw, 'deniedPaths') == [made['core-private']]
    for paths in raw['filesystem'].values():
        for path in paths:
            assert isinstance(path, str) and os.path.isabs(path)
            assert path == os.path.normpath(path), 'a non-canonical name reaches the backend'


def test_omitted_readonly_and_denied_default_to_empty(tmp_path):
    """Same rows, default column (S:395-396 `[]`; interface:17): an omitted argument may be
    absent or empty, never populated from somewhere else — an `os.getcwd()` or
    `os.environ`-derived default would show up here (INFERRED from the module docstring:
    "never inherit the host environment")."""
    raw = compiled(tmp_path, readonly=(), denied=())
    assert fs(raw, 'readonlyPaths') == [] and fs(raw, 'deniedPaths') == []


def test_two_writable_grants_are_both_carried_and_both_scanned(tmp_path):
    """Row `filesystem.readwritePaths` (**card**; seam Open item 10): `workspace` may name
    more than one directory and each of them is granted *and* put through the alias and
    hardlink scans. Validating only the first grant would hand the second to the container
    unchecked, so the second one carries the hardlink here and must be refused."""
    made = dirs(tmp_path)
    second = make(tmp_path, 'requests')
    raw = compiled(tmp_path, workspace=[made['work'], second], cwd=made['work'])
    assert fs(raw, 'readwritePaths') == [made['work'], second]
    outside = make(tmp_path, 'secret-outside', 'file')
    link_at(os.path.join(second, 'late-alias'), outside, os.link, 'hardlink')
    with pytest.raises(ERROR, match='multiple links'):
        compile_of(tmp_path, workspace=[made['work'], second], cwd=made['work'])


def test_command_line_is_verbatim_and_cwd_is_canonical(tmp_path):
    """Rows `process.commandLine`/`process.cwd` (S:180-186, S:202-203, S:323-348). The command
    is carried verbatim — quotes, spaces and arguments included — because any rewriting by the
    compiler is a command the caller did not ask Core to run. `cwd` is carried canonical:
    `_path` folds a `..` spelling, and `validate_policy` then refuses any document whose paths
    are not canonical, so a name the backend would resolve differently never leaves Core
    (**card**, §C traversal)."""
    made = dirs(tmp_path)
    sub = make(tmp_path, 'work/exec')
    command = '"C:\\Program Files\\agent.exe" --stage T238 --msg "a b"'
    raw = compiled(tmp_path, command_line=command, workspace=sub,
                   cwd=os.path.join(made['work'], 'sub', '..', 'exec'))
    assert raw['process']['commandLine'] == command
    assert raw['process']['cwd'] == sub
    assert fs(raw, 'readwritePaths') == [sub]


def test_timeout_is_carried_as_an_integer(tmp_path):
    """Row `process.timeout` (S:209; P:65): the budget the caller asked for is the budget the
    policy carries. Silently substituting a default, or a longer value, is how an execution
    outlives its own timeout. Upper/lower bounds are the note's Open item 1 and stay
    untested."""
    raw = compiled(tmp_path, timeout_ms=45_000)
    assert raw['process']['timeout'] == 45_000
    assert type(raw['process']['timeout']) is int


def test_the_env_block_is_exactly_the_supplied_one(tmp_path, monkeypatch):
    """Rows `process.env` and `process.inheritDefaultEnv` (S:207, S:208, S:356-366; P:57-63).
    Every supplied variable is carried, its name keeps its supplied spelling, a value may
    contain `=`, and nothing else is added: a host variable the caller never named must not
    appear, and `inheritDefaultEnv` stays `False`, because `true` layers the supplied block
    *over* the backend default and so hands the child an environment larger than the one Core
    reviewed (INFERRED from S:364-366).

    The draft asked for the supplied *order* to be preserved; the seam sorts the entries and
    `test_node_mxc.py::test_closed_default_policy` already pins that, so order is not claimed
    here.
    """
    monkeypatch.setenv('MXC_T238_HOST_ONLY', 'must-not-appear')
    raw = compiled(tmp_path, env={'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': 'C:\\cfg',
                                  'TASK': 'a=b', 'Weird_Case': 'v'})
    assert raw['process']['env'] == ['LOCALAPPDATA=C:\\cfg', 'SYSTEMROOT=C:\\Windows',
                                     'TASK=a=b', 'Weird_Case=v']
    assert raw['process']['inheritDefaultEnv'] is False
    assert 'must-not-appear' not in json.dumps(raw)


def test_ui_is_the_verified_pair_and_opens_nothing_else(tmp_path):
    """Rows `ui.disable`/`ui.clipboard`/`ui.injection`/`telemetry.enabled`: the desktop stays
    disabled, the clipboard closed, injection off and telemetry off, and the network stays deny."""
    raw = compiled(tmp_path)
    assert raw['ui'] == {'disable': True, 'clipboard': 'none', 'injection': False}
    assert raw['telemetry'] == {'enabled': False}
    assert net(raw, 'egress', 'default') == 'deny'
    assert net(raw, 'ingress', 'default') == 'deny'
    assert net(raw, 'ingress', 'hostLoopback') == 'deny'


def test_a_desktop_is_never_requested(tmp_path):
    refused(tmp_path, 'unsupported UI or egress policy', ui=True)


def test_proxy_policy_keeps_egress_deny_and_carries_no_direct_rules(tmp_path):
    """Rows `runtimeConfig.networkProxy` + `network.*` (S:106-108, S:139-140, S:143-145; E:109-111;
    P:89-90, P:231). `test_node_mxc.py` pins the proxy policy's three field values; this pins
    what makes it safe: egress still resolves to `deny` with no direct rule anywhere in the
    document (S:106-108, direct rules and a proxy cannot be combined; E:110-111), the endpoint
    is carried verbatim, and the policy claims no packaged identity — `allowedProxyPeer` is
    absent, because naming one binds the route to an identity Core never reviewed (S:118-123,
    P:232). Which proxy shape `proxy_url` means is the note's Open item 3, so only the absence
    is claimed, and the emitted `internetClient` capability (Open item 2, F:47, E:123) is left
    to `test_node_mxc.py::test_proxy_uses_f3_fixture_fields_and_ui_stays_disabled` rather than
    re-claimed here."""
    proxy = 'http://127.0.0.1:18080'
    raw = compiled(tmp_path, proxy_url=proxy)
    assert net(raw, 'egress', 'default') == 'deny'
    assert set(raw['network']['egress']) == {'default'}, 'a direct egress rule appeared'
    assert net(raw, 'ingress', 'default') == 'allow', 'S:118: a proxy needs ingress allow'
    assert net(raw, 'ingress', 'hostLoopback') == 'allow'
    assert raw['runtimeConfig'] == {'networkProxy': proxy}
    assert 'allowedProxyPeer' not in set(all_keys(raw))


@pytest.mark.parametrize('proxy', ['http://127.0.0.1:18080', 'http://127.0.0.1:18080/',
                                   'http://127.0.0.1:65535', 'http://[::1]:18080'])
def test_a_loopback_http_endpoint_is_carried_verbatim(tmp_path, proxy):
    """Row `runtimeConfig.networkProxy`, must-pass column (both documented forms are
    `http://127.0.0.1:<port>` — S:140, P:216): the endpoint Core hands the caller-managed
    proxy is the one the caller named; rewriting the port or the scheme would point the
    container at a different process. `::1` is pinned next to `127.0.0.1` because both are
    loopback, so neither opens a route the deny posture does not already allow — whether the
    seam should take IPv6 at all is a review question, not a fact (Open item 3)."""
    raw = compiled(tmp_path, proxy_url=proxy)
    assert raw['runtimeConfig'] == {'networkProxy': proxy}
    assert net(raw, 'ingress', 'default') == 'allow'


def test_only_the_documented_sections_exist_and_every_field_is_a_known_one(tmp_path):
    """Rows §A/§B, positive column: the document is the closed subset — eight sections, no
    backend-specific section (`lxc`, `seatbelt`, `wslc`, `hyperlight`: S:401-403, S:505-507,
    "Multiple containment backends configured"), and every key name anywhere in the tree is
    one the guide names (S:189-303, S:392-396, S:405-408, S:452-456). An unregistered field is
    not a harmless extra hint: the guide rejects unknown content (S:315-317), so emitting one
    is a policy that dies at execution, far from its cause. "Run it in WSL instead" is the
    degradation F:54-57 makes expensive, which is why the foreign sections are named."""
    raw = compiled(tmp_path)
    assert set(raw) == {'version', 'containment', 'lifecycle', 'process', 'filesystem',
                        'network', 'ui', 'telemetry'}
    assert 'processContainer' not in raw and 'runtimeConfig' not in raw
    for foreign in ('lxc', 'seatbelt', 'wslc', 'hyperlight', 'microvm', 'bubblewrap',
                    'windows_sandbox', 'fallback', 'isolation_session'):
        assert foreign not in raw
    known = {
        'version', 'containerId', 'containment', 'lifecycle', 'destroyOnExit', 'preservePolicy',
        'process', 'commandLine', 'cwd', 'env', 'inheritDefaultEnv', 'timeout', 'filesystem',
        'readwritePaths', 'readonlyPaths', 'deniedPaths', 'network', 'egress', 'ingress',
        'default', 'allow', 'deny', 'hostLoopback', 'to', 'cidr', 'ports', 'protocol', 'port',
        'ui', 'disable', 'clipboard', 'injection', 'processContainer', 'leastPrivilege',
        'capabilities', 'enumeratePaths', 'captureDenials', 'mode', 'outputPath', 'retainEtl',
        'runtimeConfig', 'networkProxy', 'allowedProxyPeer', 'telemetry', 'enabled',
    }
    unknown = {k.lower() for k in all_keys(raw)} - {k.lower() for k in known}
    assert not unknown, 'the policy carries a field the guide does not name: %s' % sorted(unknown)


def test_no_identity_retired_or_unreached_field_is_ever_emitted(tmp_path):
    """Rows §B and §D (`containerId`, the execution-supplied names, the retired list):
    `phase`/`sandboxId` are lifecycle-only and create-and-run input carrying one is parsed as
    *that operation* (S:44-49), create-and-run JSON carrying `sandboxId` is rejected
    (S:313-315), `correlationVector` cannot be supplied by callers (S:315-317), `containerId`
    is externally assigned and cleanup keys on the launcher's record (S:192, S:561-565), and
    the retired names are accepted by no supported contract (S:149-153). Checked under every
    posture the seam can reach, not just the default."""
    banned = {'containerId', 'phase', 'sandboxId', 'sessionId', 'correlationVector',
              'defaultPolicy', 'enforcementMode', 'allowLocalNetwork', 'allowedHosts',
              'blockedHosts', 'proxy', 'allowWindows', 'leastPrivilege', 'enumeratePaths',
              'captureDenials', 'outputPath', 'retainEtl', 'allowedProxyPeer',
              'allowDaclMutation', 'profileOverride', 'distribution', 'image', 'runtime',
              '$schema'}
    for changes in ({}, {'proxy_url': 'http://127.0.0.1:18080'},
                    {'readonly': (dirs(tmp_path)['runtime'],)}, {'timeout_ms': 5_000}):
        emitted = {k.lower() for k in all_keys(compiled(tmp_path, **changes))}
        hit = emitted & {b.lower() for b in banned}
        assert not hit, '%s in a policy compiled from %s' % (sorted(hit), changes)


def test_undeclared_keyword_cannot_reach_the_policy(tmp_path):
    """§B and §D (**card**): the signature is frozen (interface:17-18), so a caller cannot
    reach past it. Every name below is a field the guide defines that no argument may request;
    accepting one would let a caller ask for a capability, a preserved policy, keystroke
    injection or a Dacl mutation this seam does not expose. The frozen `*` is what makes it a
    `TypeError`, and that is the contract."""
    compiled(tmp_path)                                  # the baseline call must still work
    made = dirs(tmp_path)
    for field in ('containerId', 'phase', 'sandboxId', 'sessionId', 'correlationVector',
                  'defaultPolicy', 'enforcementMode', 'allowWindows', 'leastPrivilege',
                  'inheritDefaultEnv', 'clipboard', 'injection', 'destroyOnExit',
                  'preservePolicy', 'telemetry', 'enumeratePaths',
                  'allowedProxyPeer', 'retainEtl', 'allowDaclMutation', 'containment',
                  'version', 'proxy', 'readwritePaths', 'readonlyPaths', 'deniedPaths',
                  'networkProxy'):
        with pytest.raises(TypeError):
            mxc.compile_policy(workspace=made['work'], cwd=made['work'],
                               command_line='cmd.exe /c echo x', env=dict(BASE_ENV),
                               timeout_ms=1000, **{field: 'start'})


def test_signature_is_keyword_only(tmp_path):
    """interface:17-18 declares `def compile_policy(*, ...)`: a positional call is not part of
    the contract — INFERRED reason: an argument-order drift could silently turn a readonly
    path into a denied one."""
    made = dirs(tmp_path)
    with pytest.raises(TypeError):
        mxc.compile_policy(made['work'], (made['runtime'],), (made['core-private'],),
                           made['work'], 'cmd.exe /c echo x', {}, 1000)


def test_all_arguments_together_compile(tmp_path):
    """The whole signature at once (interface:17-18): no argument may require another to be
    absent, and a proxy plus a desktop plus several grants is still a deny-posture policy."""
    made = dirs(tmp_path)
    exec_dir = make(tmp_path, 'work/exec')
    responses = make(tmp_path, 'responses')
    authority = make(tmp_path, 'authority')
    raw = compiled(tmp_path, workspace=exec_dir, cwd=exec_dir,
                   readonly=(made['runtime'], responses),
                   denied=(made['core-private'], authority),
                   env={'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': made['config'],
                        'TASK': 'T238'},
                   egress='deny', proxy_url='http://127.0.0.1:18080',
                   timeout_ms=30_000)
    assert fs(raw, 'readwritePaths') == [exec_dir]
    assert fs(raw, 'readonlyPaths') == [made['runtime'], responses]
    assert fs(raw, 'deniedPaths') == [made['core-private'], authority]
    assert raw['process']['env'][-1] == 'TASK=T238' and raw['process']['timeout'] == 30_000
    assert raw['ui']['disable'] is True and net(raw, 'egress', 'default') == 'deny'


def test_the_working_directory_may_lie_in_a_readonly_grant(tmp_path):
    """Row `process.cwd` + §D (`_within`/`_separate`, isolation.py:393-406): the gate is "cwd
    inside *a* grant", not "cwd inside the writable grant".

    The note marks the backend's own answer for a `cwd` that names a read-only entry UNKNOWN
    (its `process.cwd` row, Open item 9) and prescribes no test for *that*; nothing here claims
    what MXC would do with such a `cwd`. What is claimed is the shape of Core's gate, because
    both directions are widening risks: narrow the gate to the writable grant and the caller's
    way around it is to widen `workspace` to cover a staged tool folder; widen it past the
    grants and containment is gone. If review decides the opposite rule (Open item 9), this
    case is the one to invert, and the refusal cases below stay valid either way."""
    made = dirs(tmp_path)
    tools = make(tmp_path, 'runtime/tools')
    raw = compiled(tmp_path, readonly=(made['runtime'],), cwd=tools)
    assert raw['process']['cwd'] == tools
    assert fs(raw, 'readwritePaths') == [made['work']]


# ── must refuse: the path rules, per entry of every path argument (§C) ────────────────

RELATIVE = ['work', './work', '../work', 'work/sub', '', '.', 'C:work']


@pytest.mark.parametrize('arg', PATH_ARGS)
@pytest.mark.parametrize('value', RELATIVE)
def test_relative_path_is_refused(tmp_path, arg, value):
    """§C row 2 (**card**; INFERRED from the skip/substitution rules S:323-331, S:341-343): a
    relative policy entry is skipped by the backend or passed verbatim with a substituted
    default, so containment can never be evaluated on it — containment only means anything over
    absolute names, and the one explicit absolute rule is the drive-path rule S:344-348. `''`
    and `'.'` are the blank/`.` entries the guide *skips* elsewhere, which is a reason to
    refuse rather than to rely on someone else's skip."""
    vary(tmp_path, 'must be absolute', arg, value)


@pytest.mark.parametrize('arg', PATH_ARGS)
@pytest.mark.parametrize('value', [1, None, b'/work', 1.5, object()])
def test_a_path_that_is_not_text_is_refused(tmp_path, arg, value):
    """§C row 1 (**card**; types PINNED S:203, S:207, S:213-215): a path that is not text must
    never reach the document. `bytes` is the case to watch — `os.fspath` accepts it, so an
    implementation that forgot the text check would emit a byte string the launcher cannot
    open. The seam is not uniform about the *class* it raises for a malformed argument (some
    leak `TypeError` from `os.fspath`/`tuple(...)`), so this accepts either: the property under
    test is that no policy comes out."""
    made, args = arguments(tmp_path, **({arg: (value,)} if arg in ('readonly', 'denied')
                                        else {arg: value}))
    with pytest.raises((ERROR, TypeError)):
        mxc.compile_policy(**args)


@pytest.mark.parametrize('arg', ('workspace', 'readonly', 'denied'))
@pytest.mark.parametrize('value', [1, None, True, {'p': 1}, object()])
def test_a_container_that_is_not_a_sequence_is_refused(tmp_path, arg, value):
    """§C row 1, container form (**card**): `workspace`/`readonly`/`denied` name string
    sequences. A `set` is deliberately *not* in this list — iterating a set of paths grants
    exactly the paths named, so refusing it would be a shape rule the note never pins; the
    footgun that does matter is the bare `str` below."""
    made, args = arguments(tmp_path)
    args[arg] = value
    with pytest.raises((ERROR, TypeError)):
        mxc.compile_policy(**args)


@pytest.mark.parametrize('arg', ('readonly', 'denied'))
def test_a_bare_string_where_a_sequence_belongs_is_refused(tmp_path, arg):
    r"""§C row 1, the case the draft singled out (S:395: the field is a string[]):
    `readonly=(r"C:\pv20\runtime",)` is right and `readonly="C:\pv20\runtime"` is the bug —
    `str` is a `Sequence`, so an unguarded `list(...)` turns one path into a pile of
    one-character grants. Iterating a drive path yields `C`, `:`, `\\`, so nothing there is
    absolute and the compile refuses it instead of emitting a filesystem section of letters."""
    refused(tmp_path, 'must be absolute', **{arg: 'C:\\pv20\\runtime'})


@pytest.mark.parametrize('arg', ('readonly', 'denied'))
@pytest.mark.parametrize('value', ['work/../work', 'work/sub/..', './work/../work'])
def test_a_protected_entry_that_normalises_onto_the_workspace_is_refused(tmp_path, arg, value):
    """§C row 3 (**card**; INFERRED: containment is a comparison over canonical paths). The
    draft refused both the raw and the normalised `..` spelling; this seam canonicalises with
    `os.path.normpath` at compile and then *requires* the canonical form, so what this case
    actually pins is the security content underneath: a protected entry written with a `..`
    that lands on the workspace still trips the overlap gate. The bypass it blocks is the
    classic one — a gate that compares strings would treat `work/../work` as "different" and
    the backend would resolve it equal."""
    made = dirs(tmp_path)
    entry = os.path.join(os.path.dirname(made['work']), value)
    assert os.path.normpath(entry) == made['work']
    with pytest.raises(ERROR, match='overlaps protected'):
        compile_of(tmp_path, **{arg: (entry,)})


@pytest.mark.parametrize('key', ['readwritePaths', 'readonlyPaths', 'deniedPaths'])
def test_a_non_canonical_path_in_a_compiled_policy_is_refused(tmp_path, key):
    """§C row 3, the other half: a document that already carries a `..`, a `.` or a doubled
    separator is refused even though it names an admissible directory, because the backend
    resolves the name and Core cannot know what it resolved to. This is the branch
    `validate_policy`'s `_path(path) != path` owns — and it runs again at launch, after
    whoever held the file had their chance."""
    policy = accepted(tmp_path)
    current = policy.raw['filesystem'][key]
    anchor = current[0] if current else dirs(tmp_path)['work']
    policy.raw['filesystem'][key] = [anchor + os.sep + 'sub' + os.sep + '..']
    with pytest.raises(ERROR, match='noncanonical path'):
        mxc.validate_policy(policy)


@pytest.mark.parametrize('arg', ('workspace', 'readonly'))
def test_an_alias_inside_a_grant_is_refused(tmp_path, arg):
    """§C row 4 (**card**; basis PINNED F:54, F:57): enforcement is path-based, so a second
    name for the same object defeats the grant — the F2 hardlink escaped read *and* write
    through a link inside the granted folder, and the file's own requirement is to refuse or
    copy anything multiply named, scanning **before** the grant. The draft put the link at the
    argument itself; the seam checks the tree, so the alias here sits inside a scanned grant
    and points at a file no grant names."""
    made = dirs(tmp_path)
    outside = make(tmp_path, 'secret-outside', 'file')
    root = made['work'] if arg == 'workspace' else made['runtime']
    link_at(os.path.join(root, 'inside-alias'), outside, os.symlink, 'symlink')
    with pytest.raises(ERROR, match='alias in grant'):
        compile_of(tmp_path, **({} if arg == 'workspace' else {'readonly': (root,)}))


def test_a_grant_reached_through_a_symlinked_ancestor_is_refused(tmp_path):
    """§C row 4, ancestor form (F:54, F:57): an alias *above* the granted folder gives the
    whole subtree a second name that no grant names, so the ancestor walk refuses it before
    anything is scanned. Deleting this branch is the F2 escape returning through the front
    door."""
    real = make(tmp_path, 'real/proj')
    alias = link_at(tmp_path / 'alias-root', os.path.dirname(real), os.symlink, 'symlink')
    granted = os.path.join(alias, 'proj')
    assert os.path.realpath(granted) == real, 'the fixture did not build the alias'
    with pytest.raises(ERROR, match='alias in grant ancestor'):
        compile_of(tmp_path, workspace=granted, cwd=granted)


@pytest.mark.parametrize('kind', ['missing', 'notdir', 'alias'])
def test_a_protected_grant_that_cannot_be_read_is_refused(tmp_path, kind):
    """§C rows 1 and 4, fail-closed form: a `readonly` entry that does not exist, is not a
    directory or is an alias is refused rather than quietly dropped — a grant list that loses
    an entry on the way in is a policy that looks checked and is not, and the caller would
    learn about it as an access error inside the container. The refusal must not name the
    outside path either (`test_node_mxc.py` pins the same discipline for hardlinks: the scan
    strips its causes)."""
    made = dirs(tmp_path)
    if kind == 'missing':
        entry = os.path.join(made['runtime'], 'never-created')
    elif kind == 'notdir':
        entry = make(tmp_path, 'runtime/file-entry.txt', 'file')
    else:
        outside = make(tmp_path, 'elsewhere')
        entry = link_at(tmp_path / 'runtime-alias', outside, os.symlink, 'symlink')
    with pytest.raises(ERROR, match='hardlink scan failed') as caught:
        compile_of(tmp_path, readonly=(entry,))
    assert 'never-created' not in str(caught.value)
    assert 'file-entry.txt' not in str(caught.value)
    assert 'elsewhere' not in str(caught.value)


# ── must refuse: cross-argument rules (§D) ────────────────────────────────────────────


@pytest.mark.parametrize('arg,shape', [(a, s) for a in ('readonly', 'denied')
                                       for s in ('equal', 'inside', 'ancestor')])
def test_a_writable_grant_may_not_meet_a_protected_grant(tmp_path, arg, shape):
    """§D rows 1-5, the separation invariant. One is PINNED: the same directory in
    `readwritePaths` and `deniedPaths` is *denied* (S:418), so a self-deny is not a
    contradiction the backend rejects — it is a workspace with no writes at all, failing at the
    agent's first file write, far from its cause. The guide cuts the other way for a denied
    ancestor ("an explicitly granted readwrite child of a denied parent remains readable and
    writable", S:420-421), which is the problem: whether the workspace is writable would hang
    on grant specificity rather than on anything the document states. `readonlyPaths` overlap
    is resolved nowhere in the guide (S:416-424), so those rows are **card**/**INFERRED**, and
    `isolation.py:393-406` (`_within`/`_separate`, used at :364) already requires each grant
    directory not to be, hold or lie inside the workspace — this seam may not regress it.
    `test_node_mxc.py` pins only readonly-inside-workspace; equality, the ancestor direction
    and everything against `denied` is new here."""
    made = dirs(tmp_path)
    work = made['work']
    root = os.path.dirname(work)
    value = {'equal': made['core-private'], 'inside': os.path.join(work, 'staged'),
             'ancestor': root}[shape]
    changes = {arg: (value,)}
    if shape == 'equal':                        # name one directory on both sides
        changes['workspace'] = made['core-private']
        changes['cwd'] = made['core-private']
    with pytest.raises(ERROR, match='overlaps protected'):
        compile_of(tmp_path, **changes)


def test_a_second_writable_grant_cannot_dodge_the_overlap_gate(tmp_path):
    """Same rows, multi-grant form (`for a in rw for b in ro + denied`): the gate quantifies
    over *every* writable grant, so a denied or read-only path wrapping the *second* grant is
    refused too. Cutting that loop to the first entry — or granting a list and checking only
    `workspace` — fails this case while every single-grant case still passes."""
    made = dirs(tmp_path)
    second = make(tmp_path, 'requests')
    with pytest.raises(ERROR, match='overlaps protected'):
        compile_of(tmp_path, workspace=[made['work'], second], denied=(second,),
                   cwd=made['work'])


@pytest.mark.parametrize('shape', ['equal', 'inside', 'ancestor'])
def test_a_readonly_grant_may_not_meet_a_denied_grant(tmp_path, shape):
    """§D row 6: the guide resolves overlap for `readwritePaths`/`deniedPaths` only and says
    nothing about a `readonlyPaths` ∩ `deniedPaths` name, so the note marks how MXC would
    resolve it UNKNOWN and prescribes no test for that (its §D row). This case claims nothing
    about MXC: it pins only that *this compiler* refuses to emit a document that withholds a
    directory in one list and re-reads it in another — the deny-by-default side of the contract,
    because such a policy's meaning depends on an evaluation order nobody can see, and a policy
    whose meaning you cannot state must not ship (**card**, stated weakly on purpose)."""
    made = dirs(tmp_path)
    runtime = make(tmp_path, 'runtime')
    sub = make(tmp_path, 'runtime/sub')
    value = {'equal': runtime, 'inside': sub, 'ancestor': runtime}[shape]
    grant = {'equal': runtime, 'inside': runtime, 'ancestor': sub}[shape]
    with pytest.raises(ERROR, match='overlaps denied'):
        compile_of(tmp_path, readonly=(grant,), denied=(value,))


@pytest.mark.parametrize('shape', ['parent', 'ghost', 'sibling', 'file', 'denied'])
def test_the_working_directory_must_lie_inside_a_grant(tmp_path, shape):
    """Row `process.cwd` + §D (**card**): a `cwd` no grant names is a working directory the
    container resolves against the host, so the whole containment argument stops meaning
    anything — and the guide *skips* or substitutes a bad `cwd` rather than refusing it
    (S:323-348), which is precisely why Core must refuse it at compile (INFERRED). `denied` is
    the shape the note leaves open as Open item 9 (must `cwd` be inside a grant at all?): it is
    refused here because the only way to reach it is to put `cwd` outside every grant."""
    made = dirs(tmp_path)
    root = os.path.dirname(made['work'])
    value = {'parent': root, 'ghost': os.path.join(root, 'ghost'),
             'sibling': made['runtime'], 'denied': made['core-private'],
             'file': make(tmp_path, 'work/notes.txt', 'file')}[shape]
    changes = {'cwd': value}
    if shape == 'denied':
        changes['denied'] = (made['core-private'],)
    with pytest.raises(ERROR, match='cwd outside grants'):
        compile_of(tmp_path, **changes)


@pytest.mark.parametrize('rescue', [False, True])
def test_a_call_that_names_no_writable_directory_is_refused(tmp_path, rescue):
    """Rows `filesystem.readwritePaths` and `workspace` (S:213, interface:17): a policy with no
    writable grant is refused — and refused even when a read-only grant would satisfy the `cwd`
    rule, because otherwise the "is there a writable grant at all" question is answered by a
    check that was written for something else. An execution that can write nothing is not a
    sandbox, it is a process carrying a document that promises nothing, and the caller would
    find out at the agent's first write."""
    made = dirs(tmp_path)
    changes = {'workspace': []}
    if rescue:                        # the cwd is covered by a read-only grant instead
        changes.update(readonly=(made['runtime'],), cwd=make(tmp_path, 'runtime/tools'))
    with pytest.raises(ERROR, match='cwd outside grants'):
        compile_of(tmp_path, **changes)


# ── must refuse: egress, UI and the proxy route (network fields) ──────────────────────


@pytest.mark.parametrize('egress', ['allow', 'ALLOW', 'Allow', 'Deny', 'DENY', 'open', 'block',
                                    'any', '', 'deny ', None, 1, True, ['deny']])
def test_egress_other_than_deny_is_refused(tmp_path, egress):
    """Row `network.egress.default` (**card**, consistent with PINNED deny-by-default
    S:111-112, the proxy contract S:116-117/E:109-111 and the measured deny posture F:10 T3):
    `"allow"` *is* a documented spelling for other backends (S:157-176), so this refusal is
    Core's rule and not MXC's — an agent reaching the network with no proxy and no broker is
    exactly the invariant. The case/whitespace variants are here because widening the compare
    to `egress.lower()` or `.strip()` reopens `"ALLOW"` and `"deny "` — `test_node_mxc.py` pins
    only the one spelling `'allow'`, and with no branch assertion. Inverting this branch is the
    single cheapest way to open the container."""
    refused(tmp_path, 'unsupported UI or egress', egress=egress)


def test_egress_allow_with_a_proxy_is_refused_too(tmp_path):
    """Row `network.egress.default` (**PINNED**, E:109-111: with `runtimeConfig.networkProxy`
    "Egress must default to deny, with no direct allow or deny rules"; S:116-117): a proxy is
    a broker, not a licence. `"allow"` beside a `proxy_url` is the policy that quietly makes
    the broker optional, so `egress` may not be used as a proxy knob."""
    refused(tmp_path, 'unsupported UI or egress', egress='allow',
            proxy_url='http://127.0.0.1:18080')


@pytest.mark.parametrize('ui', ['all', 'read', 'write', 'clipboard', 'none', 'allowWindows',
                               'True', 'true', 'False', 1, 0, 2, None, [], {}, (True,), 1.0])
def test_a_ui_value_outside_the_verified_two_is_refused(tmp_path, ui):
    """§D (**card**; boolean type PINNED S:454): the admissible `ui` values are the two
    measured over the ten-tool matrix (F:26-37). `"all"`, `"read"`, `"clipboard"` are clipboard
    enum values arriving in the wrong field, and `allowWindows` is the UNVERIFIED field P:407
    forbids in frozen policies — the seam must not let a caller reach it through `ui` either.
    `1` and `0` are the truthy non-booleans a plain `if ui:` test would silently accept, and
    `(True,)` the tuple that is truthy but is not `True`."""
    refused(tmp_path, 'unsupported UI or egress', ui=ui)


PROXY_BAD = [
    '', '   ', 'not a url', '127.0.0.1:18080', '127.0.0.1', '://nope', [],
    'http://10.0.0.1:8080', 'http://192.168.1.0:8080', 'http://169.254.1.1:9',
    'http://localhost:18080', 'http://example.invalid:8080', 'http://proxy:8080',
    'https://127.0.0.1:18080', 'ftp://127.0.0.1:21', 'socks5://127.0.0.1:1080',
    'http://127.0.0.1', 'http://127.0.0.1:0', 'http://127.0.0.1:99999',
    'http://user@127.0.0.1:18080', 'http://user:pw@127.0.0.1:18080',
    'http://127.0.0.1:18080/proxy', 'http://127.0.0.1:18080?x=1',
    'http://127.0.0.1:18080#f', 'http://0.0.0.0:9', 'http://[::ffff:0:0]:1',
]


@pytest.mark.parametrize('proxy', PROXY_BAD)
def test_a_proxy_that_is_not_an_explicit_loopback_http_endpoint_is_refused(tmp_path, proxy):
    """Row `runtimeConfig.networkProxy`, must-refuse column (**card**; grammar INFERRED from
    the two `http://127.0.0.1:<port>` examples S:140/P:216; the endpoint itself PINNED
    S:108-110 as a caller-managed *local* one): every entry below either names something that
    is not this machine's loopback — a routable address, a hostname DNS could answer
    differently later, another scheme — or names no endpoint at all (no port, port 0,
    credentials, a path, a query). Each is a route out of the deny posture, so an
    implementation that loosened the loopback test, trusted a hostname or allowed a path
    fails here. Whether the route must be loopback-only on *this* backend is Open item 3, and
    pinning the refusal is the safe direction. Three of these spellings appear in
    `test_invalid_policy_never_spawns` without a branch assertion; the rest, and the wording
    requirement, are what this case adds."""
    refused(tmp_path, 'loopback HTTP endpoint', proxy_url=proxy)


def test_a_proxy_that_is_not_a_string_refuses_as_a_policy_error(tmp_path):
    """Same row, type form: a non-string `proxy_url` is a caller mistake the seam must refuse
    in its own currency — every other bad proxy in the file above comes back as
    `MxcUnavailable`, and this one does not, which is the inconsistency the reason quotes."""
    refused(tmp_path, 'loopback HTTP endpoint', proxy_url=1)


@pytest.mark.parametrize('env', [
    ['SYSTEMROOT=C:\\Windows'],                                    # a block, not a mapping
    'SYSTEMROOT=C:\\Windows',                                      # a bare string
    1,                                                             # not a container
    ['SYSTEMROOT=C:\\Windows', 1],                                 # non-mapping members
    {'SYSTEMROOT': 'C:\\Windows'},                                 # omits LOCALAPPDATA S:368-371
    {'LOCALAPPDATA': 'C:\\cfg'},                                   # omits SYSTEMROOT S:368-371
    {'SYSTEMROOT': '', 'LOCALAPPDATA': 'C:\\cfg'},                 # present but names nothing
    {'SYSTEMROOT': None, 'LOCALAPPDATA': 'C:\\cfg'},               # not text
    {'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': 'C:\\cfg', 'TASK': 1},
    {'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': 'C:\\cfg', 'A=B': 'c'},
    {'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': 'C:\\cfg', '': 'c'},
    {'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': 'C:\\cfg', 'TA\x00SK': 'c'},
    {'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': 'C:\\cfg', 'TASK': 'a\x00b'},
])
def test_an_environment_the_container_cannot_use_is_refused(tmp_path, env):
    """Row `process.env` (S:207, S:356-366) plus the required-variable rule (PINNED S:368-371:
    the Windows process container needs `SYSTEMROOT` and `LOCALAPPDATA`, so a caller-owned block
    that omits them — including the empty one — is rejected before launch). The seam takes a
    mapping, so an entry with no `=` cannot even be formed; what must be refused is every shape
    that cannot launch or cannot be named: a block instead of a mapping, a non-text value, a
    key carrying `=` (which collides with the `KEY=value` spelling the backend parses), an empty
    key, a NUL anywhere (a truncation bug in whoever reads it next), and the two required
    variables missing or blank. A compiler that emitted one of these ships a policy that cannot
    start. `env=None` and the missing-`LOCALAPPDATA` spelling are already pinned in
    `test_node_mxc.py::test_invalid_policy_never_spawns`; the other twelve are new."""
    refused(tmp_path, 'explicit environment|SYSTEMROOT and LOCALAPPDATA', env=env)


def test_two_names_for_one_variable_are_refused(tmp_path):
    """Row `process.env` (**card**): with `inheritDefaultEnv: false` the child gets *only* the
    supplied entries (S:356-366), so two entries whose names differ only in case leave the
    value to whoever applies them last — a silent last-writer-wins on the environment is how a
    value Core reviewed stops being the value the child sees. `test_invalid_policy_never_spawns`
    carries the same shape with no branch assertion; the wording is what makes this a refusal
    for the right reason."""
    refused(tmp_path, 'SYSTEMROOT and LOCALAPPDATA',
            env={'SYSTEMROOT': 'C:\\Windows', 'systemroot': 'other',
                 'LOCALAPPDATA': 'C:\\cfg'})


@pytest.mark.parametrize('timeout', ['30000', '', 30.5, None, [], {}, -1, -5_000])
def test_a_timeout_that_is_not_a_budget_is_refused(tmp_path, timeout):
    """Row `process.timeout` (**card** for the types; `0` and `True` are already pinned in
    `test_node_mxc.py`, which is why they are not repeated here — `True` is the
    `bool`-is-`int` trap that would mean a 1 ms timeout and surface hours later as an
    unexplained kill): a string budget is no budget, a float is a value the launcher will not
    parse, and a negative budget means an execution that is already expired. Bounds themselves
    (`0` = no timeout, an upper limit) are the note's Open item 1 and stay untested."""
    refused(tmp_path, 'invalid process policy', timeout_ms=timeout)


@pytest.mark.parametrize('command', [None, 1, [], {}, b'cmd.exe /c echo x', ['cmd.exe']])
def test_a_command_line_that_is_not_a_command_is_refused(tmp_path, command):
    """Row `process.commandLine` (**PINNED** S:180-186, S:202: every complete request carrying
    a process requires a non-empty `commandLine`; the empty string is pinned in
    `test_node_mxc.py`). A list would be shell-interpreted by whoever consumes it, and `bytes`
    is the `os.fspath` trap again: it must not be carried into the document."""
    refused(tmp_path, 'invalid process policy', command_line=command)


# ── must refuse: the same gates on the launch path, after compilation ─────────────────

PROXY = 'http://127.0.0.1:18080'


def tamper(raw, path, value):
    """`raw['network']['ingress']['default'] = value`, spelled as data."""
    node = raw
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value


MUTATIONS = [
    ('ingress opened', {}, ('network', 'ingress', 'default'), 'allow', 'unsafe network policy'),
    ('host loopback opened', {}, ('network', 'ingress', 'hostLoopback'), 'allow',
     'unsafe network policy'),
    ('egress opened', {}, ('network', 'egress', 'default'), 'allow', 'unsafe network policy'),
    ('direct egress rule added', {}, ('network', 'egress', 'allow'),
     [{'to': [{'cidr': '0.0.0.0/0'}]}], 'unsafe network policy'),
    ('ingress closed under a proxy', {'proxy_url': PROXY}, ('network', 'ingress', 'default'),
     'deny', 'unsafe network policy'),
    ('proxy swapped to another host', {'proxy_url': PROXY},
     ('runtimeConfig', 'networkProxy'), 'http://10.0.0.1:8080', 'invalid proxy endpoint'),
    ('clipboard opened', {}, ('ui', 'clipboard'), 'all', 'unsafe UI or telemetry'),
    ('keystroke injection enabled', {}, ('ui', 'injection'), True, 'unsafe UI or telemetry'),
    ('telemetry enabled', {}, ('telemetry', 'enabled'), True, 'unsafe UI or telemetry'),
    ('unverified ui field', {}, ('ui', 'allowWindows'), True, 'unsafe UI or telemetry'),
    ('policy preserved after exit', {}, ('lifecycle', 'preservePolicy'), True, 'unsafe lifecycle'),
    ('container left behind', {}, ('lifecycle', 'destroyOnExit'), False, 'unsafe lifecycle'),
    ('identity claimed by the policy', {}, ('containerId',), 'core-assigned',
     'unknown or missing policy fields'),
    ('backend swapped', {}, ('containment',), 'hyperlight', 'wrong schema or backend'),
    ('schema version bumped', {}, ('version',), '1.0.1', 'wrong schema or backend'),
]


@pytest.mark.parametrize('label,changes,path,value,message', MUTATIONS)
def test_a_mutated_policy_is_refused_before_the_backend(tmp_path, label, changes, path, value,
                                                        message):
    """§A/§B, negative column on the launch path. `MxcPolicy` deep-copies `raw` and
    `validate_policy` re-checks the *exact* document at launch, because between compile and
    spawn the file sits somewhere the host can reach: every mutation above is a policy that a
    compiler-side check alone would not catch again — an opened ingress, host loopback, a
    clipboard, injection, telemetry, a preserved container (a grants set that outlives the
    execution, INFERRED from the T4 cleanup case F:11), a claimed `containerId`, a swapped
    backend, the `1.0.1` spelling the guide rejects (S:674). `test_node_mxc.py` pins this for
    one field (`inheritDefaultEnv`, :155); these are the fields whose failure is a security
    property."""
    policy = accepted(tmp_path, **changes)
    tamper(policy.raw, path, value)
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    with pytest.raises(ERROR, match='invalid MXC policy.*' + re.escape(message)):
        mxc.spawn(policy, exe='unused', job=object(), backend=fake)
    assert fake.calls == [], 'the backend was reached with %s' % label


@pytest.mark.parametrize('section,extra,message', [
    ('runtimeConfig', {'networkProxy': PROXY}, 'unknown or missing policy fields'),
    ('processContainer', {'capabilities': ['internetClient']}, 'unknown or missing policy fields'),
    ('fallback', {'allowDaclMutation': True}, 'unknown or missing policy fields'),
    ('lxc', {'distribution': 'ubuntu'}, 'unknown or missing policy fields'),
    ('wslc', {'image': 'wsl://x'}, 'unknown or missing policy fields'),
    ('seatbelt', {'guiAccess': True}, 'unknown or missing policy fields'),
    ('hyperlight', {'runtime': 'bash'}, 'unknown or missing policy fields'),
])
def test_a_smuggled_section_is_refused_before_the_backend(tmp_path, section, extra, message):
    """Rows §B (`fallback.allowDaclMutation`: accepted and ignored, S:305-309; the foreign
    backend sections: a backend section may only accompany its matching `containment`,
    S:401-403, and an unrelated one is a "Multiple containment backends configured" rejection,
    S:505-507). A field that makes a policy *look* like it asked for a Dacl mutation while
    selecting nothing is a claim the compiler never earned, and `wslc` is the "run it in WSL
    instead" degradation F:54-57 warns about by naming what the container does not enforce."""
    policy = accepted(tmp_path)
    policy.raw[section] = extra
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    with pytest.raises(ERROR, match=message):
        mxc.spawn(policy, exe='unused', job=object(), backend=fake)
    assert fake.calls == []


def test_a_writable_grant_added_after_compile_is_refused_before_the_backend(tmp_path):
    """§D on the launch path: the overlap gate is not a compile-time-only courtesy. Appending
    the denied directory to `readwritePaths` after compilation is exactly the widening the file
    exists to prevent, and the same branch that refuses it at compile refuses it again at
    `spawn`, before the backend is reached."""
    made = dirs(tmp_path)
    policy = accepted(tmp_path, denied=(made['core-private'],))
    policy.raw['filesystem']['readwritePaths'].append(made['core-private'])
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    with pytest.raises(ERROR, match='overlaps protected'):
        mxc.spawn(policy, exe='unused', job=object(), backend=fake)
    assert fake.calls == []


# Structure of the document, re-checked at launch. Each value is what whoever held the file
# could write into it; each message names the branch that must catch it.
TAMPERED = {
    'environment entry with no equals': (
        ('process', 'env'), lambda m: ['SYSTEMROOT=C:\\Windows', 'LOCALAPPDATA=C:\\cfg', 'GATEWAY'],
        'invalid environment entry'),
    'blank environment entry': (
        ('process', 'env'),
        lambda m: ['', 'SYSTEMROOT=C:\\Windows', 'LOCALAPPDATA=C:\\cfg'],
        'invalid environment entry'),
    'environment entry without a name': (
        ('process', 'env'),
        lambda m: ['=x', 'SYSTEMROOT=C:\\Windows', 'LOCALAPPDATA=C:\\cfg'],
        'duplicate environment entry'),
    'environment variable named twice': (
        ('process', 'env'),
        lambda m: ['SYSTEMROOT=a', 'systemroot=b', 'LOCALAPPDATA=c'],
        'duplicate environment entry'),
    'required variable blanked': (
        ('process', 'env'), lambda m: ['SYSTEMROOT=', 'LOCALAPPDATA=C:\\cfg'],
        'SYSTEMROOT and LOCALAPPDATA'),
    'required variable dropped': (
        ('process', 'env'), lambda m: ['SYSTEMROOT=C:\\Windows'], 'SYSTEMROOT and LOCALAPPDATA'),
    'environment forged as a string': (
        ('process', 'env'), lambda m: 'SYSTEMROOT=C:\\Windows', 'invalid process policy'),
    'writable grant named twice': (
        ('filesystem', 'readwritePaths'), lambda m: [m['work'], m['work']],
        'duplicate or invalid paths'),
    'read-only grant named twice': (
        ('filesystem', 'readonlyPaths'), lambda m: [m['runtime'], m['runtime']],
        'duplicate or invalid paths'),
    'denied grant named twice': (
        ('filesystem', 'deniedPaths'),
        lambda m: [m['core-private'], m['core-private']], 'duplicate or invalid paths'),
    'filesystem section grew a field': (
        ('filesystem', 'allowDaemonPaths'), lambda m: [], 'invalid filesystem policy'),
}


@pytest.mark.parametrize('label', sorted(TAMPERED))
def test_a_tampered_structure_is_refused_before_the_backend(tmp_path, label):
    """Rows §B/§C/§D on the launch path: `validate_policy` re-checks the *document*, not the
    caller's intentions — the grant lists must still be duplicate-free (`duplicate or invalid
    paths`: two entries for one directory is a policy whose meaning depends on which one the
    backend reads first), the environment block must still be `KEY=value` text with one name
    per variable and both required variables carrying a value (S:368-371), and the filesystem
    section may not have grown a field nobody named. `test_node_mxc.py` pins the launch-path
    refusal for one policy-level lie (`inheritDefaultEnv`, :155); the branches here are the ones
    a hand-edited policy file reaches."""
    made = dirs(tmp_path)
    path, build, message = TAMPERED[label]
    policy = accepted(tmp_path, denied=(made['core-private'],))
    tamper(policy.raw, path, build(made))
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    with pytest.raises(ERROR, match='invalid MXC policy.*' + re.escape(message)):
        mxc.spawn(policy, exe='unused', job=object(), backend=fake)
    assert fake.calls == [], 'the backend was reached after ' + label


def test_the_scan_runs_again_at_launch_on_every_grant(tmp_path):
    """§C row 4 on the launch path (F:57: scan before grant *and* re-scan at launch): a link
    created after compilation, while the policy sat on disk, is caught at `spawn`. The draft
    could only ask for this; the seam has the hook, so the case is pinned for the writable
    grant, the second writable grant and the read-only grant alike."""
    made = dirs(tmp_path)
    second = make(tmp_path, 'requests')
    protected = make(tmp_path, 'runtime/reader')
    outside = make(tmp_path, 'secret-outside', 'file')
    policy = accepted(tmp_path, workspace=[made['work'], second], readonly=(protected,))
    for root in (made['work'], second, protected):
        link_at(os.path.join(root, 'late-alias'), outside, os.link, 'hardlink')
        fake = mxc.FakeMxc([mxc.FakeOutcome()])
        with pytest.raises(ERROR, match='multiple links'):
            mxc.spawn(policy, exe='unused', job=object(), backend=fake)
        assert fake.calls == [], 'the backend was reached with a link in %s' % root
        os.unlink(os.path.join(root, 'late-alias'))
