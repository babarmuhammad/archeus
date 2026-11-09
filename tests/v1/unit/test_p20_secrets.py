"""P20 slice I, D7: every secret Archeus writes at rest, by writer and protection.

Two censuses over archeus/, both exact (p20-design-gate §12 items 109 and 120):

1. SOURCES. Every call that draws randomness or issues a credential:
   `secrets.*`, `os.urandom`, `uuid.uuid4`, `random.SystemRandom` and
   `auth.new_token`, in any import form (`import secrets as s`,
   `from secrets import token_hex`, `from .auth import new_token as nt`,
   `import archeus.api.auth` then `archeus.api.auth.new_token()`), counted
   per (file, function, source). A second draw in a listed function changes a
   count, a new one adds a row, and either fails until the table says where
   the value goes. The CLI's draws are idempotency keys and request ids.
2. SECRET WRITES. Inside each function, a value is a secret when it comes from
   a secret source call, from an external secret (an opted-in MCP server's
   definition, the hook token read back from the environment), from a
   parameter named in WRITER_PARAMS, or from an assignment over such a value.
   A secret write is a sink call with a secret among its arguments:
   `json.dump`; `write_atomic` and `write_json_atomic` in any dotted form
   (`config.write_json_atomic`); any `.write`, `.writelines`, `.write_text`
   or `.write_bytes`; `print(..., file=...)`; a logging call on a logger
   (`log.info`, `logging.warning`, `self._log.error`: core.log is a file); a
   call to a WRITER_PARAMS helper. A helper's return value is not a secret.
   In a scope that writes a secret, every file copy (`shutil.copy*`,
   `os.link`) is one more secret write: a copy of the file just written.
   Each scope's count (module, class body or function, lambdas included) must
   equal WRITERS: a token copied to a second file is a second write.
   And no code in archeus/ changes a file's mode, in any import form: `chmod`
   and friends, `shutil.copymode`/`copystat`, and the shutil copies that carry
   mode bits. A mode loosened after an exclusive create would undo it.

What this does NOT see, by construction: a secret kept on an attribute or in
a container and written by another scope; a secret passed to a function that
is not a WRITER_PARAMS helper and written there (one hop only); a write
through a subprocess or a shell; a secret read from a source not named here
(a new external file); a copy, rename or move of a secret file by a scope that
did not write it; a logger the code does not name with "log"; a secret in a
database row (the hash tests below pin only insert_token's signature and the
Execution's token fields); ACL changes (test_pv20_isolation's static gate
holds those). The runtime gate (tests/v1/integration/test_p20_secrets_runtime.py)
reads every file Core leaves behind, the database included, for the secrets it
actually minted: it covers whatever the lifecycle it drives runs, in any
syntax. This census over-counts on purpose: anything computed from a secret
(a hash included) is treated as one.
"""

import ast
import collections
import os

import pytest

from archeus.core.application import commands
from archeus.core.domain import entities, ids
from archeus.infra.db import writer

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PKG = os.path.join(ROOT, 'archeus')

SOURCES = {'secrets.' + a for a in ('token_urlsafe', 'token_bytes', 'token_hex', 'randbits',
                                    'randbelow', 'choice', 'SystemRandom')} | {
    'os.urandom', 'uuid.uuid4', 'random.SystemRandom', 'auth.new_token'}

AT_REST = 'secret at rest'
MEMORY = 'secret, memory only'
FLOW = 'secret, not stored by Archeus'
NOT_SECRET = 'not a secret'
SECRET = (AT_REST, MEMORY, FLOW)

