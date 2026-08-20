from __future__ import annotations

import os

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from .academy_auth_api import current_access_user
from .database import fetch_one

# These Academy endpoints already enforce their own role/identity rules and
# therefore must not be reduced to Owner/Admin-only by the legacy-management gate.
SELF_AUTHORIZED_PREFIXES = (
    "/api/academy/access",
    "/api/academy/parent",
    "/api/academy/reviews",
    "/api/academy/registration",
)


def _temporary_admin_mode() -> bool:
    return os.environ.get("CAM_TEMP_ADMIN_MODE", "0").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _access_is_bootstrapped() -> bool:
    row = fetch_one("SELECT COUNT(*) AS count FROM academy_users") or {"count": 0}
    return int(row.get("count") or 0) > 0


def _error_response(exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def install_academy_management_rbac(app) -> None:
    """Protect legacy Academy management APIs after the first access user exists.

    Migration behavior is deliberate:
    - Before access bootstrap: existing Academy setup APIs remain usable so an
      academy can create its initial profile/reference records and bootstrap the
      first owner without being locked out.
    - After bootstrap: generic Academy management APIs are Owner/Admin-only.
    - Parent, Access/Roles, Registration and Player Reviews endpoints retain their
      dedicated fine-grained authorization logic.
    - During the temporary controlled-pilot Admin mode, generic Academy APIs are
      intentionally left open so the current single-Admin web console can be
      manually validated without a browser session. Track B.0 will remove this.

    Role-specific Coach/Parent/Player operational APIs should be added as
    dedicated endpoints rather than reopening the generic management surface.
    """

    @app.middleware("http")
    async def academy_management_rbac(request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or not path.startswith("/api/academy/"):
            return await call_next(request)
        if _temporary_admin_mode():
            return await call_next(request)
        if any(path.startswith(prefix) for prefix in SELF_AUTHORIZED_PREFIXES):
            return await call_next(request)
        if not _access_is_bootstrapped():
            return await call_next(request)

        try:
            user = current_access_user(
                authorization=request.headers.get("authorization"),
                x_cam_session=request.headers.get("x-cam-session"),
            )
        except HTTPException as exc:
            return _error_response(exc)

        if str(user.get("role")) not in {"owner", "admin"}:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Owner or admin access is required for Academy management"},
            )
        return await call_next(request)
