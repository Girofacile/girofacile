"""Company delegation. Unknown operations are owner-only, never implicitly allowed.

Resource ownership continues to use User.id; the authenticated actor is a separate
credential. Dependencies re-read active status and grants on EVERY request.
"""
import json
from fastapi import HTTPException

RESOURCE_LABELS = {"customers": "Clienti", "deposits": "Depositi", "vehicles": "Mezzi",
                   "drivers": "Autisti", "agents": "Agenti"}
CATALOG = [
    {"key": f"{resource}.{action}", "group": label, "label": title}
    for resource, label in RESOURCE_LABELS.items()
    for action, title in (("read", "Visualizza"), ("create", "Crea"), ("update", "Modifica"), ("delete", "Elimina"))
] + [
    {"key": key, "group": group, "label": label} for key, group, label in (
        ("orders.read", "Ordini", "Visualizza ordini"),
        ("orders.create", "Ordini", "Crea ordini"),
        ("orders.update", "Ordini", "Correggi e verifica ordini"),
        ("orders.import", "Ordini", "Importa ordini"),
        ("orders.match", "Ordini", "Associa clienti agli ordini"),
        ("orders.integrations", "Ordini", "Gestisci fonti e credenziali"),
        ("orders.plan", "Ordini", "Trasferisci ordini alla pianificazione"),
        ("routes.read", "Giri", "Visualizza giri, storico e posizione del mezzo"),
        ("routes.plan", "Giri", "Pianifica e calcola percorsi"),
        ("routes.program", "Giri", "Programma e assegna giri"),
        ("routes.manage", "Giri", "Annulla e completa giri"),
        ("routes.tracking", "Giri", "Gestisci link operativi e tracking"),
        ("dashboard.read", "Dashboard", "Visualizza panoramica operativa"),
        ("reports.read", "Report", "Visualizza ed esporta report"),
        ("chat.read", "Chat autisti", "Leggi conversazioni"),
        ("chat.write", "Chat autisti", "Invia messaggi"),
        ("company.read", "Azienda", "Visualizza dati aziendali"),
        ("company.update", "Azienda", "Modifica dati aziendali"),
        ("settings.update", "Impostazioni", "Modifica impostazioni operative"),
        ("support.read", "Supporto", "Visualizza richieste aziendali"),
        ("support.write", "Supporto", "Crea richieste di assistenza"),
        ("notifications.read", "Notifiche", "Leggi e gestisci notifiche aziendali"),
    )
]
VALID = {item["key"] for item in CATALOG}
DEPENDENCIES = {
    "routes.plan": {"routes.read", "customers.read", "deposits.read", "vehicles.read", "drivers.read", "agents.read"},
    "routes.program": {"routes.plan"}, "routes.manage": {"routes.read"}, "routes.tracking": {"routes.read"},
    "dashboard.read": {"routes.read", "vehicles.read", "drivers.read"},
    "reports.read": {"routes.read", "customers.read", "drivers.read", "agents.read"},
    "chat.write": {"chat.read"}, "chat.read": {"drivers.read", "routes.read"},
    "company.update": {"company.read"}, "support.write": {"support.read"},
    "settings.update": {"company.update"},
}
for resource in RESOURCE_LABELS:
    for action in ("create", "update", "delete"):
        DEPENDENCIES[f"{resource}.{action}"] = {f"{resource}.read"}
for action in ('create', 'update', 'import', 'match', 'integrations', 'plan'):
    DEPENDENCIES[f'orders.{action}'] = {'orders.read'}
DEPENDENCIES['orders.plan'].add('routes.plan')
DEPENDENCIES['orders.match'].add('customers.read')
DEPENDENCIES["customers.read"] = {"agents.read"}


def normalize_permissions(value):
    if not isinstance(value, list) or any(not isinstance(key, str) or key not in VALID for key in value):
        raise HTTPException(422, "Permessi non validi")
    grants = set(value)
    while True:
        expanded = grants | set().union(*(DEPENDENCIES.get(key, set()) for key in grants))
        if expanded == grants:
            return sorted(grants)
        grants = expanded


def permissions_for(actor):
    try:
        value = json.loads(actor.permissions_json or "[]")
        # Do not grant new dependencies implicitly when reading historical data.
        return set(value) & VALID if isinstance(value, list) else set()
    except (TypeError, ValueError):
        return set()


# Presets are editable starting points, not authentication roles. Keep each
# permission explicit: adding a new catalogue key must not silently widen a
# preset or an existing collaborator's stored grants.
_PRESET_DEFINITIONS = (
    ("operator", "Operatore",
     "Tutte le funzioni aziendali, inclusi dati aziendali e impostazioni. "
     "Piano, fatturazione e gestione collaboratori restano riservati al titolare.",
     (
         "customers.read", "customers.create", "customers.update", "customers.delete",
         "deposits.read", "deposits.create", "deposits.update", "deposits.delete",
         "vehicles.read", "vehicles.create", "vehicles.update", "vehicles.delete",
         "drivers.read", "drivers.create", "drivers.update", "drivers.delete",
         "agents.read", "agents.create", "agents.update", "agents.delete",
         "routes.read", "routes.plan", "routes.program", "routes.manage", "routes.tracking",
         "dashboard.read", "reports.read", "chat.read", "chat.write",
         "company.read", "company.update", "settings.update",
         "orders.read", "orders.create", "orders.update", "orders.import",
         "orders.match", "orders.integrations", "orders.plan",
         "support.read", "support.write", "notifications.read",
     )),
    ("planner", "Pianificatore",
     "Consulta le risorse, pianifica e gestisce i giri, usa report, chat e assistenza. "
     "Non modifica anagrafiche, dati aziendali o impostazioni.",
     (
         "orders.read",
         "customers.read", "deposits.read", "vehicles.read", "drivers.read", "agents.read",
         "routes.read", "routes.plan", "routes.program", "routes.manage", "routes.tracking",
         "dashboard.read", "reports.read", "chat.read", "chat.write",
         "support.read", "support.write", "notifications.read",
     )),
    ("read_only", "Sola lettura",
     "Consulta risorse, giri, report, chat, dati aziendali e assistenza. "
     "Non modifica i dati operativi.",
     (
         "orders.read",
         "customers.read", "deposits.read", "vehicles.read", "drivers.read", "agents.read",
         "routes.read", "dashboard.read", "reports.read", "chat.read",
         "company.read", "support.read", "notifications.read",
     )),
)


