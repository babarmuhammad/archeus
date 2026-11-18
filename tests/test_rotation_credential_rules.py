"""T-1100: account rotation handles no credential, pinned by reading the source (no execution).

Why this exists. Anthropic's legal-and-compliance page says developers "may not collect,
store, or intermediate Claude.ai credentials or session tokens" (quoted by
RESEARCH-trends-2026-11-09.md; the page itself was not re-read for this card). An OAuth
refresh also rotates the refresh token, so a second program refreshing Claude Code's token
logs the user out of Claude Code. `rotate.py` and `quota.py` only decide WHICH account the
next process starts under (one CLAUDE_CONFIG_DIR per account); `usage._creds` only READS
the local credential block. Nothing pins that for `quota.py` or for `usage._creds` today
(tests/test_rotate.py::test_rotation_never_touches_a_credential covers rotate.py with a
text scan). These tests read each module with `ast`, ignore docstrings and comments (the
prose may say "logs the user out"), and fail the day code appears that writes a
credentials file, names a logout, imports a token-refresh helper, or opens `_creds` for
writing. Limit: a write through a path built at run time is not seen; this is a tripwire,
not a security boundary. Each rule has a planted-violation test proving the scan fires.
"""

import ast
import pathlib
import textwrap

import pytest

SRC = pathlib.Path(__file__).resolve().parent.parent / 'claude_sessions'
WRITERS = {'write', 'writelines', 'write_text', 'write_bytes', 'write_atomic',
           'write_json_atomic', 'replace', 'rename', 'remove', 'unlink', 'truncate', 'dump',
           'copy', 'copyfile', 'move', 'chmod', 'fdopen'}
LOGOUT = ('logout', 'log_out', 'sign_out', 'signout')
REFRESH = ('refresh_token', 'refreshtoken', 'token_refresh', 'refresh_access', 'oauthlib',
           'authlib', 'msal', 'keyring')


def read(name):
    return (SRC / name).read_text(encoding='utf-8')


def facts(source):
    """(code strings, identifiers and attributes, import names, open calls), all lower case,
    docstrings left out."""
    tree = ast.parse(source)
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docs.add(id(first.value))
    strings, names, imports, opens = [], set(), set(), []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docs:
                strings.append(node.value.lower())
        elif isinstance(node, ast.Name):
            names.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            names.add(node.attr.lower())
        elif isinstance(node, ast.Import):
            imports |= {a.name.lower() for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imports |= {(node.module or '').lower()} | {a.name.lower() for a in node.names}
        elif isinstance(node, ast.Call):
            callee = getattr(node.func, 'id', None) or getattr(node.func, 'attr', None)
            if callee == 'open':
                opens.append(node)
    return strings, names, imports, opens


def credential_file_use(source):
    """Rule (a): no `open` call and no code string naming a credentials file."""
    strings, _, _, opens = facts(source)
    return ['open call'] * len(opens) + [s for s in strings if 'credentials' in s]


def logout_mentions(source):
    """Rule (b): no identifier, attribute, import or code string naming a logout."""
    strings, names, imports, _ = facts(source)
    return [x for x in strings + sorted(names) + sorted(imports) if any(w in x for w in LOGOUT)]


def refresh_helpers(source):
    """Rule (c): no import, identifier or attribute naming a token refresh."""
    _, names, imports, _ = facts(source)
    return [x for x in sorted(names) + sorted(imports) if any(w in x for w in REFRESH)]


def creds_function(source):
    tree = ast.parse(source)
    found = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_creds']
    assert len(found) == 1, 'usage.py must define exactly one module level _creds'
    return ast.get_source_segment(source, found[0])


def creds_not_read_only(source):
    """Rule (d): inside `_creds` every `open` has the constant 'r' as its mode and no writer
    is called; outside it no code string names a credentials file."""
    body = creds_function(source)
    strings, names, _, opens = facts(textwrap.dedent(body))
    bad = [n for n in sorted(names) if n in WRITERS]
    for call in opens:
        mode = call.args[1] if len(call.args) > 1 else None
        if not (isinstance(mode, ast.Constant) and mode.value == 'r') or call.keywords and any(
                k.arg == 'mode' for k in call.keywords):
            bad.append('open mode is not the constant r')
    if not opens:
        bad.append('_creds has no open call to check')
    rest, _, _, _ = facts(source.replace(body, ''))
    return bad + ['outside _creds: ' + s for s in rest if 'credentials' in s]


@pytest.mark.parametrize('name', ['rotate.py', 'quota.py'])
def test_rotation_modules_never_open_or_name_a_credentials_file(name):
    """Branch protected: rotate.py and quota.py never touch `.credentials.json`; today
    neither contains an `open` call or a code string with `credentials`."""
    assert credential_file_use(read(name)) == []


@pytest.mark.parametrize('name', ['rotate.py', 'quota.py'])
def test_rotation_modules_never_name_a_logout(name):
    """Branch protected: a switch of account never signs the old one out (a logout can
    revoke the refresh token Claude Code stored for it). Docstrings and comments are not
    scanned, so the words "logs the user out" in rotate.py's prose are fine."""
    assert logout_mentions(read(name)) == []


@pytest.mark.parametrize('name', ['rotate.py', 'quota.py'])
def test_rotation_modules_import_no_token_refresh_helper(name):
    """Branch protected: neither module imports or calls a token-refresh helper. The
    `usage.refresh_now` poller refresh is a usage fetch, not a token refresh, and is not
    listed."""
    assert refresh_helpers(read(name)) == []


def test_usage_creds_stays_read_only():
    """Branch protected: `usage._creds` opens the credential block with mode 'r' and calls
    no writer, and no other code in usage.py names a credentials file."""
    assert creds_not_read_only(read('usage.py')) == []


def test_the_scan_sees_a_planted_credential_write():
    planted = read('rotate.py') + "\n\ndef _x(d):\n    open(d + '/.credentials.json', 'w')\n"
    assert credential_file_use(planted) == ['open call', '/.credentials.json']


def test_the_scan_sees_a_planted_logout():
    planted = read('quota.py') + "\n\ndef _x(run):\n    run(['claude', 'logout'])\n"
    assert logout_mentions(planted) == ['logout']


def test_the_scan_sees_a_planted_refresh_import():
    planted = read('rotate.py') + "\n\nfrom oauthlib import oauth2\n"
    assert refresh_helpers(planted) == ['oauthlib']


def test_the_scan_sees_a_planted_write_in_usage_creds():
    source = read('usage.py')
    assert creds_not_read_only(source.replace("open(p, 'r', encoding='utf-8')",
                                              "open(p, 'w', encoding='utf-8')")) != []
    written = source.replace("return json.load(f)", "f.write('x'); return json.load(f)")
    assert creds_not_read_only(written) != []
