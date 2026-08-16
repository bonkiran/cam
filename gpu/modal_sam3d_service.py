from __future__ import annotations

"""CrickAnalysis SAM-3D serverless GPU service on Modal.

This replaces the temporary Colab + ngrok pose engine. The public FastAPI
endpoint runs on a small CPU container; SAM-3D inference automatically wakes a
T4 GPU worker only when a shot is submitted.

The service exposes both:
  * POST /analyze-shot              (preferred stateless contract)
  * POST /upload + GET /people + GET /person/{pid}/joints
                                      (legacy CrickAnalysis contract)

The legacy endpoints are retained so the current Render backend can switch from
Colab to Modal simply by changing POSE_ENGINE_URL. Once this path is validated,
CrickAnalysis can move fully to /analyze-shot and remove the compatibility
state.
"""

import os
from pathlib import Path
from typing import Any

import modal

APP_NAME = "crickanalysis-sam3d"
MODEL_REPO = "facebook/sam-3d-body-dinov3"
MODEL_VOLUME_NAME = "crickanalysis-sam3d-models"
LEGACY_STATE_NAME = "crickanalysis-sam3d-state"
HF_SECRET_NAME = "crickanalysis-huggingface"

MODEL_ROOT = Path("/models")
MODEL_DIR = MODEL_ROOT / "sam-3d-body-dinov3"
SAM3D_SOURCE = Path("/opt/sam-3d-body")
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
DEFAULT_FRAME_INTERVAL = 5

app = modal.App(APP_NAME)
model_volume = modal.Volume.from_name(MODEL_VOLUME_NAME, create_if_missing=True)
legacy_state = modal.Dict.from_name(LEGACY_STATE_NAME, create_if_missing=True)
hf_secret = modal.Secret.from_name(HF_SECRET_NAME, required_keys=["HF_TOKEN"])

# Keep the runtime close to the working Colab proof-of-concept: Python 3.11,
# CUDA-capable PyTorch, Meta's official SAM-3D source, and the inference
# dependencies from Meta's INSTALL.md. Detector/segmentor/FOV packages are
# intentionally omitted in Stage 1 because CrickAnalysis sends a short clip in
# which the batter is expected to be prominent.
base_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "git",
        "ffmpeg",
        "libgl1",
        "libglib2.0-0",
        "build-essential",
    )
    .pip_install(
        "torch==2.7.1",
        "torchvision==0.22.1",
        "numpy==1.26.4",
        "opencv-python-headless",
        "pytorch-lightning",
        "pyrender",
        "yacs",
        "scikit-image",
        "einops",
        "timm",
        "dill",
        "pandas",
        "rich",
        "hydra-core",
        "hydra-submitit-launcher",
        "hydra-colorlog",
        "pyrootutils",
        "webdataset",
        "chump",
        "networkx==3.2.1",
        "roma",
        "joblib",
        "wandb",
        "appdirs",
        "ffmpeg-python",
        "cython",
        "jsonlines",
        "xtcocotools",
        "loguru",
        "optree",
        "fvcore",
        "pycocotools",
        "tensorboard",
        "huggingface_hub",
    )
    .run_commands(
        "git clone --depth 1 https://github.com/facebookresearch/sam-3d-body.git /opt/sam-3d-body"
    )
    .env(
        {
            "PYTHONPATH": "/opt/sam-3d-body",
            "HF_HUB_DISABLE_XET": "1",
            "HF_HUB_DOWNLOAD_TIMEOUT": "600",
            "HF_HUB_ETAG_TIMEOUT": "60",
        }
    )
)

web_image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "fastapi[standard]",
    "python-multipart",
)


def _model_files() -> list[str]:
    return [
        "model_config.yaml",
        "model.ckpt",
        "assets/mhr_model.pt",
        "LICENSE",
        "README.md",
    ]


def _looks_complete(filename: str) -> bool:
    path = MODEL_DIR / filename
    if not path.exists():
        return False
    if filename == "model.ckpt":
        return path.stat().st_size > 100_000_000
    if filename.endswith("mhr_model.pt"):
        return path.stat().st_size > 10_000_000
    return path.stat().st_size > 0


