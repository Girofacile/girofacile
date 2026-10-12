"""Compatibility-only helper for historical route code.

Order/customer matching has been retired. This module intentionally does not
query Customer, look up codes, produce matching suggestions, link an order, or
inherit any customer data. Remove the import from route_orders when its callers
can be migrated safely.
"""


def effective(db, order):
    """Only order-owned delivery fields may be used to build a route stop."""
    return dict(order.operational_data or {}), []
