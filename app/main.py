"""
GiroFacile SaaS - main.py
Setup applicazione + inclusione router.
Tutta la logica è nei moduli app/routers/ e app/services/.
"""
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from .core.config import APP_PASSWORD, APP_USER
from .core.http_security import IS_PRODUCTION, login_rate_limit_middleware
from .core.security import hash_password
from .database import Base, engine, get_db
from .models import Agent, Customer, Deposit, Driver, RoutePlan, User, Vehicle, PasswordResetToken, DistanceCache
from .routers import (
    admin_billing, admin_database, admin_profile, admin_server, admin_support, admin_users,
    agents, auth, billing, customers, tracking, collaborators, orders,
    deposits, reports, routes, operator, notifications, settings, support, driver as driver_router_module, agent as agent_router_module,
)
from .routers.vehicles_drivers import drivers_router, vehicles_router
from .services.geocoding import search_address_autocomplete
from .services.object_storage import StorageUnavailable

# -----------------------------------------------------------------------
# App
# -----------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app):
    from .migrations import require_current_schema
    require_current_schema(engine)
    yield


app = FastAPI(
    lifespan=lifespan,
    title="GiroFacile SaaS",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)

# Protezione centralizzata contro tentativi ripetuti sui login.
app.middleware("http")(login_rate_limit_middleware)


@app.middleware("http")
async def platform_maintenance(request: Request, call_next):
    from starlette.concurrency import run_in_threadpool
    from .services.platform_settings import setting_bool
    from .database import SessionLocal
    path = request.url.path
    exempt = path.startswith(('/api/admin/', '/api/billing/', '/api/support', '/api/password-reset')) or path.endswith('/logout')
    if path.startswith('/api/') and not exempt:
        def enabled():
            with SessionLocal() as db:
                return setting_bool(db, 'maintenance_mode')
        if await run_in_threadpool(enabled):
            return JSONResponse(status_code=503, content={'detail': 'Servizio temporaneamente in manutenzione. Riprova più tardi.'}, headers={'Retry-After': '60'})
    return await call_next(request)


@app.exception_handler(StorageUnavailable)
async def pod_storage_error(request: Request, exc: StorageUnavailable):
    from .services.error_monitor import log_exception
    error_id = log_exception(request, exc, severity='high')
    return JSONResponse(status_code=503, content={'detail': exc.detail, 'error_id': error_id},
                        headers={'Cache-Control': 'no-store'})


@app.middleware("http")
async def system_error_monitor(request: Request, call_next):
    """Registra gli errori tecnici veri e avvisa il Super Admin.

    Non intercetta errori ordinari come password errata o 404/401, perché FastAPI
    li gestisce come risposte HTTP previste.
    """
    try:
        return await call_next(request)
    except Exception as exc:
        from .services.error_monitor import log_exception
        error_id = log_exception(request, exc)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Errore interno. Il Super Admin è stato avvisato.",
                "error_id": error_id,
            },
        )

static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# -----------------------------------------------------------------------
# Include router
# -----------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(collaborators.router)
app.include_router(orders.router)
app.include_router(deposits.router)
app.include_router(agents.router)
app.include_router(customers.router)
app.include_router(vehicles_router)
app.include_router(drivers_router)
app.include_router(routes.router)
app.include_router(tracking.router)
app.include_router(reports.router)
app.include_router(admin_profile.router)
app.include_router(admin_server.router)
app.include_router(admin_database.router)
app.include_router(admin_users.router)
app.include_router(admin_support.router)
app.include_router(admin_billing.router)
app.include_router(billing.router)
app.include_router(operator.router)
app.include_router(notifications.router)
app.include_router(settings.router)
app.include_router(support.router)
app.include_router(driver_router_module.router)
app.include_router(agent_router_module.router)


# -----------------------------------------------------------------------
# Endpoint pagine HTML
# -----------------------------------------------------------------------
@app.get("/")
def index(request_headers: dict = None):
    # La landing page pubblica è il punto di ingresso
    return FileResponse(
        static_dir / "landing" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )




@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Serve la favicon ufficiale GiroFacile in formato ICO."""
    return FileResponse(
        static_dir / "favicon.ico",
        media_type="image/x-icon",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/login")
def unified_login():
    return FileResponse(
        static_dir / "dashboard" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/dashboard")
def dashboard():
    return FileResponse(
        static_dir / "dashboard" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/mobile")
def mobile():
    return FileResponse(
        static_dir / "mobile" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/reset-password/{token}")
def reset_password_page(token: str):
    return FileResponse(
        static_dir / "dashboard" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )



@app.get("/privacy-policy")
def privacy_policy_page():
    return FileResponse(static_dir / "legal" / "privacy-policy.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/cookie-policy")
def cookie_policy_page():
    return FileResponse(static_dir / "legal" / "cookie-policy.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/termini-condizioni")
def terms_page():
    return FileResponse(static_dir / "legal" / "termini-condizioni.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/sicurezza")
def security_page():
    return FileResponse(static_dir / "legal" / "sicurezza.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/dpa-responsabile-trattamento")
def dpa_page():
    return FileResponse(static_dir / "legal" / "dpa-responsabile-trattamento.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/subprocessors")
def subprocessors_page():
    return FileResponse(static_dir / "legal" / "subprocessors.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


# -----------------------------------------------------------------------
# Autocomplete indirizzi
# -----------------------------------------------------------------------
from .core.dependencies import current_user
from .models import User as UserModel


@app.get("/api/address/search")
def address_search(
    q: str, comune: str = "", provincia: str = "",
    db: Session = Depends(get_db),
    _user: UserModel = Depends(current_user),
):
    return search_address_autocomplete(q, comune, provincia, db=db, user_id=_user.id)


# -----------------------------------------------------------------------
# Migrazione DB e utente default
# -----------------------------------------------------------------------


@app.get("/admin/login")
def admin_login_page():
    return FileResponse(
        static_dir / "admin" / "login.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/admin")
def admin_panel():
    return FileResponse(
        static_dir / "admin" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/giro/{token}")
def operator_portal(token: str):
    return FileResponse(
        static_dir / "operator" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/collaborator/setup", include_in_schema=False)
def collaborator_setup():
    # The invitation secret lives in the URL fragment and is submitted via POST.
    return FileResponse(
        static_dir / "collaborator" / "setup.html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/driver")
@app.get("/driver/")
def driver_portal():
    return FileResponse(
        static_dir / "driver" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/driver/setup/{token}")
def driver_setup(token: str):
    return FileResponse(
        static_dir / "driver" / "setup.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/agent")
@app.get("/agent/")
def agent_portal():
    return FileResponse(
        static_dir / "agent" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/agent/setup/{token}")
def agent_setup(token: str):
    return FileResponse(
        static_dir / "agent" / "setup.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )
