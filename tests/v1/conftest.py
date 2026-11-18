"""Every V1 test runs against its own ARCHEUS_HOME (testing-strategy §1.1).

The resolver reads the variable at call time, so setting it per test is enough
for everything under `archeus/` to land in the test's temp directory — and a
V1 test can never touch the real `%LOCALAPPDATA%\\Archeus`, nor the legacy
`~/.archeus/`. The suite-wide guards in tests/conftest.py (no real claude /
codex process, no writes outside the temp area) apply here unchanged.
"""

import os
import sys

import pytest

from archeus.node import staging

# The interpreter's own install, captured before any test can monkeypatch sys and
# compared as strings only: proving a path is not the install must not read it.
INSTALLED = tuple({os.path.normcase(os.path.abspath(p))
                   for p in (sys.base_prefix, sys.prefix, os.path.dirname(sys.executable))})


def installed(path):
    p = os.path.normcase(os.path.abspath(path))
    for i in INSTALLED:
        try:
            if os.path.commonpath([p, i]) in (p, i):
                return True
        except ValueError:      # another drive
            pass
    return False


@pytest.fixture(autouse=True)
def archeus_home(tmp_path, monkeypatch):
    home = tmp_path / 'archeus-home'
    monkeypatch.setenv('ARCHEUS_HOME', str(home))
    monkeypatch.delenv('ARCHEUS_EXECUTION_ID', raising=False)
    return home


@pytest.fixture(autouse=True)
def no_installed_runtime_stage(monkeypatch):
    """No test stages the real install (owner, T-040). The guard sits on `_plan`,
    the first thing every `stage` does however it was imported, so it fails before
    the install is inventoried, hashed or copied. `pytest.fail` is not an OSError,
    so a caller that turns a stage error into a refusal cannot hide it."""
    def plan(source_root, *a, **k):
        if installed(source_root):
            pytest.fail('a test staged the installed runtime: %s' % source_root)
        return plan.__wrapped__(source_root, *a, **k)
    plan.__wrapped__ = staging._plan
    monkeypatch.setattr(staging, '_plan', plan)
