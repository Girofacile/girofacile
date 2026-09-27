"""Run daily on the server; defaults to a dry run and never prints addresses."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    from sqlalchemy.orm import Session
    from app.database import engine
    from app.services.billing_notices import send_due_notices
    with Session(engine) as db:
        print(send_due_notices(db, send=args.send))