@app.function(
    image=base_image,
    secrets=[hf_secret],
    volumes={MODEL_ROOT: model_volume},
    timeout=1800,
)
def download_weights() -> dict[str, Any]:
    """One-time bootstrap: download the gated SAM-3D weights to a Modal Volume."""
    import time

    from huggingface_hub import hf_hub_download

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    token = os.environ["HF_TOKEN"]

    downloaded: list[str] = []
    cached: list[str] = []
    for filename in _model_files():
        if _looks_complete(filename):
            cached.append(filename)
            continue

        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                hf_hub_download(
                    repo_id=MODEL_REPO,
                    filename=filename,
                    local_dir=str(MODEL_DIR),
                    token=token,
                )
                if not _looks_complete(filename):
                    raise RuntimeError(f"{filename} failed size validation after download")
                downloaded.append(filename)
                last_error = None
                break
            except Exception as exc:  # pragma: no cover - remote bootstrap diagnostics
                last_error = exc
                time.sleep(5 * attempt)
        if last_error is not None:
            raise last_error

    model_volume.commit()
    return {
        "status": "ready",
        "model_repo": MODEL_REPO,
        "model_dir": str(MODEL_DIR),
        "downloaded": downloaded,
        "cached": cached,
        "model_ckpt_bytes": (MODEL_DIR / "model.ckpt").stat().st_size,
        "mhr_model_bytes": (MODEL_DIR / "assets/mhr_model.pt").stat().st_size,
    }


@app.cls(
    image=base_image,
    gpu="T4",
    volumes={MODEL_ROOT: model_volume},
    memory=16384,
    max_containers=1,
    scaledown_window=300,
    timeout=900,
    startup_timeout=600,
)
class PoseWorker:
    """GPU worker that loads SAM-3D once per warm container."""

    @modal.enter()
    def load_model(self) -> None:
        import sys

        import torch

        if str(SAM3D_SOURCE) not in sys.path:
            sys.path.insert(0, str(SAM3D_SOURCE))

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available in the Modal GPU worker")

        checkpoint_path = MODEL_DIR / "model.ckpt"
        mhr_path = MODEL_DIR / "assets" / "mhr_model.pt"
        if not checkpoint_path.exists() or not mhr_path.exists():
            raise RuntimeError(
                "SAM-3D weights are missing. Run `modal run gpu/modal_sam3d_service.py` once before deploy/use."
            )

        from sam_3d_body import SAM3DBodyEstimator
        from sam_3d_body.build_models import load_sam_3d_body

        model, cfg = load_sam_3d_body(
            checkpoint_path=str(checkpoint_path),
            device="cuda",
            mhr_path=str(mhr_path),
        )
        self.estimator = SAM3DBodyEstimator(
            sam_3d_body_model=model,
            model_cfg=cfg,
            human_detector=None,
            human_segmentor=None,
            fov_estimator=None,
        )
        self.gpu_name = torch.cuda.get_device_name(0)

    @staticmethod
    def _joints_to_list(value: Any) -> list[list[float]] | None:
        import numpy as np
        import torch

        if value is None:
            return None
        if torch.is_tensor(value):
            value = value.detach().cpu().numpy()
        array = np.asarray(value)
        while array.ndim > 2 and array.shape[0] == 1:
            array = array[0]
        if array.ndim != 2 or array.shape[1] < 3:
            return None
        return array[:, :3].astype(float).tolist()

    @modal.method()
    def analyze(self, video_bytes: bytes, filename: str = "shot_clip.mp4") -> dict[str, Any]:
        import tempfile

        import cv2
        import torch

        if not video_bytes:
            raise ValueError("Uploaded video is empty")
        if len(video_bytes) > MAX_UPLOAD_BYTES:
            raise ValueError(f"Uploaded clip exceeds {MAX_UPLOAD_BYTES // 1024 // 1024} MB")

        suffix = Path(filename or "shot_clip.mp4").suffix or ".mp4"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as temp:
            temp.write(video_bytes)
            temp.flush()

            cap = cv2.VideoCapture(temp.name)
            if not cap.isOpened():
                raise RuntimeError("OpenCV could not open the submitted shot clip")

            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
            interval = max(1, int(os.environ.get("POSE_FRAME_INTERVAL", str(DEFAULT_FRAME_INTERVAL))))
            timeline: list[dict[str, Any]] = []
            source_frame_index = 0
            try:
                with torch.inference_mode():
                    while True:
                        ok, frame = cap.read()
                        if not ok:
                            break
                        if source_frame_index % interval != 0:
                            source_frame_index += 1
                            continue

                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        outputs = self.estimator.process_one_image(rgb, inference_type="body")
                        if isinstance(outputs, dict):
                            primary = outputs
                        elif isinstance(outputs, (list, tuple)) and outputs:
                            primary = outputs[0]
                        else:
                            primary = None

                        if isinstance(primary, dict):
                            joints = primary.get("pred_joint_coords")
                            if joints is None:
                                joints = primary.get("pred_keypoints_3d")
                            normalized = self._joints_to_list(joints)
                            if normalized:
                                timeline.append(
                                    {
                                        "pose_frame_index": len(timeline),
                                        "source_frame_index": source_frame_index,
                                        "timestamp": (source_frame_index / fps) if fps > 0 else None,
                                        "pred_joint_coords": normalized,
                                    }
                                )
                        source_frame_index += 1
            finally:
                cap.release()

        if not timeline:
            raise RuntimeError(
                "SAM-3D completed, but no usable body joints were produced for the submitted clip"
            )

        person_id = "person_000"
        return {
            "status": "complete",
            "provider": "CrickAnalysis SAM-3D on Modal",
            "people": [person_id],
            "timelines": {person_id: timeline},
            "pose_frames": len(timeline),
            "source_fps": fps,
            "frame_interval": interval,
            "gpu": self.gpu_name,
        }


