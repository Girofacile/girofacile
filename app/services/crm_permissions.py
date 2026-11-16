"""CRM grants are explicit; legacy 'all' never grants CRM to collaborators."""
from fastapi import HTTPException

CRM_PERMISSIONS = {
    'crm_access': 'CRM: accedere al proprio portafoglio',
    'crm_write': 'CRM: gestire aziende, contatti e attività',
    'crm_view_all': 'CRM: vedere e gestire tutto il portafoglio',
    'crm_export': 'CRM: esportare il portafoglio visibile',
}


def allowed(actor, permission='crm_access'):
    if actor.get('role') == 'superadmin':
        return True
    permissions = actor.get('permissions') or {}
    return isinstance(permissions, dict) and permissions.get('crm_access') is True and permissions.get(permission) is True


def require(actor, permission='crm_access'):
    if not allowed(actor, permission):
        raise HTTPException(403, 'Accesso CRM non autorizzato')


def guard_grants(actor, permissions, previous=None):
    """Only the owner may change CRM grants, including on their own account."""
    if not isinstance(permissions, dict):
        raise HTTPException(422, 'Permessi non validi')
    if any(key in permissions and not isinstance(permissions[key], bool) for key in CRM_PERMISSIONS):
        raise HTTPException(422, 'I permessi CRM devono essere attivati o disattivati esplicitamente')
    if actor.get('role') == 'superadmin':
        return
    old = previous or {}
    if any(bool(permissions.get(k)) != bool(old.get(k)) for k in CRM_PERMISSIONS):
        raise HTTPException(403, 'Solo il Super Admin può autorizzare il CRM')


def guard_account(actor, collaborator):
    """Delegated account managers cannot take over a CRM identity by resetting its password."""
    import json
    if actor.get('role') == 'superadmin':
        return
    try:
        permissions = json.loads(collaborator.permissions_json or '{}')
    except (TypeError, ValueError):
        permissions = {}
    if isinstance(permissions, dict) and permissions.get('crm_access') is True:
        raise HTTPException(403, 'Solo il Super Admin può gestire questo account commerciale')
