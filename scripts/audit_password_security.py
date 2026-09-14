"""Audit sicurezza password GiroFacile v70.

Esegue un controllo in sola lettura sugli hash salvati nel database e mostra
quanti account usano il nuovo formato PBKDF2 e quanti sono ancora legacy.
Non stampa mai hash, token o password.
"""
from app.database import SessionLocal
from app.models import AgentAccount, DriverAccount, SuperAdminCollaborator, User
from app.core.security import is_legacy_sha256_hash


def classify(stored: str | None) -> str:
    if not stored:
        return "mancante"
    if stored.startswith("pbkdf2_sha256$"):
        return "pbkdf2_v70"
    if ":" in stored:
        return "pbkdf2_legacy"
    if is_legacy_sha256_hash(stored):
        return "sha256_legacy"
    return "altro"


def main() -> None:
    db = SessionLocal()
    try:
        groups = [
            ("Aziende/utenti", db.query(User).all()),
            ("Autisti", db.query(DriverAccount).all()),
            ("Agenti", db.query(AgentAccount).all()),
            ("Collaboratori Super Admin", db.query(SuperAdminCollaborator).all()),
        ]
        for label, rows in groups:
            counts = {}
            for row in rows:
                kind = classify(getattr(row, "password_hash", None))
                counts[kind] = counts.get(kind, 0) + 1
            print(f"\n{label}")
            if not rows:
                print("  nessun account")
                continue
            for kind, total in sorted(counts.items()):
                print(f"  {kind}: {total}")
        print("\nNota: gli hash SHA-256 legacy vengono aggiornati automaticamente al primo login o reset password.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
