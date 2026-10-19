"""P20 slice I, D7 at runtime: the secrets Core actually mints, searched for in
every byte it leaves under ARCHEUS_HOME (p20-design-gate §12 items 109, 120).

tests/v1/unit/test_p20_secrets.py reads the source, so it sees only the
syntax it was taught. This drives Core through its lifecycle and catches every
mint where it happens: each `secrets.token_urlsafe` call (device tokens, the
local token, launch and pairing codes, the hook token) is recorded with its
kind, decided by the function that asked for it. Third-party keys an opted-in
MCP server carries, and an account's own settings secrets, are planted. Then
every file under ARCHEUS_HOME is read as bytes (the SQLite database and its
WAL, core.log and every execution file included), and each secret may appear
only where ALLOWED says its kind is kept. Any other hit fails, whatever wrote
it and in whatever syntax.

It covers what these lifecycles run: pairing, a launch-code redemption, a
revocation, a stream, a mission, and an execution with an opted-in MCP server
and a hooked tool call. Code that no lifecycle here reaches is the static
census's to see.
"""

import fnmatch
import os
import secrets
import sys

import pytest

from archeus.harnesses import base, sources
from archeus.harnesses.fake import FakeHarness
from archeus.core.application import world
from archeus.infra import paths

from v1.integration.test_execution import TOOL, DONE, Rig
from v1.integration.test_policy import task
from v1.integration.test_settings_sources import _git_commit, _write, opt, ready_in, run_one
from v1.judge.http import SSEClient, request

#: kind -> the only files (relative to ARCHEUS_HOME) its plaintext may be in
ALLOWED = {
    'local': ('run/local-token',),
    'hook': ('run/exec/*/req/*.req.json',),
    # only while its execution runs: T-099 deletes it when the execution ends
    'mcp': ('run/exec/*/res/mcp.json',),
}
#: the function that asked for a token -> what it is
MINTERS = {'_ensure_local_token': 'local', '_spawn': 'hook', '_mint': 'code',
           'pair_redeem': 'device', 'launch_redeem': 'device'}

MCP_ENV_KEY = 'mcpenv-' + 'k' * 28
MCP_HEADER_KEY = 'mcphdr-' + 'h' * 28
SETTINGS_KEY = 'sk-' + 'q' * 30


@pytest.fixture
def minted(monkeypatch):
    """[(kind, value)] of every token_urlsafe drawn from now on; a draw no
    MINTERS function asked for is 'unknown', which is allowed nowhere."""
    got, real = [], secrets.token_urlsafe

    def spy(*a, **k):
        value, f, kind = real(*a, **k), sys._getframe(1), None
        while f is not None and kind is None:
            kind, f = MINTERS.get(f.f_code.co_name), f.f_back
        got.append((kind or 'unknown', value))
        return value
    monkeypatch.setattr(secrets, 'token_urlsafe', spy)
    return got


def leaks(found):
    """[(kind, file)] of every secret found outside the files its kind may be in."""
    home, bad = str(paths.archeus_home()), set()
    for d, _dirs, files in os.walk(home):
        for name in files:
            path = os.path.join(d, name)
            rel = os.path.relpath(path, home).replace(os.sep, '/')
            try:
                with open(path, 'rb') as f:
                    data = f.read()
            except OSError:                 # a file that went while walking
                continue
            for kind, value in found:
                if value.encode('utf-8') in data and not any(
                        fnmatch.fnmatch(rel, g) for g in ALLOWED.get(kind, ())):
                    bad.add((kind, rel))
    return sorted(bad)


