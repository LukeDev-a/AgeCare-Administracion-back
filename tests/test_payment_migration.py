import importlib.util
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app import models
from app.database import Base


def test_payment_migration_preserves_accounts_and_checks_amount_and_foreign_keys():
    spec = importlib.util.spec_from_file_location('payment_migration', Path(__file__).parents[1] / 'alembic/versions/0019_payment_storage.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    engine = sa.create_engine('sqlite://')
    with engine.begin() as db:
        db.exec_driver_sql('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(db, tables=[models.AppAccount.__table__])
        user_id = uuid4()
        db.execute(models.AppAccount.__table__.insert().values(id=user_id, full_name='Carmen Soto', email='carmen@example.test', is_active=True))
        module.op = Operations(MigrationContext.configure(db))
        module.upgrade()
        assert db.scalar(sa.select(sa.func.count()).select_from(models.AppAccount)) == 1
        assert db.scalar(sa.select(sa.func.count()).select_from(models.PaymentSubscription)) == 0
        now = datetime.now(timezone.utc)
        sub_id = uuid4()
        db.execute(models.PaymentSubscription.__table__.insert().values(id=sub_id, code='SUS-0001', user_id=user_id,
            plan='Dorado', price=3990, state='active', started_at=now, ends_at=now, version=1, history=[], data_origin='demo'))
        assert sa.inspect(db).get_foreign_keys('payment_charges')[0]['referred_table'] == 'payment_subscriptions'
        module.downgrade()
        assert db.scalar(sa.select(sa.func.count()).select_from(models.PaymentSubscription)) == 1
    engine.dispose()
