"""Controllo duplicati per vincoli univoci aziendali.

Uso:
    python scripts/check_unique_constraints.py

Verifica che dentro la stessa azienda non esistano duplicati per:
- customers.codice_cliente
- vehicles.targa
- drivers.email
- agents.email
- agents.codice_agente
"""
from app.database import SessionLocal
from sqlalchemy import text

CHECKS = [
    ("customers", "codice_cliente", "codice cliente duplicato"),
    ("vehicles", "targa", "targa mezzo duplicata"),
    ("drivers", "email", "email autista duplicata"),
    ("agents", "email", "email agente duplicata"),
    ("agents", "codice_agente", "codice agente duplicato"),
]


def main():
    db = SessionLocal()
    try:
        found = False
        for table, column, label in CHECKS:
            rows = db.execute(text(f"""
                SELECT user_id, {column}, COUNT(*) AS totale
                FROM {table}
                WHERE user_id IS NOT NULL
                  AND {column} IS NOT NULL
                  AND TRIM({column}) <> ''
                GROUP BY user_id, {column}
                HAVING COUNT(*) > 1
                ORDER BY totale DESC
                LIMIT 50
            """)).fetchall()
            if rows:
                found = True
                print(f"\n[ATTENZIONE] {label} in {table}.{column}")
                for r in rows:
                    print(f"  azienda/user_id={r[0]} valore={r[1]!r} duplicati={r[2]}")
        if not found:
            print("[OK] Nessun duplicato trovato per i vincoli aziendali principali.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
