"""P20 slice I, D7: every secret Archeus writes at rest, by writer and protection.

The signal is the CSPRNG call: a credential Archeus issues has to be drawn from
`secrets` or `os.urandom`, so a new secret cannot appear without a new call site
here, and every call site must say where its value goes (p20-design-gate §12,
slice I). A grep for file writes would be wider and still miss a secret that
reaches disk through a helper; the draw is where every one of them starts.
`auth.new_token()` is a second draw point by construction (one call, many
uses), so its callers are held to the same table.
"""

import ast
import os

import pytest

from archeus.core.application import commands
from archeus.core.domain import entities, ids
from archeus.infra.db import writer

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PKG = os.path.join(ROOT, 'archeus')

DRAWS = {('secrets', a) for a in ('token_urlsafe', 'token_bytes', 'token_hex', 'randbits',
                                  'randbelow', 'choice', 'SystemRandom')} | {('os', 'urandom')}

AT_REST = 'secret at rest'
MEMORY = 'secret, memory only'
FLOW = 'secret, not stored by Archeus'
NOT_SECRET = 'not a secret'

#: (file, enclosing qualname, draw) -> (disposition, where it goes)
SITES = {
    ('archeus/api/auth.py', 'new_token', 'secrets.token_urlsafe'):
        (FLOW, 'a device token; its callers are NEW_TOKEN_CALLERS'),
    ('archeus/api/auth.py', 'LaunchCodes._mint', 'secrets.token_urlsafe'):
        (MEMORY, 'launch and pairing codes, kept as sha256 keys in the process'),
    ('archeus/core/execution/manager.py', 'ExecutionManager._spawn', 'secrets.token_urlsafe'):
        (AT_REST, 'the hook token: env of the child; sha256 in executions.hook_token_hash, '
                  'cleared on every end path; plaintext in run/exec/<id>/req/<seq>.req.json, '
                  'written by the hook, dead once the hash is cleared'),
    ('archeus/core/application/commands.py', 'hash_pin', 'secrets.token_bytes'):
        (AT_REST, 'the salt of a step-up PIN record, pbkdf2_sha256 in devices.pin_hash'),
    ('archeus/api/server.py', 'translate', 'secrets.token_hex'):
        (NOT_SECRET, 'the reference of a 500 answer, logged and returned'),
    ('archeus/api/server.py', 'Api.__init__', 'secrets.token_hex'):
        (NOT_SECRET, "the Core process's instance id"),
    ('archeus/core/domain/ids.py', 'new_ulid', 'secrets.randbits'):
        (NOT_SECRET, 'ULID entropy'),
    ('archeus/node/staging.py', 'stage', 'os.urandom'):
        (NOT_SECRET, 'a temporary directory name'),
    ('archeus/cli/gui.py', 'Shell.pause_all', 'os.urandom'):
        (NOT_SECRET, 'an idempotency key'),
}
#: every `os.urandom` in archeus/cli/main.py is an idempotency key or request id
CLI_KEYS = 'archeus/cli/main.py'

#: who turns `auth.new_token()` into a credential, and where its plaintext goes
NEW_TOKEN_CALLERS = {
    ('archeus/api/routes.py', 'launch_redeem'): 'returned once to the client; sha256 in tokens',
    ('archeus/api/routes.py', 'pair_redeem'): 'returned once to the client; sha256 in tokens',
    ('archeus/core/runtime.py', 'Core._ensure_local_token'):
        'run/local-token, plaintext, O_EXCL 0600 (discovery.write_local_token); sha256 in tokens',
}


def _calls(match):
    """[(file, qualname, node)] of every Call in archeus/ that *match* accepts."""
    out = []
    for dirpath, dirs, files in os.walk(PKG):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for name in files:
            if not name.endswith('.py'):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
            with open(path, encoding='utf-8') as f:
                tree = ast.parse(f.read())

            def walk(node, stack, rel=rel):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    stack = stack + [node.name]
                if isinstance(node, ast.Call) and match(node.func):
                    out.append((rel, '.'.join(stack), node))
                for child in ast.iter_child_nodes(node):
                    walk(child, stack, rel)
            walk(tree, [])
    return out


def _draw(func):
    return (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
            and (func.value.id, func.attr) in DRAWS)


def test_every_random_draw_in_archeus_is_in_the_secrets_table():
    seen = {(rel, qual, '%s.%s' % (n.func.value.id, n.func.attr))
            for rel, qual, n in _calls(_draw) if rel != CLI_KEYS}
    assert seen - set(SITES) == set(), 'a new random draw: say where its value goes'
    assert set(SITES) - seen == set(), 'a table row whose draw is gone'


def test_the_cli_draws_only_idempotency_keys_and_request_ids():
    for rel, qual, n in _calls(_draw):
        if rel == CLI_KEYS:
            assert n.func.attr == 'urandom'


def test_every_caller_of_new_token_is_in_the_table():
    def new_token(func):
        return ((isinstance(func, ast.Attribute) and func.attr == 'new_token')
                or (isinstance(func, ast.Name) and func.id == 'new_token'))
    seen = {(rel, qual) for rel, qual, _ in _calls(new_token)}
    assert seen == set(NEW_TOKEN_CALLERS)


def _func(rel, name):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        tree = ast.parse(f.read())
    return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)


def test_the_local_token_file_is_created_exclusively_and_owner_only():
    """The one plaintext credential Archeus writes itself. POSIX also has a
    behavioural test (test_core_lifecycle); this one holds on Windows too."""
    fn = _func('archeus/infra/discovery.py', 'write_local_token')
    opens = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == 'open' and getattr(n.func.value, 'id', None) == 'os']
    assert len(opens) == 1
    flags, mode = opens[0].args[1], opens[0].args[2]
    assert {a.attr for a in ast.walk(flags) if isinstance(a, ast.Attribute)} >= {'O_CREAT', 'O_EXCL'}
    assert isinstance(mode, ast.Constant) and mode.value == 0o600


def test_device_and_hook_credentials_are_stored_as_hashes_only():
    params = [a.arg for a in _func('archeus/infra/db/writer.py', 'insert_token').args.kwonlyargs]
    assert 'token_hash' in params and not [p for p in params if p in ('token', 'secret', 'code')]
    assert hasattr(writer.Tx, 'insert_token')
    fields = {f for f in entities.Execution.__dataclass_fields__ if 'token' in f}
    assert fields == {'hook_token_hash'}


def test_a_step_up_pin_is_kept_only_as_a_pbkdf2_record():
    rec = commands.hash_pin('2468')
    assert entities.PIN_HASH.fullmatch(rec) and '2468' not in rec
    assert commands.PIN_ITERATIONS >= 200_000
    entities.Device(id=ids.new_id('device'), principal_id=ids.new_id('principal'), name='x',
                    platform='web', pin_hash=rec)
    with pytest.raises(ValueError, match='pin_hash is not a pbkdf2'):
        entities.Device(id=ids.new_id('device'), principal_id=ids.new_id('principal'),
                        name='x', platform='web', pin_hash='2468')
