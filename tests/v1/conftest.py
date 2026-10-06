"""Every V1 test runs against its own ARCHEUS_HOME (testing-strategy §1.1).

The resolver reads the variable at call time, so setting it per test is enough
for everything under `archeus/` to land in the test's temp directory — and a
V1 test can never touch the real `%LOCALAPPDATA%\\Archeus`, nor the legacy
`~/.archeus/`. The suite-wide guards in tests/conftest.py (no real claude /
codex process, no writes outside the temp area) apply here unchanged.
"""

import pytest


@pytest.fixture(autouse=True)
def archeus_home(tmp_path, monkeypatch):
    home = tmp_path / 'archeus-home'
    monkeypatch.setenv('ARCHEUS_HOME', str(home))
    monkeypatch.delenv('ARCHEUS_EXECUTION_ID', raising=False)
    return home
