import logging

from fastapi import FastAPI, HTTPException, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis import Redis
from redis.exceptions import RedisError
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api import router
from app.automations_api import router as automations_router
from app.billing_api import router as billing_router
from app.config import get_settings
from app.control_room_api import router as control_room_router
from app.customer_portal_api import router as customer_portal_router
from app.database import engine
from app.document_storage import validate_production_document_encryption
from app.documents_contracts_api import router as documents_contracts_router
from app.employee_portal_api import router as employee_portal_router
from app.identity_api import router as identity_router
from app.incidents_api import router as incidents_router
from app.inventory_api import router as inventory_router
from app.key_management_api import router as key_management_router
from app.notification_monitoring import router as notification_monitoring_router
from app.notifications_api import router as notifications_router
from app.owks_api import router as owks_router
from app.personnel_api import router as personnel_router
from app.rate_limit import limiter
from app.scheduling_api import router as scheduling_router
from app.search_api import router as search_router
from app.tasks_api import router as tasks_router
from app.time_tracking_api import router as time_tracking_router
from app.time_tracking_surcharges import router as time_tracking_surcharges_router

settings = get_settings()
validate_production_document_encryption(settings)
logger = logging.getLogger(__name__)
rate_limit_store = (
    Redis.from_url(settings.rate_limit_storage_uri)
    if settings.rate_limit_storage_uri.startswith(("redis://", "rediss://"))
    else None
)


app = FastAPI(title=settings.app_name, version="0.1.0")
app.state.limiter = limiter


def rate_limit_exceeded_handler(_request, _exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "Zu viele Anfragen. Bitte später erneut versuchen."},
    )


app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc: RequestValidationError):
    if request.url.path.startswith(f"{settings.api_prefix}/incidents"):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": "Eingaben für den Vorfall sind ungültig."},
        )
    if request.url.path.startswith(f"{settings.api_prefix}/customer-portal"):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": "Eingaben für den Kundenportalvorgang sind ungültig."},
        )
    return await request_validation_exception_handler(request, exc)


app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
)
app.include_router(router, prefix=settings.api_prefix)
app.include_router(automations_router, prefix=settings.api_prefix)
app.include_router(personnel_router, prefix=settings.api_prefix)
app.include_router(employee_portal_router, prefix=settings.api_prefix)
app.include_router(scheduling_router, prefix=settings.api_prefix)
app.include_router(time_tracking_router, prefix=settings.api_prefix)
app.include_router(time_tracking_surcharges_router, prefix=settings.api_prefix)
app.include_router(tasks_router, prefix=settings.api_prefix)
app.include_router(notifications_router, prefix=settings.api_prefix)
app.include_router(notification_monitoring_router, prefix=settings.api_prefix)
app.include_router(key_management_router, prefix=settings.api_prefix)
app.include_router(inventory_router, prefix=settings.api_prefix)
app.include_router(documents_contracts_router, prefix=settings.api_prefix)
app.include_router(billing_router, prefix=settings.api_prefix)
app.include_router(identity_router, prefix=settings.api_prefix)
app.include_router(incidents_router, prefix=settings.api_prefix)
app.include_router(owks_router, prefix=settings.api_prefix)
app.include_router(control_room_router, prefix=settings.api_prefix)
app.include_router(customer_portal_router, prefix=settings.api_prefix)
app.include_router(search_router, prefix=settings.api_prefix)


@app.get("/health/live", tags=["System"])
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["System"])
def readiness() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.exception("Datenbankverbindung für Readiness-Prüfung fehlgeschlagen")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Datenbankverbindung nicht verfügbar",
        ) from exc
    if rate_limit_store is not None:
        try:
            rate_limit_store.ping()
        except RedisError as exc:
            logger.exception("Rate-Limit-Speicher für Readiness-Prüfung fehlgeschlagen")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rate-Limit-Speicher nicht verfügbar",
            ) from exc
    return {"status": "ready"}
