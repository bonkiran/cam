# CrickAnalysis — Functional MVP

This is the actual app codebase, not a static prototype.

## What works now

- Left-side vertical navigation shell.
- Real video upload to a FastAPI backend.
- Persistent SQLite storage for players, videos, generated frames, and tagged cricket events.
- Background OpenCV analysis after upload.
- Real metadata extraction: FPS, duration, resolution, and frame count.
- Real motion-intensity timeline from the uploaded video.
- Automatic extraction of timeline frames and motion-peak candidate frames.
- Analysis-detail workspace with HTML5 video player.
- One-frame and ten-frame stepping based on the video's real FPS.
- Clickable generated frame strip.
- Manual event tagging at the current video position: Four, Six, Dot, 1, 2, 3, Wicket, Other.
- Real boundary/event counts reflected on the dashboard.
- Exact evidence-sequence extraction around any current timestamp.
- Re-analysis endpoint.
- Player list generated from uploaded videos.

## Important Phase-1 limitation

The app does **not** claim that high-motion frames are automatically detected cricket shots. They are explicitly presented as *motion candidates*. Automatic delivery segmentation, four/six recognition, pose/biomechanics, bat/ball tracking, reaction time, and shot-selection intelligence are the next CV/ML pipeline phases.

This distinction is deliberate so the app never invents analysis it cannot yet support.

## Run locally

### Windows (PowerShell)

```powershell
cd crickanalysis-app
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

Open: `http://127.0.0.1:8080`

### macOS/Linux

```bash
cd crickanalysis-app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Open: `http://127.0.0.1:8080`

## MVP architecture

```text
Browser SPA
   |
   | REST + video upload
   v
FastAPI
   |---- SQLite: players / videos / frames / events
   |---- OpenCV analyzer
   |       |- video metadata
   |       |- 5 Hz motion timeline
   |       |- motion peak candidates
   |       `- extracted evidence frames
   |
   `---- local media storage
```

## Next development slices

1. Delivery segmentation model.
2. Four/six outcome identification.
3. Bowler release / bounce / impact event detection.
4. Batter pose/keypoint pipeline.
5. Head, feet, knee, hip, elbow and trunk metrics.
6. Bat detection/path/speed.
7. Ball line/length/speed and shot-selection context.
8. Reaction-time measurement.
9. Evidence-linked AI coaching diagnosis.
10. Longitudinal player scouting dossier.

## API quick reference

- `GET /api/health`
- `GET /api/dashboard`
- `GET /api/players`
- `GET /api/videos`
- `POST /api/videos`
- `GET /api/videos/{id}`
- `GET /api/videos/{id}/frames`
- `GET /api/videos/{id}/events`
- `POST /api/videos/{id}/events`
- `DELETE /api/events/{id}`
- `POST /api/videos/{id}/extract-sequence`
- `POST /api/videos/{id}/reanalyze`

## Render deployment

This build is Render-ready. See `RENDER_DEPLOYMENT.md` and `render.yaml`. The Render configuration uses Docker plus a persistent disk because the MVP stores SQLite, uploaded videos, and generated frames locally.