def permission_presets():
    """Return fresh metadata; the owner still saves an explicit permissions list."""
    return [
        {"key": key, "label": label, "description": description,
         "permissions": sorted(grants)}
        for key, label, description, grants in _PRESET_DEFINITIONS
    ]


# Exact FastAPI route templates, not prefixes controlled by the client.
RULES = {}
for resource in RESOURCE_LABELS:
    for method, suffix, action in (("GET", "", "read"), ("POST", "", "create"),
                                   ("PUT", "/{item_id}", "update"), ("DELETE", "/{item_id}", "delete")):
        RULES[method, f"/api/{resource}{suffix}"] = {f"{resource}.{action}"}


def rule(method, paths, *grants):
    for path in paths:
        RULES[method, path] = set(grants)


rule("GET", ["/api/orders", "/api/orders/{order_id}"], "orders.read")
rule("POST", ["/api/orders"], "orders.create")
rule("PUT", ["/api/orders/{order_id}"], "orders.update")
rule("POST", ["/api/orders/{order_id}/status", "/api/orders/{order_id}/verify-address"], "orders.update")
rule("GET", ["/api/settings", "/api/sector-config"], "session")
rule("GET", ["/api/company-profile"], "company.read")
rule("PUT", ["/api/company-profile"], "company.update")
rule("PUT", ["/api/settings"], "settings.update")
rule("GET", ["/api/routes", "/api/routes/operativi", "/api/routes/{route_id}",
             "/api/routes/{route_id}/position", "/api/routes/{route_id}/live", "/api/routes/{route_id}/map-data",
             "/api/deliveries/{delivery_id}/evidence/{kind}", "/api/dashboard/completed-deliveries-today"], "routes.read")
rule("GET", ["/api/resources/availability"], "routes.plan")
rule("POST", ["/api/routes/optimize", "/api/routes/recalculate-manual", "/api/routes/verify-stop-address",
              "/api/routes/{route_id}/refresh-traffic", "/api/routes/{route_id}/ai-explanation"], "routes.plan")
rule("POST", ["/api/routes/{route_id}/program"], "routes.program")
rule("POST", ["/api/routes/{route_id}/cancel", "/api/routes/{route_id}/complete"], "routes.manage")
rule("POST", ["/api/routes/{route_id}/generate-token", "/api/deliveries/{delivery_id}/tracking"], "routes.tracking")
rule("DELETE", ["/api/deliveries/{delivery_id}/tracking"], "routes.tracking")
rule("POST", ["/api/customers/import"], "customers.create")
rule("POST", ["/api/customers/verify-address-preview"], "customers.create", "customers.update")
rule("POST", ["/api/customers/{item_id}/verify-address", "/api/customers/verify-pending"], "customers.update")
rule("GET", ["/api/vehicles/usage", "/api/vehicles/fuel-prices/current"], "vehicles.read")
rule("GET", ["/api/vehicles/lookup-plate/{plate}"], "vehicles.create", "vehicles.update")
for resource in ("agents", "drivers"):
    rule("POST", [f"/api/{resource}/{{item_id}}/invite"], f"{resource}.update")
rule("GET", ["/api/reports/summary", "/api/reports/ai-summary", "/api/reports/export"], "reports.read")
rule("GET", ["/api/driver/admin/chat-threads", "/api/driver/admin/chat/{route_id}",
             "/api/driver/admin/direct-chat/{driver_id}"], "chat.read")
rule("POST", ["/api/driver/admin/chat/{route_id}", "/api/driver/admin/direct-chat/{driver_id}"], "chat.write")
rule("GET", ["/api/support/tickets"], "support.read")
rule("POST", ["/api/support/tickets", "/api/support/tickets/assist-text"], "support.write")
rule("GET", ["/api/notifications", "/api/notifications/count"], "notifications.read")
rule("POST", ["/api/notifications/{notification_id}/read", "/api/notifications/read-all"], "notifications.read")
rule("GET", ["/api/address/search"], "routes.plan", "customers.create", "customers.update", "deposits.create", "deposits.update")


def authorize(request, actor):
    template = getattr(request.scope.get("route"), "path", request.url.path)
    required = RULES.get((request.method, template))
    if required == {"session"}:
        return
    if not required or not (permissions_for(actor) & required):
        raise HTTPException(403, "Il tuo account non è autorizzato a questa operazione")
