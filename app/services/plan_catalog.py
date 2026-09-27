"""Commercial catalogue shared by APIs, quotas and administration."""
import os

TRIAL_DAYS = 14
GRACE_DAYS = 7
PLAN_LIMITS = {}
PLAN_PRICES = {}
for key, name, price, customers, drivers, depots, routes, deliveries in (
    ("starter", "Starter", 29, 150, 3, 1, 100, 2000),
    ("business", "Business", 59, 500, 10, 3, 400, 10000),
    ("pro", "Pro", 99, 5000, 50, 20, 1500, 30000),
):
    PLAN_PRICES[key] = dict(name=name, price_eur=price, price_cents=price * 100,
                           stripe_price_id=os.getenv(f"STRIPE_PRICE_{key.upper()}", ""))
    PLAN_LIMITS[key] = dict(
        name=name, max_customers=customers, max_drivers=drivers, max_vehicles=drivers,
        max_deposits=depots, max_routes_per_day=None, max_routes_per_month=routes,
        max_deliveries_per_month=deliveries, has_agents=key != "starter",
        has_reports=key != "starter", has_export=True, has_geocoding=True,
        has_mobile=True, has_driver_chat=key != "starter", has_ai=key == "pro",
    )
