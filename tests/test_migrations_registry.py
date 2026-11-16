"""Elenco delle migrazioni: ultima versione ricavata da sola e controllo di tutte le versioni all'avvio."""
import re
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app import migrations


def test_latest_is_the_newest_registered_migration():
    source = Path(migrations.__file__).read_text(encoding='utf-8')
    checked = set(re.findall(r"'(\d{8}_\d{2})' not in applied", source))
    # Ogni versione controllata viene anche registrata (tranne il vecchio marker 20261005_01, sostituito dal 20261006_01).
    assert checked - set(migrations.VERSIONS) <= {'20261005_01'}
    assert migrations.LATEST == max(migrations.VERSIONS) == migrations.VERSIONS[-1]
    assert '20261114_01' in migrations.VERSIONS


def test_schema_with_only_the_old_latest_marker_is_rejected():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE schema_migrations (version VARCHAR PRIMARY KEY, applied_at TIMESTAMP)'))
        for version in migrations.VERSIONS[:-1]:
            conn.execute(text('INSERT INTO schema_migrations (version) VALUES (:v)'), {'v': version})
    assert migrations.missing_versions(engine) == [migrations.LATEST]
    with pytest.raises(RuntimeError, match='Migrazioni pendenti'):
        migrations.require_current_schema(engine)
    with engine.begin() as conn:
        conn.execute(text('INSERT INTO schema_migrations (version) VALUES (:v)'), {'v': migrations.LATEST})
    migrations.require_current_schema(engine)
