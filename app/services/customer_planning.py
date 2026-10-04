"""Planning eligibility uses the existing customer geocoding state and coordinates."""
import math
from ..models import Customer

PLANNING_ADDRESS_ERROR = "L'indirizzo del cliente deve essere verificato prima di poterlo inserire in un giro."


def customer_is_plannable(customer):
    return has_verified_coordinates(customer.stato_geocodifica, customer.lat, customer.lon)


def has_verified_coordinates(state, lat, lon):
    if state != 'verificato':
        return False
    try:
        lat, lon = float(lat), float(lon)
        return math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180
    except (TypeError, ValueError):
        return False


def planning_customer_filters():
    return (Customer.stato_geocodifica == 'verificato',
            Customer.lat.between(-90, 90), Customer.lon.between(-180, 180))
