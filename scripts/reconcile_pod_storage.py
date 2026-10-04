"""Report old unreferenced POD objects; deletion is an explicit maintenance action.

Run from the repository root: python -m scripts.reconcile_pod_storage [--delete].
Never configure expiration on the entire companies/ prefix.
"""
import argparse
import re
from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models import DeliveryStatus, RoutePlan
from app.services.object_storage import get_storage


def reconcile(storage, db, *, delete=False, now=None):
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=48)
    paginator = storage.client.get_paginator('list_objects_v2')
    pattern = r'companies/(\d+)/routes/(\d+)/deliveries/(\d+)/(signature|delivery_photo|pod)-[a-f0-9]{32}\.(png|jpg|pdf)'
    for page in paginator.paginate(Bucket=storage.bucket, Prefix='companies/'):
        for item in page.get('Contents', []):
            key = item['Key']
            match = re.fullmatch(pattern, key)
            if not match or item['LastModified'] >= cutoff:
                continue
            company_id, route_id, delivery_id = map(int, match.groups()[:3])
            # The same lock used by uploads prevents races with evidence replacement.
            route = db.query(RoutePlan).filter_by(id=route_id).with_for_update().first()
            if route and route.user_id != company_id:
                db.rollback()
                continue
            referenced = db.query(DeliveryStatus).filter(
                (DeliveryStatus.signature_object_key == key) |
                (DeliveryStatus.delivery_photo_object_key == key) |
                (DeliveryStatus.pod_object_key == key)).first()
            if not referenced:
                print(('DELETE ' if delete else 'UNREFERENCED ') + key)
                if delete:
                    storage.delete(key)
            db.rollback()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delete', action='store_true', help='Delete only unreferenced POD objects older than 48 hours')
    args = parser.parse_args()
    storage = get_storage()
    storage.verify_configuration()
    with SessionLocal() as db:
        reconcile(storage, db, delete=args.delete)
