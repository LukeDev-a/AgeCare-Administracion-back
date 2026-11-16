from datetime import datetime, timezone
from sqlalchemy import select
import pytest
from app import models, database
from scripts.seed_moderation_demo import dataset, load_demo


@pytest.mark.asyncio
async def test_samples_are_additive_repeatable_and_preserve_decisions(client):
    rows = dataset()
    assert len(rows) == len({row['id'] for row in rows}) == 60
    assert sum(row['status'] == 'pending' for row in rows) == 36
    assert all(row['content'] == {} for row in rows if row['type'] in ('photo', 'chat_message'))
    assert all(row['author_user_id'] is None and row['decided_by'] is None for row in rows)
    async with database._session_factory() as db:
        first = await load_demo(db)
        assert first == {'added': 60, 'preserved': 0}
        changed = await db.get(models.ModerationItem, rows[0]['id'])
        changed.status = 'rejected'; changed.decision_note = 'Decisión posterior que debe conservarse'
        changed.decided_at = datetime.now(timezone.utc)
        await db.flush()
        second = await load_demo(db)
        await db.flush()
        assert second == {'added': 0, 'preserved': 60}
        await db.refresh(changed)
        assert changed.status == 'rejected' and changed.decision_note == 'Decisión posterior que debe conservarse'
        assert len((await db.scalars(select(models.ModerationItem).where(models.ModerationItem.id.in_([r['id'] for r in rows])))).all()) == 60
