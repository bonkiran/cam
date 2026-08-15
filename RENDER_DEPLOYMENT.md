# Deploy CrickAnalysis on Render

This repository is configured for a **free Render test deployment** with `render.yaml`.

## Current test configuration

- Service: Render Web Service
- Runtime: Docker
- Region: Virginia
- Instance: Free
- Health check: `/api/health`
- Temporary app data directory: `/tmp/crickanalysis`
- Upload safety cap: 250 MB per file
- No persistent disk

## Important limitation of the free deployment

The MVP currently uses SQLite and stores uploaded videos/generated frames on the local filesystem. Render Free web services do not support persistent disks, so data stored locally can be lost whenever the service restarts or redeploys.

This free configuration is intended only to validate that the application builds, starts, uploads a short video, and runs the analysis workflow in the cloud.

## Deploy from GitHub

1. In Render select **New > Blueprint**.
2. Connect the private `bonkiran/crickanalysis` GitHub repository.
3. Render detects `render.yaml`.
4. Confirm the service shows **Free** and no persistent disk.
5. Click **Apply / Deploy Blueprint**.
6. Wait for the deployment to become Live.
7. Open the generated `*.onrender.com` URL.
8. Verify `/api/health` returns a healthy response.
9. Upload a short cricket video and test the frame/event workflow.

## Next storage architecture

After the cloud workflow is validated, move metadata from SQLite to a persistent database and uploaded videos/generated frames to persistent object storage. At that point we can choose either Render paid storage or an external storage architecture without rebuilding the analysis UI.
