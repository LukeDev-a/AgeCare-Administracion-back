import json
import pytest
import sqlalchemy as sa
from app import models
from test_directory_coherence import legacy, migration
from scripts.migrate_neon_0020 import verify_directory, MigrationError, DIRECTORY


def snapshot(db):
    return {name: json.loads(json.dumps([dict(row) for row in db.execute(sa.select(models.Base.metadata.tables[name])).mappings()], default=str)) for name in DIRECTORY}


def test_neon_verifier_accepts_exact_migration_and_rejects_unexpected_changes():
    engine = sa.create_engine('sqlite://')
    with engine.begin() as db:
        legacy(db)
        before = snapshot(db)
        migration(db).upgrade()
        after = snapshot(db)
        verify_directory(before, after)
        verify_directory(after, after)
        for table, field in [('app_accounts', 'full_name'), ('app_patients', 'full_name'), ('app_memberships', 'role')]:
            corrupted = json.loads(json.dumps(after))
            corrupted[table][0][field] = 'unexpected'
            with pytest.raises(MigrationError):
                verify_directory(before, corrupted)
        deleted = json.loads(json.dumps(after))
        deleted['app_memberships'].pop()
        with pytest.raises(MigrationError):
            verify_directory(before, deleted)
    engine.dispose()
