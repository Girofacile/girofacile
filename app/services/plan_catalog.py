"""Commercial catalogue shared by APIs, quotas and administration."""
import os

TRIAL_DAYS = 14
GRACE_DAYS = 7
PLAN_LIMITS = {}
PLAN_PRICES = {}
for key, name, price, customers, drivers, depots, orders, collaborators, electric_bonus in (
    ("starter", "Starter", 29, 150, 3, 1, 300, 2, 1),
    ("business", "Business", 59, 500, 10, 3, 1200, 5, 2),
    ("pro", "Pro", 99, 5000, 50, 20, 6000, 10, 5),
):
    PLAN_PRICES[key] = dict(name=name, price_eur=price, price_cents=price * 100,
                           stripe_price_id=os.getenv(f"STRIPE_PRICE_{key.upper()}", ""))
    PLAN_LIMITS[key] = dict(
        name=name, max_customers=customers, max_drivers=drivers, max_vehicles=drivers,
        electric_vehicle_bonus=electric_bonus,
        max_deposits=depots, max_orders_per_month=orders, max_collaborators=collaborators,
        # Compatibility keys: routes and deliveries have no commercial monthly cap.
        max_routes_per_day=None, max_routes_per_month=None, max_deliveries_per_month=None,
        has_collaborators=True, has_agents=key != "starter",
        has_reports=key != "starter", has_export=True, has_geocoding=True,
        has_mobile=True, has_driver_chat=key != "starter", has_ai=key == "pro",
        has_order_integrations=key != "starter", has_fleet_planning=key != "starter",
        has_customer_tracking=key != "starter", has_delivery_signature=key != "starter",
        has_photo_proof=key != "starter", has_pod_pdf=key != "starter",
    )
