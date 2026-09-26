"""SaaS administration router, composed from domain-specific modules."""
from fastapi import APIRouter

from . import (
    admin_billing,
    admin_database,
    admin_profile,
    admin_server,
    admin_support,
    admin_users,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])
router.include_router(admin_profile.router)
router.include_router(admin_server.router)
router.include_router(admin_database.router)
router.include_router(admin_users.router)
router.include_router(admin_support.router)
router.include_router(admin_billing.router)