def test_no_minted_credential_is_at_rest_outside_its_one_home(minted, tc):
    local = tc.token                       # minted at start, before `minted` could see it
    code = tc.http('POST', '/v1/devices/pair/start', body={'name': 'phone'}).json()['code']
    paired = request(tc.base_url, 'POST', '/v1/devices/pair/redeem',
                     body={'code': code, 'platform': 'android', 'pin': '482913'}).json()
    launch = tc.http('POST', '/v1/devices/launch/code', body={}).json()['code']
    page = tc.http('POST', '/v1/devices/launch/redeem',
                   body={'code': launch, 'platform': 'web', 'name': 'laptop'}).json()
    tc.http('POST', '/v1/missions', token=paired['token'],
            body={'title': 't', 'objective': 'o', 'idempotency_key': 'a'})
    s = SSEClient(tc.base_url, page['token'])
    s.close()
    tc.http('POST', '/v1/devices/%s/revoke' % paired['device_id'],
            body={'idempotency_key': 'r'})
    tc.stop()
    found = list(minted) + [('local', local)]
    kinds = {k for k, _v in found}
    assert {'local', 'code', 'device'} <= kinds, kinds        # the lifecycle minted each
    # a token is a prefix plus the draw: the scan looks for the draw itself
    assert all(any(v in t for k, v in found if k == 'device')
               for t in (paired['token'], page['token']))
    assert leaks(found) == []
    with open(os.path.join(str(paths.archeus_home()), 'run', 'local-token'),
              encoding='utf-8') as f:
        assert f.read() == local                               # its one plaintext home


@pytest.fixture
def rig(db, tmp_path, monkeypatch):
    """An account whose home holds two MCP servers carrying third-party keys (an
    env var, an HTTP header) and settings with a secret of their own; a
    project that is a git repository."""
    monkeypatch.setattr(sources, 'MANAGED', str(tmp_path / 'no-managed.json'))
    home, root = str(tmp_path / 'home'), str(tmp_path / 'proj')
    _write(os.path.join(home, '.claude.json'), {'mcpServers': {
        'gh': {'command': 'gh-mcp', 'env': {'GH_TOKEN': MCP_ENV_KEY}},
        'api': {'type': 'http', 'url': 'https://mcp.example.com',
                'headers': {'Authorization': 'Bearer ' + MCP_HEADER_KEY}}}})
    _write(os.path.join(home, 'settings.json'), {'env': {'K': SETTINGS_KEY}})
    _write(os.path.join(root, 'README.md'), {'readme': True})
    _git_commit(root)
    x = Rig(db, adapters=[FakeHarness(sources=True)])
    x.acc = x.account('Work', home_ref=home)
    x.prj = x.do(world.create_project, who=x.user, name='p', root_paths=[root])['project']['id']
    yield x
    x.cleanup()


def test_an_execution_leaves_its_hook_token_and_mcp_keys_only_where_they_are_kept(
        minted, rig, monkeypatch):
    opt(rig, rig.acc, 'mcp', 'gh')
    opt(rig, rig.acc, 'mcp', 'api')
    rig.scenarios['t1'] = [TOOL('Read', {'file_path': 'README.md'}), DONE]
    planted = [('mcp', MCP_ENV_KEY), ('mcp', MCP_HEADER_KEY), ('settings', SETTINGS_KEY)]
    live = []                                     # the scan while the config still exists
    drop = base.drop_mcp_config

    def scan_then_drop(p):
        now = list(minted) + planted              # the hook token is minted at spawn
        live.append(({k for k, _rel in _hits(now)}, leaks(now)))
        return drop(p)
    monkeypatch.setattr(base, 'drop_mcp_config', scan_then_drop)
    e = run_one(rig, ready_in(rig, rig.prj, task('t1', 'read')))
    assert e.state == 'ENDED_OK'
    found = list(minted) + planted
    assert 'hook' in {k for k, _v in found}
    assert live, 'the execution ended without dropping its MCP config'
    hits, leaked = live[0]
    assert {'hook', 'mcp'} <= hits, hits          # each kind was written where it is kept
    assert leaked == []
    assert 'mcp' not in {k for k, _rel in _hits(found)}   # gone once the execution ended
    assert leaks(found) == []


def _hits(found):
    """[(kind, file)] of every secret found anywhere: the check that the scan
    sees the files it is meant to, not only that it finds nothing."""
    home, out = str(paths.archeus_home()), []
    for d, _dirs, files in os.walk(home):
        for name in files:
            path = os.path.join(d, name)
            with open(path, 'rb') as f:
                data = f.read()
            out += [(k, path) for k, v in found if v.encode('utf-8') in data]
    return out
