"""Controllo integrità soft delete GiroFacile.

Esegue verifiche semplici per capire se nel database esistono record operativi
archiviati logicamente e se gli storici restano collegati correttamente.
"""
from app.database import SessionLocal
from app.models import Customer, Deposit, Vehicle, Driver, Agent, RoutePlan


def main():
    db = SessionLocal()
    try:
        models = [Customer, Deposit, Vehicle, Driver, Agent]
        print("=== Soft delete GiroFacile ===")
        for model in models:
            total = db.query(model).count()
            archived = db.query(model).filter(model.deleted_at.is_not(None)).count()
            active = db.query(model).filter(model.deleted_at.is_(None)).count()
            print(f"{model.__tablename__}: attivi={active} archiviati={archived} totali={total}")
        routes_with_refs = db.query(RoutePlan).filter(
            (RoutePlan.deposit_id.is_not(None)) |
            (RoutePlan.vehicle_id.is_not(None)) |
            (RoutePlan.driver_id.is_not(None))
        ).count()
        print(f"route_plans con riferimenti storici a deposito/mezzo/autista: {routes_with_refs}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