def _latest_result() -> dict[str, Any]:
    try:
        value = legacy_state["latest"]
    except KeyError:
        return {}
    return value if isinstance(value, dict) else {}


@app.function(
    image=web_image,
    timeout=900,
    max_containers=1,
    scaledown_window=120,
)
@modal.concurrent(max_inputs=1)
@modal.asgi_app()
def fastapi_app():
    """Public HTTP gateway. It does not consume a GPU while idle."""
    from fastapi import FastAPI, File, HTTPException, UploadFile

    web = FastAPI(title="CrickAnalysis SAM-3D Pose Engine", version="1.0")

    async def run_analysis(video: UploadFile) -> dict[str, Any]:
        payload = await video.read()
        if not payload:
            raise HTTPException(400, "Uploaded video is empty")
        if len(payload) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"Clip exceeds {MAX_UPLOAD_BYTES // 1024 // 1024} MB")
        try:
            result = PoseWorker().analyze.remote(payload, video.filename or "shot_clip.mp4")
        except Exception as exc:
            raise HTTPException(500, f"SAM-3D inference failed: {exc}") from exc
        legacy_state["latest"] = result
        return result

    @web.get("/")
    def health() -> dict[str, Any]:
        latest = _latest_result()
        return {
            "status": "CrickAnalysis SAM-3D Modal service running",
            "platform": "Modal",
            "gpu": "T4 (starts on demand)",
            "model_repo": MODEL_REPO,
            "preferred_endpoint": "/analyze-shot",
            "legacy_contract": True,
            "latest_pose_frames": latest.get("pose_frames", 0),
        }

    @web.post("/analyze-shot")
    async def analyze_shot(video: UploadFile = File(...)) -> dict[str, Any]:
        return await run_analysis(video)

    # Compatibility contract for the current Render backend.
    @web.post("/upload")
    async def legacy_upload(video: UploadFile = File(...)) -> dict[str, Any]:
        return await run_analysis(video)

    @web.get("/people")
    def people() -> list[str]:
        latest = _latest_result()
        return [str(item) for item in latest.get("people", [])]

    @web.get("/person/{person_id}/joints")
    def person_joints(person_id: str) -> list[dict[str, Any]]:
        latest = _latest_result()
        timelines = latest.get("timelines", {})
        timeline = timelines.get(person_id) if isinstance(timelines, dict) else None
        if not isinstance(timeline, list) or not timeline:
            raise HTTPException(404, f"No joints timeline available for {person_id}")
        return timeline

    return web


@app.local_entrypoint()
def main() -> None:
    """Run once during setup to populate/validate the persistent model Volume."""
    result = download_weights.remote()
    print("SAM-3D model cache:", result)
    print("Next: modal deploy gpu/modal_sam3d_service.py")
