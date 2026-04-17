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
npm run dev -- --host 0.0.0.0 --port 8080
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

Dataset audit (scene naming, geometry, gap distribution, class histogram):

```powershell
cd C:\Users\maksi\projects\vizard-arctic
.\.venv\Scripts\python.exe -m ml.data_audit
```

Accuracy-oriented MVP training on representative subset:

```powershell
cd C:\Users\maksi\projects\vizard-arctic
.\.venv\Scripts\python.exe -m ml.train_mvp --subset-size 220 --epochs 6
```

Full training pass:

```powershell
.\.venv\Scripts\python.exe -m ml.train_full --subset-size 409 --epochs 14
```

Smoke inference for one scene:

```powershell
.\.venv\Scripts\python.exe -m ml.infer --scene-id <SCENE_ID>
```

Benchmark with masked-area metrics and optional YOLO comparison:

```powershell
.\.venv\Scripts\python.exe -m ml.benchmark --checkpoint .\backend\checkpoints\mvp_unet.pt
```

If you have previous YOLO predictions (`<scene_id>.npy/.npz/.png`):

```powershell
.\.venv\Scripts\python.exe -m ml.benchmark --checkpoint .\backend\checkpoints\mvp_unet.pt --yolo-pred-dir <YOLO_PRED_DIR>
```
