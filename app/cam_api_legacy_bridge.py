from __future__ import annotations


class CamLegacyApiBridge:
    """Temporary transport bridge for pre-CAM /api/academy clients.

    Current application code uses /api/cam. Persisted external bookmarks or old
    test clients can still call /api/academy during the migration window; those
    requests are rewritten before authorization and route matching.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            path = str(scope.get("path") or "")
            if path == "/api/academy" or path.startswith("/api/academy/"):
                suffix = path[len("/api/academy") :]
                scope = dict(scope)
                scope["path"] = "/api/cam" + suffix
                scope["raw_path"] = scope["path"].encode("utf-8")
        await self.app(scope, receive, send)


def install_cam_legacy_api_bridge(app) -> None:
    app.add_middleware(CamLegacyApiBridge)
