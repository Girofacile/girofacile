"""Read-only superadmin database viewer and masked CSV export."""


import csv
import io
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from ..core.dependencies import require_superadmin
from ..database import get_db, engine
from .admin_helpers import (
    _activity,
    _database_kind_label,
    _require_perm,
)


router = APIRouter(prefix="/api/admin", tags=["admin"])


SENSITIVE_DB_FIELD_PATTERNS = (
    "password", "password_hash", "token", "secret", "api_key", "apikey",
    "key", "smtp_password", "reset", "session", "cookie", "authorization",
    "access", "refresh", "credential", "pepper"
)


DATABASE_VIEWER_EXCLUDED_TABLES = {
    }


def _db_inspector():
    return inspect(engine)


def _allowed_database_tables() -> list[str]:
    insp = _db_inspector()
    tables = []
    for name in insp.get_table_names():
        lname = name.lower()
        if lname.startswith("pg_") or lname.startswith("sql_") or lname in DATABASE_VIEWER_EXCLUDED_TABLES:
            continue
        tables.append(name)
    return sorted(tables)


def _is_sensitive_db_column(column: str) -> bool:
    c = (column or "").lower()
    return any(pattern in c for pattern in SENSITIVE_DB_FIELD_PATTERNS)


def _mask_db_value(column: str, value, table_name="", row=None):
    if value is None:
        return None
    if _is_sensitive_db_column(column) or (column == "value" and row is not None and _is_sensitive_db_column(str(row.get("key", "")))):
        text = str(value)
        if not text:
            return ""
        return "••••••••••••"
    if isinstance(value, bytes):
        return f"<BLOB {len(value)} byte>"
    text = str(value)
    if len(text) > 600:
        return text[:600] + "…"
    return value


def _safe_db_table_name(table_name: str) -> str:
    table_name = (table_name or "").strip()
    if not table_name:
        raise HTTPException(400, "Tabella non indicata")
    allowed = _allowed_database_tables()
    if table_name not in allowed:
        raise HTTPException(404, "Tabella non trovata o non visualizzabile")
    return table_name


def _db_table_columns(table_name: str) -> list[dict]:
    insp = _db_inspector()
    pk_cols = set()
    try:
        pk_cols = set((insp.get_pk_constraint(table_name) or {}).get("constrained_columns") or [])
    except Exception:
        pk_cols = set()
    cols = []
    for col in insp.get_columns(table_name):
        name = col.get("name")
        cols.append({
            "name": name,
            "type": str(col.get("type") or ""),
            "notnull": not bool(col.get("nullable", True)),
            "default": str(col.get("default") or "") if col.get("default") is not None else None,
            "primary_key": name in pk_cols,
            "sensitive": _is_sensitive_db_column(name),
        })
    return cols


def _db_table_summary(table_name: str) -> dict:
    preparer = engine.dialect.identifier_preparer
    qtable = preparer.quote(table_name)
    with engine.connect() as conn:
        count = conn.execute(text(f"SELECT COUNT(*) AS c FROM {qtable}")).scalar()
    columns = _db_table_columns(table_name)
    return {
        "name": table_name,
        "rows": int(count or 0),
        "columns_count": len(columns),
        "sensitive_columns": [c["name"] for c in columns if c["sensitive"]],
    }


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
        searchable = [c for c in column_names if not _is_sensitive_db_column(c) and not (c == 'value' and 'key' in column_names)]
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
                item[col] = _mask_db_value(col, row.get(col), table_name, row)
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
        searchable = [c for c in column_names if not _is_sensitive_db_column(c) and not (c == 'value' and 'key' in column_names)]
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
            writer.writerow([_mask_db_value(col, row.get(col), table_name, row) for col in column_names])

    _activity(db, superadmin.get("username"), "database_table_exported", f"Export CSV tabella {table_name}", "warning")
    db.commit()
    data = out.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{table_name}_export.csv"'},
    )
