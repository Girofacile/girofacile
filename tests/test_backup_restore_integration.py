"""Opt-in real PostgreSQL test: creates and removes only uniquely named test DBs."""
import os
import shutil
import subprocess
import uuid
from urllib.parse import urlsplit, urlunsplit

import pytest


@pytest.mark.skipif(not os.getenv('TEST_POSTGRES_URL'), reason='TEST_POSTGRES_URL not configured')
def test_real_postgres_backup_and_restore(tmp_path):
    import psycopg2
    from psycopg2 import sql
    from scripts.backup_database import backup_postgres, postgres_connection
    admin_url=os.environ['TEST_POSTGRES_URL']
    parsed=urlsplit(admin_url)
    names=['gf_test_backup_'+uuid.uuid4().hex, 'gf_test_restore_'+uuid.uuid4().hex]
    urls=[urlunsplit(parsed._replace(path='/'+name)) for name in names]
    admin=psycopg2.connect(admin_url);admin.autocommit=True
    try:
        for name in names:
            with admin.cursor() as cursor:cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        with psycopg2.connect(urls[0]) as source:
            with source.cursor() as cursor:
                cursor.execute('CREATE TABLE backup_probe (id integer PRIMARY KEY, label text NOT NULL)')
                cursor.execute('INSERT INTO backup_probe VALUES (%s,%s)',(1,'Firma e consegna: città'))
        archive=backup_postgres(urls[0],tmp_path)
        target,env=postgres_connection(urls[1])
        subprocess.run([shutil.which('pg_restore'),'--exit-on-error','--no-owner','--no-acl',
                        '--dbname',target,str(archive)],env=env,check=True,capture_output=True,timeout=90)
        with psycopg2.connect(urls[1]) as restored:
            with restored.cursor() as cursor:
                cursor.execute('SELECT id,label FROM backup_probe')
                assert cursor.fetchall()==[(1,'Firma e consegna: città')]
    finally:
        for name in names:
            assert name.startswith(('gf_test_backup_','gf_test_restore_'))
            with admin.cursor() as cursor:cursor.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(sql.Identifier(name)))
        admin.close()
