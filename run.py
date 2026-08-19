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
from app.academy_auth_api import router as academy_auth_router
from app.academy_parent_billing_api import router as academy_parent_billing_router
from app.academy_reviews_api import router as academy_reviews_router
from app.academy_rbac_middleware import install_academy_management_rbac
from app.biomechanics import router as biomechanics_router
from app.system_api import router as system_router

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
app.include_router(academy_auth_router)
app.include_router(academy_parent_billing_router)
app.include_router(academy_reviews_router)
app.include_router(system_router)
app.router.routes.extend(spa_routes)

# Once the first Owner account exists, the generic Academy management surface
# becomes Owner/Admin-only. Role-specific APIs keep their own narrower controls.
install_academy_management_rbac(app)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port, reload=False)