#: (file, enclosing qualname, source) -> (count, disposition, where it goes)
SITES = {
    ('archeus/api/auth.py', 'new_token', 'secrets.token_urlsafe'):
        (1, FLOW, 'a device token; its callers are the auth.new_token rows'),
    ('archeus/api/auth.py', 'LaunchCodes._mint', 'secrets.token_urlsafe'):
        (1, MEMORY, 'launch and pairing codes, kept as sha256 keys in the process'),
    ('archeus/api/routes.py', 'launch_redeem', 'auth.new_token'):
        (1, FLOW, 'returned once to the client; sha256 in tokens'),
    ('archeus/api/routes.py', 'pair_redeem', 'auth.new_token'):
        (1, FLOW, 'returned once to the client; sha256 in tokens'),
    ('archeus/core/runtime.py', 'Core._ensure_local_token', 'auth.new_token'):
        (1, AT_REST, 'run/local-token, plaintext (discovery.write_local_token); sha256 in tokens'),
    ('archeus/core/execution/manager.py', 'ExecutionManager._spawn', 'secrets.token_urlsafe'):
        (1, AT_REST, 'the hook token: env of the child; sha256 in executions.hook_token_hash, '
                     'cleared on every end path; plaintext in run/exec/<id>/req/<seq>.req.json, '
                     'written by the hook beside the raw tool input, dead once the hash is cleared'),
    ('archeus/core/application/commands.py', 'hash_pin', 'secrets.token_bytes'):
        (1, AT_REST, 'the salt of a step-up PIN record, pbkdf2_sha256 in devices.pin_hash'),
    ('archeus/infra/discovery.py', 'public_account_secret', 'secrets.token_bytes'):
        (1, AT_REST, 'run/public-account-secret, 32 raw bytes: the HMAC key of the public account ids; '
                     'never in a row, ledger, snapshot, event, log or response'),
    ('archeus/api/server.py', 'translate', 'secrets.token_hex'):
        (1, NOT_SECRET, 'the reference of a 500 answer, logged and returned'),
    ('archeus/api/server.py', 'Api.__init__', 'secrets.token_hex'):
        (1, NOT_SECRET, "the Core process's instance id"),
    ('archeus/core/domain/ids.py', 'new_ulid', 'secrets.randbits'):
        (3, NOT_SECRET, 'ULID entropy'),
    ('archeus/node/staging.py', 'stage', 'os.urandom'):
        (1, NOT_SECRET, 'a temporary directory name'),
    ('archeus/cli/gui.py', 'Shell.pause_all', 'os.urandom'):
        (1, NOT_SECRET, 'an idempotency key'),
    ('archeus/harnesses/claude_code/adapter.py', 'ClaudeCodeAdapter.start', 'uuid.uuid4'):
        (1, NOT_SECRET, "a new provider session's id"),
    ('archeus/harnesses/sessions.py', 'FakeSessions.launch_argv', 'uuid.uuid4'):
        (1, NOT_SECRET, "the fake harness's session ref"),
    ('archeus/cli/tui/sync.py', 'new_key', 'uuid.uuid4'):
        (1, NOT_SECRET, 'an idempotency key'),
    ('archeus/cli/tui/screens.py', 'session_insp', 'uuid.uuid4'):
        (2, NOT_SECRET, 'the request ids of the Resume and Hand off actions'),
}
#: every source in archeus/cli/main.py is an `os.urandom` idempotency key or request id
CLI_KEYS = 'archeus/cli/main.py'

#: secrets Archeus copies in from outside: a call by this name, or this constant
EXTERNAL_CALLS = {'mcp_config'}       # an opted-in MCP server's full definition (T-099)
EXTERNAL_CONSTANTS = {'ARCHEUS_HOOK_TOKEN'}

#: helpers that write the secret they are given: (file, function) -> secret parameters
WRITER_PARAMS = {
    ('archeus/infra/discovery.py', 'write_local_token'): {'token'},
    ('archeus/harnesses/hook.py', '_reserve'): {'body'},
}

#: (file, qualname) -> (the number of secret writes in it, what they are)
WRITERS = {
    ('archeus/infra/discovery.py', 'write_local_token'):
        (1, 'run/local-token, os.open O_CREAT|O_EXCL mode 0o600; on Windows the home DACL'),
    ('archeus/infra/discovery.py', 'public_account_secret'):
        (1, 'run/public-account-secret, os.open O_CREAT|O_RDWR|O_BINARY mode 0o600 under a lock; '
            'on Windows the home DACL'),
    ('archeus/core/runtime.py', 'Core._ensure_local_token'):
        (1, 'hands the new local token to write_local_token'),
    ('archeus/harnesses/hook.py', '_reserve'):
        (1, 'run/exec/<id>/req/<seq>.req.json: the hook token and the raw tool input'),
    ('archeus/harnesses/hook.py', 'run'):
        (1, 'hands the hook token and the tool input to _reserve'),
    ('archeus/harnesses/sources.py', 'flag_argv'):
        (1, "run/exec/<id>/res/mcp.json: opted-in MCP servers' env and headers (third-party "
            'keys), kept only while the execution runs (T-099)'),
}

