"""CRM transactions and migrations against isolated PostgreSQL schemas."""
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import inspect
from sqlalchemy.orm import Session
from fastapi import HTTPException
from test_audit_postgres import pg


def test_crm_upgrade_and_parallel_updates(pg):
    from app.migrations import run_migrations, require_current_schema
    from app.crm_models import CRM_TABLES, CRMCompany, CRMAudit
    from app.routers.admin_crm import update_company
    from app.schemas.crm import CompanyIn
    run_migrations(pg)
    run_migrations(pg)
    require_current_schema(pg)
    assert {t.name for t in CRM_TABLES} <= set(inspect(pg).get_table_names())
    with Session(pg) as db:
        row = CRMCompany(name='Before', country='IT', vat='123')
        db.add(row); db.commit(); record_id=row.id
    def write(name):
        with Session(pg) as db:
            try:
                update_company(record_id, CompanyIn(name=name, version=1), {'role':'superadmin','username':'owner'}, db)
                return 200
            except HTTPException as error:
                db.rollback()
                return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write, ['First writer','Second writer']))
    assert sorted(outcomes) == [200,409]
    with Session(pg) as db:
        assert db.get(CRMCompany,record_id).version == 2
        assert db.query(CRMAudit).filter_by(company_id=record_id).count() == 1
