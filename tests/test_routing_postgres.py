"""Exercise directed cache upserts/concurrency on the real CI PostgreSQL service."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.database import Base
from app.models import DistanceCache, User
from app.services import distance_cache


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL not configured")
def test_postgres_cache_upserts_are_persistent_directional_and_concurrent():
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    schema = "routing_test_" + uuid.uuid4().hex
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA " + schema))
    isolated = engine.execution_options(schema_translate_map={None: schema})
    try:
        Base.metadata.create_all(isolated)
        with Session(isolated) as db:
            owner = User(username="routing-owner", password_hash="test")
            other = User(username="routing-other", password_hash="test")
            db.add_all([owner, other])
            db.commit()
            owner_id, other_id = owner.id, other.id
        a = distance_cache.customer_key(1, user_id=owner_id)
        b = distance_cache.customer_key(2, user_id=owner_id)
        def save(index):
            with Session(isolated) as db:
                distance_cache.save_pairs(db, owner_id, [(a, b, 10 + index, 20), (b, a, 25, 40)])
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(save, range(3)))
        with Session(isolated) as db:
            assert db.query(DistanceCache).count() == 2
            pairs = distance_cache.get_pairs(db, owner_id, [(a, b), (b, a)])
            assert pairs[b, a] == {"km": 25, "min": 40}
            assert 10 <= pairs[a, b]["km"] <= 12
            assert distance_cache.get_pairs(db, other_id, [(a, b)]) == {}
            assert all(row.expires_at is None for row in db.query(DistanceCache).all())
            distance_cache.invalidate_key(db, a, user_id=other_id)
            assert db.query(DistanceCache).count() == 2
            distance_cache.invalidate_key(db, a, user_id=owner_id)
            assert db.query(DistanceCache).count() == 0
    finally:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA " + schema + " CASCADE"))
        engine.dispose()
