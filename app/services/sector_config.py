"""Configurazioni settore legacy per testi e impostazioni iniziali.

L'interfaccia operativa di GiroFacile è universale; queste configurazioni
restano solo per compatibilità con account creati nelle versioni precedenti.
"""

COMMON_LABELS = {
    "customer": "Cliente",
    "customers": "Clienti",
    "driver": "Autista",
    "drivers": "Autisti",
    "vehicle": "Mezzo",
    "vehicles": "Mezzi",
    "delivery": "Consegna",
    "deliveries": "Consegne",
    "route": "Giro",
    "routes": "Giri",
    "stop": "Fermata",
    "stops": "Fermate",
    "scheduled_routes": "Giri programmati",
    "active_routes": "Giri in corso",
    "completed_today": "Giri completati oggi",
    "route_planning": "Pianificazione giro",
    "new_route": "+ Nuovo giro",
}

def _config(name, subtitle, labels=None, features=None, defaults=None, future=None, statuses=None):
    return {
        "name": name,
        "subtitle": subtitle,
        "labels": {**COMMON_LABELS, **(labels or {})},
        "features": features or [],
        "recommended_defaults": defaults or {},
        "future_fields": future or [],
        "delivery_statuses": statuses or ["Da fare", "Consegnata", "Mancata"],
    }

SECTOR_CONFIGS = {
    "distribution": _config(
        "Distribuzione / Cash & Carry",
        "Grossisti, Cash & Carry, Ho.Re.Ca., surgelati, beverage e consegne programmate.",
        {"delivery": "Consegna merce", "deliveries": "Consegne merce", "route_planning": "Pianificazione giro consegne"},
        ["Codice cliente", "Fasce orarie", "Tempo di scarico", "Colli e bancali", "Sponda / transpallet", "ZTL", "Firma alla consegna"],
        {"has_time_windows": True, "needs_signature": True, "needs_tail_lift": True},
        ["codice_cliente", "colli", "bancali", "tempo_scarico", "sponda", "ztl"],
        ["Da fare", "Consegnata", "Parziale", "Cliente chiuso", "Rifiutata", "Mancata"],
    ),
    "logistics": _config(
        "Logistica / Corrieri locali",
        "Corrieri locali, ultimo miglio, spedizioni, colli, ritiri e consegne.",
        {"customer": "Destinatario", "customers": "Destinatari", "driver": "Corriere", "drivers": "Corrieri",
         "delivery": "Spedizione", "deliveries": "Spedizioni", "route": "Giro spedizioni", "routes": "Giri spedizioni",
         "stop": "Tentativo", "stops": "Tentativi", "route_planning": "Pianificazione spedizioni"},
        ["Numero spedizione / tracking", "Mittente e destinatario", "Numero colli", "Peso e volume", "Tentativi di consegna", "Giacenza", "Foto prova consegna", "Firma"],
        {"needs_photo_proof": True},
        ["tracking", "mittente", "numero_colli", "peso", "volume", "tentativo", "giacenza"],
        ["In consegna", "Consegnata", "Cliente assente", "Indirizzo errato", "Rifiutata", "In giacenza"],
    ),
    "ecommerce": _config(
        "E-commerce / Consegna ordini",
        "Shop online e aziende retail che consegnano ordini con mezzi propri.",
        {"customer": "Destinatario", "customers": "Destinatari", "driver": "Corriere", "drivers": "Corrieri",
         "delivery": "Ordine", "deliveries": "Ordini", "route": "Giro ordini", "routes": "Giri ordini",
         "stop": "Consegna ordine", "stops": "Consegne ordine", "scheduled_routes": "Ordini programmati",
         "active_routes": "Ordini in consegna", "completed_today": "Ordini completati oggi", "route_planning": "Pianificazione ordini"},
        ["Numero ordine", "Tracking spedizione", "Integrazione Shopify", "Email cliente", "Telefono cliente", "Contrassegno", "Reso", "Orario previsto consegna", "Prova consegna"],
        {"needs_photo_proof": True, "has_time_windows": True},
        ["numero_ordine", "tracking", "email_cliente", "contrassegno", "reso", "orario_previsto"],
        ["Da consegnare", "Consegnato", "Cliente assente", "Reso", "Rifiutato", "Riprogrammare"],
    ),
    "food_delivery": _config(
        "Food delivery / Ristorazione",
        "Ristoranti, pizzerie, dark kitchen, catering e rider.",
        {"customer": "Cliente finale", "customers": "Clienti finali", "driver": "Rider", "drivers": "Rider",
         "delivery": "Ordine food", "deliveries": "Ordini food", "route": "Turno", "routes": "Turni",
         "stop": "Consegna", "stops": "Consegne", "scheduled_routes": "Turni programmati", "active_routes": "Turni in corso",
         "completed_today": "Turni completati oggi", "route_planning": "Pianificazione turno rider", "new_route": "+ Nuovo turno"},
        ["Menu / catalogo prodotti", "Ristorante o punto vendita", "Orario ritiro", "Orario consegna", "Pagamento", "Note ordine", "Ritardi ordine"],
        {"has_time_windows": True},
        ["ristorante", "menu", "prodotti", "orario_ritiro", "pagamento", "note_ordine"],
        ["Da ritirare", "Ritirato", "In consegna", "Consegnato", "Cliente non risponde", "Annullato"],
    ),
    "healthcare": _config(
        "Farmaceutico / Sanitario",
        "Farmacie, laboratori, materiale sanitario e consegne tracciate.",
        {"customer": "Punto consegna", "customers": "Punti consegna", "driver": "Operatore", "drivers": "Operatori",
         "vehicle": "Veicolo", "vehicles": "Veicoli", "delivery": "Consegna tracciata", "deliveries": "Consegne tracciate",
         "route": "Giro sanitario", "routes": "Giri sanitari", "stop": "Tappa", "stops": "Tappe", "route_planning": "Pianificazione sanitaria"},
        ["Firma obbligatoria", "Tracciabilità", "Priorità", "Temperatura", "Destinatario autorizzato", "Note conformità", "Orario tassativo"],
        {"needs_signature": True, "has_refrigerated_goods": True, "has_time_windows": True},
        ["temperatura", "priorita", "codice_consegna", "destinatario_autorizzato", "note_conformita"],
        ["In preparazione", "In consegna", "Consegnata con firma", "Non consegnata", "Temperatura non conforme", "Urgente"],
    ),
    "other": _config(
        "Altro / configurazione generica",
        "Configurazione standard per aziende fuori dai settori principali.",
        features=["Pianificazione", "Clienti", "Autisti", "Mezzi", "Storico", "Report"],
    ),
}

