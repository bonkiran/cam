# CrickAnalysis GPU Pose Engine — Modal

This is the permanent replacement for the temporary Google Colab + ngrok SAM-3D service.

## Architecture

```text
CrickAnalysis on Render
        |
        | short 3–8 second shot clip
        v
Modal public FastAPI gateway (CPU, inexpensive while idle)
        |
        | automatically wakes on demand
        v
Modal T4 GPU worker
        |
        v
Meta SAM-3D Body
        |
        v
3D joints timeline returned to CrickAnalysis
```

There is no Colab runtime to reconnect and no ngrok URL to refresh. Modal starts the GPU when CrickAnalysis submits a shot and scales it down after the configured idle window.

## One-time setup

### 1. Install and authenticate Modal

From the CrickAnalysis repository on your computer:

```powershell
pip install -U modal
modal setup
```

`modal setup` opens the browser to authenticate the local CLI to your Modal workspace.

### 2. Create the Hugging Face secret

In the Modal dashboard create a Secret named exactly:

```text
crickanalysis-huggingface
```

Add this key using the existing Hugging Face read token that has access to the gated Meta model:

```text
HF_TOKEN
```

Do not commit the token to GitHub or paste it into CrickAnalysis source code.

### 3. Populate the persistent model Volume

Run once:

```powershell
modal run gpu/modal_sam3d_service.py
```

This downloads/validates `facebook/sam-3d-body-dinov3` into the persistent Modal Volume `crickanalysis-sam3d-models`. Re-running the command should reuse files already present.

### 4. Deploy the service

```powershell
modal deploy gpu/modal_sam3d_service.py
```

Modal prints a permanent HTTPS URL for the deployed FastAPI web function.

### 5. Connect Render

Set the Render environment variable:

```text
POSE_ENGINE_URL=https://<your-modal-endpoint>
```

Use the base URL only — do not append `/upload` or `/analyze-shot`.

The current CrickAnalysis backend can keep using its existing legacy contract while we validate Modal:

- `POST /upload`
- `GET /people`
- `GET /person/{person_id}/joints`

The Modal service also provides the preferred future stateless endpoint:

- `POST /analyze-shot`

Once Modal is validated end-to-end, the Render backend can be simplified to use only `/analyze-shot`.

## Runtime behavior

- GPU: T4
- `min_containers`: zero/default — no permanently running GPU required
- `max_containers`: 1 for this MVP
- GPU idle scale-down window: 300 seconds
- Shot sampling: every 5th clip frame by default
- Model weights: persistent Modal Volume
- Legacy latest-result compatibility: persistent Modal Dict

## Important Stage-1 limitation

The service intentionally does not use a human detector, segmentor, or FOV estimator yet. It treats the prominent person in the short clip as the subject. This matches the Colab Stage-1 proof of concept. Batter isolation/tracking is the next model-quality step after the infrastructure migration is stable.
