"""Timezone-aware datetime defaults (Phase 10).

Locks two things: the model default is tz-aware UTC (no more naive utcnow), and
DB datetime fields still serialize correctly through the API schemas."""
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app import models
from app.database import Base
from app.schemas import GenerationOut


def test_now_default_is_timezone_aware_utc():
    now = models._now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timezone.utc.utcoffset(None)


def test_generation_datetimes_round_trip_and_serialize(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'tz.db'}")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = models.User(email="t@e.c", name="T", credits=10)
            session.add(user)
            session.commit()

            gen = models.Generation(
                user_id=user.id,
                prompt="hi",
                media_type="image",
                status="queued",
                credits_cost=0,
            )
            session.add(gen)
            session.commit()
            session.refresh(gen)

            # Defaults populated, and the API schema serializes them to ISO strings.
            assert gen.created_at is not None
            payload = GenerationOut.model_validate(gen).model_dump(mode="json")
            assert isinstance(payload["created_at"], str)
            # Must be a parseable timestamp.
            datetime.fromisoformat(payload["created_at"])
    finally:
        engine.dispose()
