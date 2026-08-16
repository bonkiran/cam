import os

import uvicorn

from app.biomechanics import router as biomechanics_router
from app.main import app

# Register the optional PoseForge/SAM-3D biomechanics API without changing the
# existing FastAPI application module. Docker/Render starts through run.py.
app.include_router(biomechanics_router)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port, reload=False)
