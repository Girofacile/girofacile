"""Costi usati per confrontare i giri (5 novembre 2026).

Il giro migliore è quello che costa meno: carburante al km più ore dell'autista,
attese comprese. Un'ora ferma davanti a un cliente chiuso costa quanto un'ora di guida.

- Ore dell'autista: costo orario scritto in Impostazioni, 15 €/ora se manca.
- Carburante: consumo del mezzo per prezzo dell'energia; 0,20 €/km se mancano
  i dati (furgone diesel, circa 11 L/100 km a 1,75 €/L).

I valori entrano nel dizionario del mezzo usato dal calcolo (costo_km,
costo_orario_autista) e servono solo a scegliere l'ordine delle fermate e la
partenza: i costi mostrati nel giro restano quelli di sempre.
"""
import math

DEFAULT_COST_PER_KM = 0.20
DEFAULT_DRIVER_HOURLY_COST = 15
HOURLY_COST_LIMITS = (0, 200)


def driver_hourly_cost(user):
    """Costo orario dell'autista dell'azienda, oppure il valore predefinito."""
    value = getattr(user, 'driver_hourly_cost', None)
    return DEFAULT_DRIVER_HOURLY_COST if value is None else int(value)


def cost_per_km(vehicle, price_primary=None, price_electric=None):
    """Euro di energia al km del mezzo; None se mancano consumo o prezzo."""
    if vehicle is None:
        return None
    kind = getattr(vehicle, 'alimentazione', None) or 'gasolio'
    primary_use = float(getattr(vehicle, 'consumo_primario_100km', None) or getattr(vehicle, 'consumo_l_100km', None) or 0)
    electric_use = float(getattr(vehicle, 'consumo_kwh_100km', None) or 0)
    primary = 0.0 if kind == 'elettrico' else primary_use / 100 * float(price_primary or 0)
    electric = (electric_use / 100 * float(price_electric or 0)
                if kind in ('elettrico', 'ibrido_plugin_benzina', 'ibrido_plugin_diesel') else 0.0)
    total = primary + electric
    return total if math.isfinite(total) and total > 0 else None


def rates(user, vehicle=None, price_primary=None, price_electric=None):
    """Campi da aggiungere al dizionario del mezzo per il calcolo."""
    per_km = cost_per_km(vehicle, price_primary, price_electric)
    return {'costo_km': DEFAULT_COST_PER_KM if per_km is None else round(per_km, 4),
            'costo_orario_autista': driver_hourly_cost(user)}
