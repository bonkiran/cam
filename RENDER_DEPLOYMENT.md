# Deploy CrickAnalysis on Render

This repository is configured for Render with `render.yaml`.

## Why a persistent disk is enabled

The MVP currently uses SQLite and stores uploaded videos/generated frames on the filesystem. Render's ordinary service filesystem is ephemeral, so `render.yaml` mounts a persistent disk at `/var/data` and sets `CRICKANALYSIS_DATA_DIR=/var/data`.

## Recommended first deployment

- Service: Render Web Service
- Runtime: Docker
- Region: Virginia
- Instance: Starter
- Persistent disk: 5 GB mounted at `/var/data`
- Health check: `/api/health`
- Upload safety cap: 1 GB per file

## Deploy from GitHub

1. Create a new GitHub repository named `crickanalysis` (do not use the ESAP repository).
2. Push this project to that repository.
3. In Render select **New > Blueprint**.
4. Connect the `crickanalysis` GitHub repository.
5. Render detects `render.yaml`.
6. Review the Starter instance + 5 GB disk and click **Apply**.
7. Wait for the deployment to become Live.
8. Open the generated `*.onrender.com` URL.
9. Verify `/api/health` returns `{"ok": true, ...}`.
10. Upload a short cricket video and confirm it remains available after a manual redeploy.

## Later production architecture

The persistent-disk/SQLite architecture is deliberately simple for MVP validation. Before horizontal scaling, move metadata to Postgres and videos/frames to object storage such as S3/R2.
