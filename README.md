# Vizard Arctic

End-to-end prototype for Arctic ice gap filling and route planning.

## Monorepo structure

- `backend/` FastAPI + job queue + scene index + layer publishing + A* routes
- `frontend/` React + MapLibre UI (integrated from `arctic-vista-main`)
- `ml/` temporal U-Net training/inference scripts
- `configs/` palette and model configs
- `storage/` runtime artifacts (`layers/`, `metadata.db`)
- `scripts/` bootstrap helpers for remote Windows machine

## Remote deployment target

Designed for:
- Windows host `10.78.211.199`
- GPU: RTX 2060 SUPER 8GB
- Data folders (read-only):
  - `C:\Users\maksi\Downloads\vizard_iceclass\Dataset_2025_IceClass`
  - `C:\Users\maksi\Downloads\vizard_composite\Dataset_2025_composite`

## Quick start (Windows remote)

```powershell
cd C:\Users\maksi\projects\vizard-arctic
powershell -ExecutionPolicy Bypass -File .\scripts\setup_remote.ps1
```

### Run backend

```powershell
cd C:\Users\maksi\projects\vizard-arctic\backend
..\.venv\Scripts\python.exe run.py
```

### Run frontend

```powershell
cd C:\Users\maksi\projects\vizard-arctic\frontend
npm.cmd run dev -- --host 0.0.0.0 --port 8080
```

Set API URL for frontend with:

```powershell
setx VITE_API_BASE_URL http://127.0.0.1:8000
```

## API contract

- `GET /api/v1/scenes`
- `POST /api/v1/reconstruction/jobs`
- `GET /api/v1/reconstruction/jobs/{job_id}`
- `GET /api/v1/layers/{layer_id}/manifest`
- `GET /api/v1/layers/{layer_id}/{view}.png`
- `GET /api/v1/layers/{layer_id}/summary`
- `POST /api/v1/routes/solve`

## ML scripts

### Recommended RTX 2060 SUPER training profile

The training defaults are tuned for 8GB VRAM:
- `crop_size=256`
- `batch_size=1`
- `grad_accum=4`
- `base_channels=16`
- `history_steps=1`
- `norm=group`
- synthetic gap masking enabled for masked-area validation

Dataset audit (scene naming, geometry, gap distribution, class histogram):

```powershell
cd C:\Users\maksi\projects\vizard-arctic
.\.venv\Scripts\python.exe -m ml.data_audit
```

Accuracy-oriented MVP training on representative subset:

```powershell
cd C:\Users\maksi\projects\vizard-arctic
.\.venv\Scripts\python.exe -m ml.train_mvp
```

Full training pass:

```powershell
.\.venv\Scripts\python.exe -m ml.train_full
```

Smoke inference for one scene:

```powershell
.\.venv\Scripts\python.exe -m ml.infer --scene-id <SCENE_ID> --tile-size 512 --tile-overlap 64
```

Benchmark with masked-area metrics and optional YOLO comparison:

```powershell
.\.venv\Scripts\python.exe -m ml.benchmark --checkpoint .\backend\checkpoints\mvp_unet.pt --synthetic-eval
```

If you have previous YOLO predictions (`<scene_id>.npy/.npz/.png`):

```powershell
.\.venv\Scripts\python.exe -m ml.benchmark --checkpoint .\backend\checkpoints\mvp_unet.pt --yolo-pred-dir <YOLO_PRED_DIR>
```

## Runtime model modes

`POST /api/v1/reconstruction/jobs` supports:
- `fast`: temporal fill baseline (no neural net)
- `balanced`: tiled Temporal U-Net reconstruction with moderate overlap
- `precise`: tiled Temporal U-Net reconstruction with larger overlap
