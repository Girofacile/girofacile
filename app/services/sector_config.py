"""Configurazioni settore per adattare testi e impostazioni iniziali di GiroFacile.

v48 - Settori principali ottimizzati
Abbiamo ridotto i settori commerciali a 6 macro-settori + Altro, mantenendo
alias tecnici per compatibilità con le registrazioni create nelle versioni v46/v47.
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

SECTOR_CONFIGS = {
    "distribution": {
        "name": "Distribuzione / Cash & Carry",
        "subtitle": "Grossisti, Cash & Carry, Ho.Re.Ca., surgelati, beverage e consegne programmate.",
        "labels": {
            **COMMON_LABELS,
            "customer": "Cliente",
            "customers": "Clienti",
            "delivery": "Consegna merce",
            "deliveries": "Consegne merce",
            "route_planning": "Pianificazione giro consegne",
        },
        "features": [
            "Codice cliente",
            "Fasce orarie mattina/pomeriggio",
            "Tempo di scarico",
            "Colli e bancali",
            "Sponda / transpallet",
            "ZTL",
            "Firma alla consegna",
        ],
        "recommended_defaults": {
            "has_time_windows": True,
            "needs_signature": True,
            "needs_tail_lift": True,
        },
        "future_fields": ["codice_cliente", "colli", "bancali", "tempo_scarico", "sponda", "ztl"],
        "delivery_statuses": ["Da fare", "Consegnata", "Parziale", "Cliente chiuso", "Rifiutata", "Mancata"],
    },
    "logistics": {
        "name": "Logistica / Corrieri locali",
        "subtitle": "Corrieri locali, ultimo miglio, spedizioni, colli, ritiri e consegne.",
        "labels": {
            **COMMON_LABELS,
            "customer": "Destinatario",
            "customers": "Destinatari",
            "driver": "Corriere",
            "drivers": "Corrieri",
            "delivery": "Spedizione",
            "deliveries": "Spedizioni",
            "route": "Giro spedizioni",
            "routes": "Giri spedizioni",
            "stop": "Tentativo",
            "stops": "Tentativi",
            "route_planning": "Pianificazione spedizioni",
        },
        "features": [
            "Numero spedizione / tracking",
            "Mittente e destinatario",
            "Numero colli",
            "Peso e volume",
            "Tentativi di consegna",
            "Giacenza",
            "Foto prova consegna",
            "Firma",
        ],
        "recommended_defaults": {"needs_photo_proof": True},
        "future_fields": ["tracking", "mittente", "numero_colli", "peso", "volume", "tentativo", "giacenza"],
        "delivery_statuses": ["In consegna", "Consegnata", "Cliente assente", "Indirizzo errato", "Rifiutata", "In giacenza"],
    },
    "ecommerce": {
        "name": "E-commerce / Consegna ordini",
        "subtitle": "Shop online e aziende retail che consegnano ordini con mezzi propri.",
        "labels": {
            **COMMON_LABELS,
            "customer": "Destinatario",
            "customers": "Destinatari",
            "driver": "Corriere",
            "drivers": "Corrieri",
            "delivery": "Ordine",
            "deliveries": "Ordini",
            "route": "Giro ordini",
            "routes": "Giri ordini",
            "stop": "Consegna ordine",
            "stops": "Consegne ordine",
            "scheduled_routes": "Ordini programmati",
            "active_routes": "Ordini in consegna",
            "completed_today": "Ordini completati oggi",
            "route_planning": "Pianificazione ordini",
        },
        "features": [
            "Numero ordine",
            "Tracking spedizione",
            "Integrazione Shopify",
            "Email cliente",
            "Telefono cliente",
            "Contrassegno",
            "Reso",
            "Orario previsto consegna",
            "Prova consegna",
        ],
        "recommended_defaults": {"needs_photo_proof": True, "has_time_windows": True},
        "future_fields": ["numero_ordine", "tracking", "email_cliente", "contrassegno", "reso", "orario_previsto"],
        "delivery_statuses": ["Da consegnare", "Consegnato", "Cliente assente", "Reso", "Rifiutato", "Riprogrammare"],
    },
    "food_delivery": {
        "name": "Food delivery / Ristorazione",
        "subtitle": "Ristoranti, pizzerie, dark kitchen, catering e rider.",
        "labels": {
            **COMMON_LABELS,
            "customer": "Cliente finale",
            "customers": "Clienti finali",
            "driver": "Rider",
            "drivers": "Rider",
            "delivery": "Ordine food",
            "deliveries": "Ordini food",
            "route": "Turno",
            "routes": "Turni",
            "stop": "Consegna",
            "stops": "Consegne",
            "scheduled_routes": "Turni programmati",
            "active_routes": "Turni in corso",
            "completed_today": "Turni completati oggi",
            "route_planning": "Pianificazione turno rider",
            "new_route": "+ Nuovo turno",
        },
        "features": [
            "Menu / catalogo prodotti",
            "Ristorante o punto vendita",
            "Orario ritiro",
            "Orario consegna",
            "Pagamento",
            "Note ordine",
            "Ritardi ordine",
        ],
        "recommended_defaults": {"has_time_windows": True},
        "future_fields": ["ristorante", "menu", "prodotti", "orario_ritiro", "pagamento", "note_ordine"],
        "delivery_statuses": ["Da ritirare", "Ritirato", "In consegna", "Consegnato", "Cliente non risponde", "Annullato"],
    },
    "transfer": {
        "name": "Servizio transfer",
        "subtitle": "NCC, navette hotel, transfer aeroportuali, servizi turistici e corse su prenotazione.",
        "labels": {
            **COMMON_LABELS,
            "customer": "Cliente / passeggero",
            "customers": "Clienti / passeggeri",
            "vehicle": "Veicolo",
            "vehicles": "Veicoli",
            "delivery": "Corsa",
            "deliveries": "Corse",
            "route": "Turno / tratta",
            "routes": "Turni / tratte",
            "stop": "Tappa",
            "stops": "Tappe",
            "scheduled_routes": "Corse programmate",
            "active_routes": "Corse in corso",
            "completed_today": "Corse completate oggi",
            "route_planning": "Pianificazione transfer",
            "new_route": "+ Nuovo transfer",
        },
        "features": [
            "Prenotazioni",
            "Indirizzo ritiro",
            "Destinazione",
            "Orario ritiro",
            "Numero passeggeri",
            "Bagagli",
            "Numero volo / treno",
            "No-show",
        ],
        "recommended_defaults": {"has_time_windows": True},
        "future_fields": ["passeggeri", "bagagli", "numero_volo", "destinazione", "orario_ritiro", "cartello_nominativo"],
        "delivery_statuses": ["Prenotata", "Autista assegnato", "Autista in arrivo", "Cliente a bordo", "Completata", "No-show", "Annullata"],
    },
    "healthcare": {
        "name": "Farmaceutico / Sanitario",
        "subtitle": "Farmacie, laboratori, materiale sanitario e consegne tracciate.",
        "labels": {
            **COMMON_LABELS,
            "customer": "Punto consegna",
            "customers": "Punti consegna",
            "driver": "Operatore",
            "drivers": "Operatori",
            "vehicle": "Veicolo",
            "vehicles": "Veicoli",
            "delivery": "Consegna tracciata",
            "deliveries": "Consegne tracciate",
            "route": "Giro sanitario",
            "routes": "Giri sanitari",
            "stop": "Tappa",
            "stops": "Tappe",
            "route_planning": "Pianificazione sanitaria",
        },
        "features": [
            "Firma obbligatoria",
            "Tracciabilità",
            "Priorità",
            "Temperatura",
            "Destinatario autorizzato",
            "Note conformità",
            "Orario tassativo",
        ],
        "recommended_defaults": {"needs_signature": True, "has_refrigerated_goods": True, "has_time_windows": True},
        "future_fields": ["temperatura", "priorita", "codice_consegna", "destinatario_autorizzato", "note_conformita"],
        "delivery_statuses": ["In preparazione", "In consegna", "Consegnata con firma", "Non consegnata", "Temperatura non conforme", "Urgente"],
    },
    "other": {
        "name": "Altro / configurazione generica",
        "subtitle": "Configurazione standard per aziende fuori dai settori principali.",
        "labels": {**COMMON_LABELS},
        "features": ["Pianificazione", "Clienti", "Autisti", "Mezzi", "Storico", "Report"],
        "recommended_defaults": {},
        "future_fields": [],
        "delivery_statuses": ["Da fare", "Consegnata", "Mancata"],
    },
}

# Alias per compatibilità con i valori usati in v46/v47.
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
    "transfer_service": "transfer",
    "altro": "other",
}

DEFAULT_SECTOR_KEY = "distribution"
PUBLIC_SECTOR_KEYS = ["distribution", "logistics", "ecommerce", "food_delivery", "transfer", "healthcare", "other"]


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
