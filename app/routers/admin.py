"""Compatibility router for callers importing app.routers.admin.

The application registers the section routers directly in main.py. This
aggregate is retained for existing standalone integrations and tests only.
"""
from fastapi import APIRouter

from . import admin_billing, admin_database, admin_profile, admin_server, admin_support, admin_users

router = APIRouter()
router.include_router(admin_profile.router)
router.include_router(admin_server.router)
router.include_router(admin_database.router)
router.include_router(admin_users.router)
router.include_router(admin_support.router)
router.include_router(admin_billing.router)
