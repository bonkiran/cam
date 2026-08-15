# CrickAnalysis Build Status — MVP 0.1

## Implemented and tested
- Functional FastAPI application server.
- Persistent SQLite schema for players, videos, frames, and cricket events.
- Real video-file upload.
- Background OpenCV processing.
- FPS, duration, resolution and source frame-count extraction.
- 5 Hz motion-intensity timeline.
- Motion-peak candidate selection with temporal de-duplication.
- Generated evidence/timeline JPEG frames.
- Browser video player with real one-frame / ten-frame stepping.
- Clickable generated-frame filmstrip.
- Manual truth tagging for Four, Six, Dot, 1, 2, 3, Wicket and Other.
- Event deletion.
- Exact multi-frame evidence sequence extraction around any chosen timestamp.
- Dashboard counts sourced from the real SQLite data.
- Player list sourced from uploads.
- Re-analysis endpoint.
- Responsive left-sidebar UI.

## End-to-end smoke test completed
A generated MP4 was uploaded through the HTTP API and successfully produced:
- 25 FPS metadata
- 5.0 second duration
- 640×360 resolution
- 125 source frames
- timeline/candidate images
- a SIX event persisted at 2.1 seconds
- an 8-frame evidence sequence
- updated dashboard boundary/six counts

The test data was removed from the distributable after verification.

## Not falsely claimed as complete
The current motion detector is **not** labeled as automatic cricket-shot detection. The following are next engineering slices:
- delivery segmentation
- automatic Four/Six recognition
- bowler-release / bounce / impact timing
- human pose/keypoint tracking
- footwork/head/knee/hip/elbow/trunk metrics
- bat path/speed
- ball line/length/speed
- reaction time
- shot-selection vs execution scoring
- longitudinal scouting dossier
