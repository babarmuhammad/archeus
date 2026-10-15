"""G8 — legacy data migration: a fixture legacy home imports idempotently,
read-only, with the counts and mappings of migration-plan §4."""

import pytest


@pytest.mark.xfail(strict=True, reason="phase:P22")
def test_importing_a_legacy_home_twice_yields_the_same_world(client, rig):
    legacy = rig.fixture_legacy_home('two-projects')
    first = rig.import_legacy(legacy)
    second = rig.import_legacy(legacy)
    assert first == second
    assert first['projects'] == 2 and client.status()['projects']
    assert legacy.unchanged()
