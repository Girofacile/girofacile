"""Company preference combined with the existing subscription entitlement."""
from fastapi import HTTPException

from .plans import get_plan_limits, is_plan_active, require_feature


def agents_enabled(user) -> bool:
    return bool(
        user
        and getattr(user, "agents_enabled", False)
        and get_plan_limits(user.plan or "starter").get("has_agents", False)
        and is_plan_active(user)
    )


def require_agents_enabled(user):
    if not user:
        raise HTTPException(403, "Azienda non disponibile")
    require_feature(user, "has_agents")
    if not getattr(user, "agents_enabled", False):
        raise HTTPException(403, "La funzione Agenti è disattivata nelle impostazioni aziendali.")
