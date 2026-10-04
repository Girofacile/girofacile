from app.services.occasional_stops import sign_stop_address


def verified_stop(user_id, **values):
    """A server-attested address for tests unrelated to the Google HTTP call."""
    row = dict(customer_id=None, cliente_nome="Cantiere", indirizzo="Via Roma 18, Napoli",
               lat=40.85, lon=14.27, stato_geocodifica="verificato")
    row.update(values)
    row["geocoding_token"] = sign_stop_address(user_id, row["indirizzo"], row["lat"], row["lon"])
    return row
