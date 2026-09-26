"""Admin database: extracted from the SaaS administration router."""
import csv
import io
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from ..core.dependencies import require_superadmin
from ..database import get_db, engine

from .admin_helpers import (
    _activity,
    _allowed_database_tables,
    _database_kind_label,
    _db_table_columns,
    _db_table_summary,
    _is_sensitive_db_column,
    _mask_db_value,
    _require_perm,
    _safe_db_table_name,
)

router = APIRouter()


@router.get("/database-viewer/tables")
def admin_database_tables(db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_database")
    tables = []
    for name in _allowed_database_tables():
        try:
            tables.append(_db_table_summary(name))
        except Exception:
            tables.append({"name": name, "rows": 0, "columns_count": 0, "sensitive_columns": []})
    _activity(db, superadmin.get("username"), "database_viewer_opened", "Aperto Database Viewer PostgreSQL", "warning")
    db.commit()
    return {"tables": tables, "masking_enabled": True, "database_type": _database_kind_label()}


@router.get("/database-viewer/table/{table_name}")
def admin_database_table(
    table_name: str,
    page: int = 1,
    page_size: int = 50,
    q: str = "",
    db: Session = Depends(get_db),
    superadmin: dict = Depends(require_superadmin),
):
    _require_perm(superadmin, "view_database")
    page = max(1, int(page or 1))
    page_size = max(10, min(200, int(page_size or 50)))
    q_text = (q or "").strip()
    table_name = _safe_db_table_name(table_name)
    columns = _db_table_columns(table_name)
    column_names = [c["name"] for c in columns]
    preparer = engine.dialect.identifier_preparer
    qtable = preparer.quote(table_name)
    where_sql = ""
    params = {}
    if q_text and column_names:
        searchable = [c for c in column_names if not _is_sensitive_db_column(c)]
        if searchable:
            clauses = []
            for i, col in enumerate(searchable):
                pname = f"q{i}"
                clauses.append(f"CAST({preparer.quote(col)} AS TEXT) ILIKE :{pname}")
                params[pname] = f"%{q_text}%"
            where_sql = " WHERE " + " OR ".join(clauses)
    total_sql = text(f"SELECT COUNT(*) AS c FROM {qtable}{where_sql}")
    params_page = dict(params)
    params_page.update({"limit": page_size, "offset": (page - 1) * page_size})
    rows_sql = text(f"SELECT * FROM {qtable}{where_sql} LIMIT :limit OFFSET :offset")
    clean_rows = []
    with engine.connect() as conn:
        total = conn.execute(total_sql, params).scalar()
        rows = conn.execute(rows_sql, params_page).mappings().all()
        for row in rows:
            item = {}
            for col in column_names:
                item[col] = _mask_db_value(col, row.get(col))
            clean_rows.append(item)
    return {
        "table": table_name,
        "columns": columns,
        "rows": clean_rows,
        "page": page,
        "page_size": page_size,
        "total": int(total or 0),
        "total_pages": max(1, ((int(total or 0) + page_size - 1) // page_size)),
        "query": q_text,
    }


@router.get("/database-viewer/table/{table_name}/export")
def admin_database_export(
    table_name: str,
    q: str = "",
    db: Session = Depends(get_db),
    superadmin: dict = Depends(require_superadmin),
):
    _require_perm(superadmin, "export_database")
    q_text = (q or "").strip()
    table_name = _safe_db_table_name(table_name)
    columns = _db_table_columns(table_name)
    column_names = [c["name"] for c in columns]
    preparer = engine.dialect.identifier_preparer
    qtable = preparer.quote(table_name)
    where_sql = ""
    params = {}
    if q_text and column_names:
        searchable = [c for c in column_names if not _is_sensitive_db_column(c)]
        if searchable:
            clauses = []
            for i, col in enumerate(searchable):
                pname = f"q{i}"
                clauses.append(f"CAST({preparer.quote(col)} AS TEXT) ILIKE :{pname}")
                params[pname] = f"%{q_text}%"
            where_sql = " WHERE " + " OR ".join(clauses)
    rows_sql = text(f"SELECT * FROM {qtable}{where_sql} LIMIT 10000")
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(column_names)
    with engine.connect() as conn:
        rows = conn.execute(rows_sql, params).mappings().all()
        for row in rows:
            writer.writerow([_mask_db_value(col, row.get(col)) for col in column_names])

    _activity(db, superadmin.get("username"), "database_table_exported", f"Export CSV tabella {table_name}", "warning")
    db.commit()
    data = out.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{table_name}_export.csv"'},
    )
