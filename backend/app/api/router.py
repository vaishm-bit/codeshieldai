"""Central router. Each future module registers its router here."""

from fastapi import APIRouter

from app.api.routes import health

api_router = APIRouter()

# Health lives at the root: GET /health
api_router.include_router(health.router)

# Future modules (added in later steps), for example:
# api_router.include_router(upload.router, prefix="/api/v1")
# api_router.include_router(scans.router, prefix="/api/v1")
