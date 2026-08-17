import os

import uvicorn

from app.academy_api import router as academy_router
from app.biomechanics import router as biomechanics_router
from app.main import app

# Register optional API routers after app.main is imported. The SPA catch-all
# route is temporarily removed and restored last so specific GET API routes
# always remain reachable.
spa_routes = [route for route in app.router.routes if getattr(route, "path", None) == "/{path:path}"]
for route in spa_routes:
    app.router.routes.remove(route)

app.include_router(biomechanics_router)
app.include_router(academy_router)
app.router.routes.extend(spa_routes)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port, reload=False)
