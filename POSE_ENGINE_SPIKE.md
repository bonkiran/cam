# CrickAnalysis Biomechanics Spike v1

This spike integrates CrickAnalysis with a **PoseForge-compatible SAM-3D service over HTTP**. It does not copy PoseForge frontend or biomechanics source code into CrickAnalysis.

## Web flow

1. Upload/prepare a cricket video normally.
2. Open Video Review and seek to the shot of interest.
3. In **Biomechanics Scan (Experimental)** choose a 4, 6, or 8 second window, batting handedness, camera view, and optionally player height.
4. CrickAnalysis extracts only that short window, downsizes the long side to at most 960 px, and caps the pose-engine clip at 30 FPS.
5. The short clip is sent to a PoseForge-compatible endpoint using multipart field `video` at `POST /upload`.
6. CrickAnalysis reads `/people` and `/person/{pid}/joints`, chooses the longest usable person track for the first spike, and computes neutral geometry.
7. The video playhead and projected pose skeleton remain synchronized in the web review screen.

## v1 measurements

- Front-knee angle
- Trunk lean from vertical
- Stance width
- Head horizontal displacement from the start of the scan

If player height is supplied, stance width/head movement are also shown in centimeters. Otherwise they are normalized to the estimated body-height proxy.

**No Elite/Good/Poor grading is applied in v1.** We should validate geometry, player tracking, camera robustness, and phase timing before creating normative technique grades.

## Required pose-engine contract

The configured service must expose the PoseForge-style endpoints:

- `POST /upload` — multipart field `video`
- `GET /people`
- `GET /person/{pid}/joints`

The joints response may use `pred_joint_coords`, `mhr_joints`, or `joints` per frame.

## Configuration

Set this environment variable on the CrickAnalysis web service:

```text
POSE_ENGINE_URL=https://your-pose-engine.example
```

Optional settings:

```text
POSE_ENGINE_UPLOAD_TIMEOUT=900
POSE_ENGINE_POLL_SECONDS=3
POSE_ENGINE_MAX_WAIT_SECONDS=180
```

If `POSE_ENGINE_URL` is not configured, the normal CrickAnalysis web app continues working and the Biomechanics panel clearly shows **POSE ENGINE NOT CONNECTED**.

## GPU service for the first experiment

PoseForge documents a Colab/GPU-first SAM-3D backend and ngrok exposure. For the first experiment, run that service separately and use its HTTPS ngrok base URL as `POSE_ENGINE_URL`. Keep Hugging Face/ngrok credentials in Colab secrets/environment variables; do not commit them.

## Production direction

The temporary PoseForge-compatible service is an integration boundary, not the desired production architecture. If the spike validates well, build a CrickAnalysis-owned GPU worker around the underlying licensed pose model/service, durable object storage, a job queue, and explicit person-selection/confidence handling.

## Licensing checkpoint

The PoseForge repository is public but currently does not expose a repository license through GitHub. Until clarified, CrickAnalysis should avoid copying PoseForge source code. This spike communicates with a separately running service through its documented API contract. Review the license of the underlying SAM-3D materials before production/commercial distribution.
