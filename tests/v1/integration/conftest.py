"""P2 fixtures: a real archeus.db on the test's own ARCHEUS_HOME."""

import os
import shutil

import pytest

from archeus.core.application import commands
from archeus.core.domain import ids
from archeus.core.domain.values import Ref
from archeus.infra.db import Database, migrate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


@pytest.fixture
def actor():
    return Ref('user_device', ids.new_id('principal'))


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


@pytest.fixture
def new_mission(db, actor):
    def make(title='M', key=None):
        return db.writer.execute(commands.create_mission,
                                 {'actor': actor, 'title': title, 'objective': 'o'},
                                 idempotency_key=key)
    return make


@pytest.fixture
def migrations_dir(tmp_path):
    """A private migrations directory holding the real 0001; tests add more."""
    d = tmp_path / 'migrations'
    d.mkdir()
    shutil.copy(os.path.join(migrate.MIGRATIONS_DIR, '0001_init.sql'), d)
    return d
