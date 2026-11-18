import ast
from pathlib import Path

import pytest


PRIVATE = {'account_ref', 'home_ref', 'home_key'}


def _private(node):
    return any(
        isinstance(n, ast.Name) and n.id in PRIVATE
        or isinstance(n, ast.Attribute) and n.attr in PRIVATE
        or isinstance(n, ast.Constant) and isinstance(n.value, str)
        and any(field in n.value for field in PRIVATE)
        for n in ast.walk(node))


def _violations(source):
    return [n.lineno for n in ast.walk(ast.parse(source))
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name) and n.func.value.id == 'log'
            and any(_private(arg) for arg in [*n.args, *(k.value for k in n.keywords)])]


def test_T4_logs_do_not_format_account_home_fields():
    root = Path(__file__).resolve().parents[3] / 'archeus'
    bad = {str(p.relative_to(root)): lines for p in root.rglob('*.py')
           if (lines := _violations(p.read_text(encoding='utf-8-sig')))}
    assert not bad, bad


@pytest.mark.parametrize('expression', [
    'account_ref', 'account.home_ref', 'snapshot["home_key"]',
    'f"home {account.home_ref}"', '"home %s" % home_key',
    '"home {}".format(account_ref)',
])
def test_T4_guard_detects_private_formatting(expression):
    assert _violations('log.info("resource %s", %s)' % ('%s', expression)) == [1]


def test_T4_traceback_carve_out():
    assert _violations('log.error("internal error %s", ref, exc_info=err)') == []
