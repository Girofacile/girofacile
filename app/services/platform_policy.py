"""Runtime policy shared by registration, catalogue and request guards."""
from fastapi import HTTPException
from .platform_settings import get_platform_setting, setting_bool
from .plan_catalog import TRIAL_DAYS, PLAN_LIMITS


def trial_days(db):
    try:
        return max(0, min(365, int(get_platform_setting(db, 'trial_days', str(TRIAL_DAYS)))))
    except ValueError:
        return TRIAL_DAYS


def default_plan(db):
    plan = get_platform_setting(db, 'default_plan', 'starter')
    return plan if plan in PLAN_LIMITS else 'starter'


def require_registration(db):
    if setting_bool(db, 'maintenance_mode') or not setting_bool(db, 'registrations_enabled', True):
        raise HTTPException(503, 'Le nuove registrazioni sono temporaneamente sospese')


def require_available(db):
    if setting_bool(db, 'maintenance_mode'):
        raise HTTPException(503, 'Servizio temporaneamente in manutenzione. Riprova più tardi.')