SECTOR_ALIASES = {
    "grossista_distribuzione": "distribution",
    "cash_carry": "distribution",
    "horeca": "distribution",
    "surgelati_refrigerato": "distribution",
    "beverage": "distribution",
    "lavanderia": "distribution",
    "ricambi_auto": "distribution",
    "corriere_locale": "logistics",
    "ecommerce_spedizioni": "ecommerce",
    "delivery_food": "food_delivery",
    "farmaceutico": "healthcare",
    "sanitario": "healthcare",
    "altro": "other",
}

DEFAULT_SECTOR_KEY = "distribution"
PUBLIC_SECTOR_KEYS = ["distribution", "logistics", "ecommerce", "food_delivery", "healthcare", "other"]

def normalize_sector_key(value: str | None) -> str:
    key = (value or "").strip()
    if key in SECTOR_CONFIGS:
        return key
    if key in SECTOR_ALIASES:
        return SECTOR_ALIASES[key]
    return "other"

def get_sector_config(value: str | None) -> dict:
    key = normalize_sector_key(value)
    cfg = SECTOR_CONFIGS.get(key) or SECTOR_CONFIGS["other"]
    return {"key": key, **cfg}

def public_sector_options() -> list[dict]:
    return [{"key": key, "name": SECTOR_CONFIGS[key]["name"]} for key in PUBLIC_SECTOR_KEYS]