_FILE_SINKS = {'json.dump'}
#: matched on the last segment: archeus calls them `config.write_atomic(...)`
_HELPER_SINKS = {'write_atomic', 'write_json_atomic'}
_METHOD_SINKS = {'write', 'write_text', 'write_bytes', 'writelines'}
#: `log.info(...)`, `logging.warning(...)`, `self._log.error(...)`: core.log is a file
_LOG_METHODS = {'debug', 'info', 'warning', 'warn', 'error', 'exception', 'critical', 'log'}
#: a file copied in a scope that writes a secret is a second copy of it
_COPIES = {'shutil.copy', 'shutil.copyfile', 'shutil.copy2', 'os.link'}
_MODE_CHANGES = {'chmod', 'fchmod', 'lchmod', 'copymode', 'copystat'}
_MODE_COPIES = {'shutil.copy', 'shutil.copy2'}           # these copy the mode bits too


def _modules():
    for dirpath, dirs, files in os.walk(PKG):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for name in files:
            if name.endswith('.py'):
                path = os.path.join(dirpath, name)
                with open(path, encoding='utf-8') as f:
                    yield os.path.relpath(path, ROOT).replace(os.sep, '/'), ast.parse(f.read())


def _aliases(tree):
    """local name -> dotted name, from every import anywhere in the module."""
    out = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                out[a.asname or a.name.split('.')[0]] = a.name if a.asname else a.name.split('.')[0]
        elif isinstance(n, ast.ImportFrom):
            base = (n.module or '').split('.')[-1]
            for a in n.names:
                out[a.asname or a.name] = '%s.%s' % (base, a.name) if base else a.name
    return out


def _name(func, aliases):
    """The callee as its last two dotted parts with aliases resolved, through a
    dotted chain of any length (`archeus.api.auth.new_token`); '.attr' for a
    method of anything that is not a name or a chain of names; None otherwise."""
    if isinstance(func, ast.Name):
        full = aliases.get(func.id, func.id)
    elif isinstance(func, ast.Attribute):
        chain, base = [func.attr], func.value
        while isinstance(base, ast.Attribute):
            chain.append(base.attr)
            base = base.value
        if not isinstance(base, ast.Name):
            return '.' + func.attr
        full = '.'.join([aliases.get(base.id, base.id)] + chain[::-1])
    else:
        return None
    parts = full.split('.')
    if parts[-1] == 'new_token' and (len(parts) == 1 or parts[-2] == 'auth'):
        return 'auth.new_token'
    return '.'.join(parts[-2:])


def _scopes(tree):
    """[(qualname, node)] of the module ('') and every class and function in it,
    named through their enclosing classes and functions."""
    out = [('', tree)]

    def walk(node, stack):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out.append(('.'.join(stack + [child.name]), child))
                walk(child, stack + [child.name])
            else:
                walk(child, stack)
    walk(tree, [])
    return out


def _own(scope):
    """The nodes of *scope* itself (its lambdas included), not of the functions
    or classes defined in it."""
    todo, out = list(ast.iter_child_nodes(scope)), []
    while todo:
        n = todo.pop()
        out.append(n)
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            todo.extend(ast.iter_child_nodes(n))
    return out


_HELPERS = {f for _, f in WRITER_PARAMS}


def _secret(expr, tainted, secret_calls, aliases):
    """Does *expr* hold a secret? A writer helper's return value does not."""
    todo = [expr]
    while todo:
        n = todo.pop()
        if (isinstance(n, ast.Name) and n.id in tainted) or id(n) in secret_calls:
            return True
        if isinstance(n, ast.Constant) and n.value in EXTERNAL_CONSTANTS:
            return True
        if not (isinstance(n, ast.Call)
                and (_name(n.func, aliases) or '').split('.')[-1] in _HELPERS):
            todo.extend(ast.iter_child_nodes(n))
    return False


