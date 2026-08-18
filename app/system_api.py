from fastapi import APIRouter

from .database import POSTGRES_ENABLED, connection

router = APIRouter()


@router.get("/api/system/storage")
def storage_status():
    """Expose the active database backend without revealing credentials."""
    with connection() as conn:
        row = conn.execute("SELECT 1").fetchone()
    return {
        "ok": bool(row),
        "database": "postgresql" if POSTGRES_ENABLED else "sqlite",
    }
