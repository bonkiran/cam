import os

import uvicorn

# Import the core FastAPI app first. app.main initializes the base database schema
# (academies, players, videos, etc.) before dependent Academy modules create tables
# that reference those core entities.
from app.main import app
from app.academy_api import router as academy_router
from app.academy_programs_api import router as academy_programs_router
from app.academy_coaches_api import router as academy_coaches_router
from app.academy_batches_api import router as academy_batches_router
from app.academy_batch_roster_lifecycle_api import router as academy_batch_roster_router
from app.academy_attendance_api import router as academy_attendance_router
from app.academy_matches_api import router as academy_matches_router
from app.academy_tournaments_api import router as academy_tournaments_router
from app.academy_fees_api import router as academy_fees_router
from app.academy_payments_v2_api import router as academy_payments_router
from app.academy_payment_provider_api import router as academy_payment_provider_router
from app.academy_finance_operations_api import router as academy_finance_operations_router
from app.academy_demo_cleanup_api import router as academy_demo_cleanup_router
from app.academy_auth_api import (
    ROLE_PERMISSIONS,
    _user_row,
    current_access_user,
    require_access_admin,
    router as academy_auth_router,
)
from app.academy_registration_api import router as academy_registration_router
from app.academy_registration_branding_api import router as academy_registration_branding_router
from app.academy_registration_validation_policy import apply_registration_validation_policy
from app.academy_enrollment_api import router as academy_enrollment_router
from app.academy_enrollment_payment_api import router as academy_enrollment_payment_router
from app.academy_enrollment_completion_api import router as academy_enrollment_completion_router
from app.academy_parent_billing_api import router as academy_parent_billing_router
from app.academy_parent_payment_policy_api import router as academy_parent_payment_policy_router
from app.academy_dashboard_api import router as academy_dashboard_router
from app.academy_current_weather_api import router as academy_current_weather_router
from app.academy_owner_console_api import router as academy_owner_console_router
from app.academy_reviews_api import router as academy_reviews_router
from app.academy_rbac_middleware import install_academy_management_rbac
from app.biomechanics import router as biomechanics_router
from app.database import fetch_one
from app.system_api import router as system_router

# Registration process policy: Emergency Contact 1 is required and Emergency
# Contact 2 is optional. Public registration validates phone and US address data,
# and does not collect a separate Guardian/pickup-authorization section.
apply_registration_validation_policy()

# Temporary controlled-pilot mode. While CAM_TEMP_ADMIN_MODE=1, the current web
# deployment behaves as a single Admin console so the Academy UX can be tested
# without repeatedly establishing a browser session. Track B.0 will remove this
# bypass when tenant-aware authentication is introduced.
TEMP_ADMIN_MODE = os.environ.get("CAM_TEMP_ADMIN_MODE", "0").strip().lower() in {
    "1", "true", "yes", "on"
}


def _temporary_admin_user() -> dict:
    row = fetch_one(
        """
        SELECT id
        FROM academy_users
        ORDER BY CASE WHEN role IN ('owner','admin') THEN 0 ELSE 1 END, id
        LIMIT 1
        """
    )
    if row:
        user = _user_row(int(row["id"]))
        user["display_name"] = "Admin"
        user["role"] = "admin"
        user["permissions"] = list(ROLE_PERMISSIONS["admin"])
        return user
    # The Render free pilot can restart with an empty ephemeral access table.
    # Use a stable synthetic ID so read-only dashboard serialization does not
    # fail on int(None). Write paths must continue to tolerate a non-persisted
    # temporary user and Track B.0 will replace this bypass entirely.
    return {
        "id": 0,
        "academy_id": None,
        "email": "admin@temporary.local",
        "display_name": "Admin",
        "role": "admin",
        "status": "active",
        "permissions": list(ROLE_PERMISSIONS["admin"]),
        "linked_name": None,
    }


if TEMP_ADMIN_MODE:
    # FastAPI dependency overrides cover endpoints that explicitly depend on the
    # access helpers. The RBAC middleware separately honors the same env flag.
    app.dependency_overrides[current_access_user] = _temporary_admin_user
    app.dependency_overrides[require_access_admin] = _temporary_admin_user

# Register optional API routers after app.main is imported. The SPA catch-all
# route is temporarily removed and restored last so specific GET API routes
# always remain reachable.
spa_routes = [route for route in app.router.routes if getattr(route, "path", None) == "/{path:path}"]
for route in spa_routes:
    app.router.routes.remove(route)

# Track A roster lifecycle extends the original add-player endpoint with future
# session synchronization. Remove only that legacy POST route before including
# the enhanced router; every other Batches & Sessions route stays untouched.
academy_batches_router.routes[:] = [
    route
    for route in academy_batches_router.routes
    if not (
        getattr(route, "path", None) == "/api/academy/batches/{batch_id}/players"
        and "POST" in (getattr(route, "methods", set()) or set())
    )
]

# Parents/guardians pay invoices in full. Keep the original Parent Billing
# surface, but replace only its first-version pay route with the stricter policy
# router so partial amounts cannot be posted through UI or direct API calls.
academy_parent_billing_router.routes[:] = [
    route
    for route in academy_parent_billing_router.routes
    if not (
        getattr(route, "path", None) == "/api/academy/parent/invoices/{invoice_id}/pay"
        and "POST" in (getattr(route, "methods", set()) or set())
    )
]

app.include_router(biomechanics_router)
app.include_router(academy_router)
app.include_router(academy_programs_router)
app.include_router(academy_coaches_router)
app.include_router(academy_batch_roster_router)
app.include_router(academy_batches_router)
app.include_router(academy_attendance_router)
app.include_router(academy_matches_router)
app.include_router(academy_tournaments_router)
app.include_router(academy_fees_router)
app.include_router(academy_payments_router)
app.include_router(academy_payment_provider_router)
app.include_router(academy_finance_operations_router)
app.include_router(academy_demo_cleanup_router)
app.include_router(academy_auth_router)
app.include_router(academy_registration_router)
app.include_router(academy_registration_branding_router)
app.include_router(academy_enrollment_router)
app.include_router(academy_enrollment_payment_router)
app.include_router(academy_enrollment_completion_router)
app.include_router(academy_parent_billing_router)
app.include_router(academy_parent_payment_policy_router)
app.include_router(academy_dashboard_router)
app.include_router(academy_current_weather_router)
app.include_router(academy_owner_console_router)
app.include_router(academy_reviews_router)
app.include_router(system_router)


@app.get("/api/cam-mode")
def cam_mode():
    return {
        "temporary_admin_mode": TEMP_ADMIN_MODE,
        "display_name": "Admin" if TEMP_ADMIN_MODE else None,
        "role": "admin" if TEMP_ADMIN_MODE else None,
    }


app.router.routes.extend(spa_routes)

# Once the first Owner account exists, the generic Academy management surface
# becomes Owner/Admin-only. Role-specific APIs keep their own narrower controls.
install_academy_management_rbac(app)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port, reload=False)