def _census():
    sources, writes = collections.Counter(), collections.Counter()
    for rel, tree in _modules():
        aliases = _aliases(tree)
        for qual, fn in _scopes(tree):
            nodes = _own(fn)
            calls = [n for n in nodes if isinstance(n, ast.Call)]
            secret_calls = set()
            for c in calls:
                src = _name(c.func, aliases)
                if src in SOURCES:
                    sources[(rel, qual, src)] += 1
                    row = SITES.get((rel, qual, src))
                    if (row[1] in SECRET) if row else rel != CLI_KEYS:
                        secret_calls.add(id(c))
                elif src and src.split('.')[-1] in EXTERNAL_CALLS:
                    secret_calls.add(id(c))
            tainted = set(WRITER_PARAMS.get((rel, getattr(fn, 'name', '')), ()))
            for _ in range(4):           # a short fixpoint over the assignments
                for n in nodes:
                    if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                        if n.value is not None and _secret(n.value, tainted, secret_calls, aliases):
                            for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                                tainted |= {x.id for x in ast.walk(t) if isinstance(x, ast.Name)}
                    elif isinstance(n, ast.withitem) and n.optional_vars is not None:
                        if _secret(n.context_expr, tainted, secret_calls, aliases):
                            tainted |= {x.id for x in ast.walk(n.optional_vars)
                                        if isinstance(x, ast.Name)}
            found = copies = 0
            for c in calls:
                callee = _name(c.func, aliases) or ''
                head, _, last = callee.rpartition('.')
                sink = (callee in _FILE_SINKS or last in _HELPER_SINKS or last in _HELPERS
                        or (isinstance(c.func, ast.Attribute) and c.func.attr in _METHOD_SINKS)
                        or (callee == 'print' and any(k.arg == 'file' for k in c.keywords))
                        or (last in _LOG_METHODS and 'log' in head.lower()))
                args = list(c.args) + [k.value for k in c.keywords]
                if sink and any(_secret(a, tainted, secret_calls, aliases) for a in args):
                    found += 1
                copies += callee in _COPIES
            if found:
                writes[(rel, qual)] += found + copies
    return sources, writes


@pytest.fixture(scope='module')
def census():
    return _census()


def test_every_source_in_archeus_is_in_the_secrets_table_with_its_count(census):
    seen = {k: v for k, v in census[0].items() if k[0] != CLI_KEYS}
    want = {k: v[0] for k, v in SITES.items()}
    assert {k: v for k, v in seen.items() if want.get(k) != v} == {}, \
        'a new or extra source: say where its value goes'
    assert set(want) - set(seen) == set(), 'a table row whose source is gone'


def test_the_cli_draws_only_idempotency_keys_and_request_ids(census):
    assert {k[2] for k in census[0] if k[0] == CLI_KEYS} <= {'os.urandom'}


def test_every_secret_write_in_archeus_is_in_the_writers_table(census):
    assert dict(census[1]) == {k: v[0] for k, v in WRITERS.items()}, \
        'a secret reaches a file: say where and how it is protected'


def test_no_code_in_archeus_changes_a_files_mode():
    """`chmod` and friends in any import form (`from os import chmod as ch`),
    and the shutil copies that carry mode bits onto their target."""
    found = []
    for rel, tree in _modules():
        aliases = _aliases(tree)
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                callee = _name(n.func, aliases) or ''
                if callee.rpartition('.')[2] in _MODE_CHANGES or callee in _MODE_COPIES:
                    found.append((rel, n.lineno, callee))
    assert found == []


def _func(rel, name):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        tree = ast.parse(f.read())
    return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)


def test_the_local_token_file_is_created_exclusively_with_a_posix_owner_only_mode():
    """The POSIX mode literal is checked on every platform. On Windows os.open's
    mode only sets the read-only attribute, so the file's protection there is
    the home DACL (I-F1, T-096); test_core_lifecycle holds the POSIX behaviour."""
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
