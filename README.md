# Vizard Arctic

End-to-end prototype for Arctic ice gap filling and route planning.

## Monorepo structure

- `backend/` FastAPI + job queue + scene index + layer publishing + A* routes
- `frontend/` React + MapLibre UI (full `vizard-arctic-clean` interface)
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

## Frontend status

`frontend/` now contains the full `vizard-arctic-clean` interface and is the primary UI for this repository.

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

### Run frontend on macOS, backend+model on remote PC

On remote Windows PC:

```powershell
cd C:\Users\maksi\projects\vizard-arctic\backend
..\.venv\Scripts\python.exe run.py
```

On local macOS:

```bash
cd /Users/maksos/Documents/work/hack_ice/_repo_hack_ice/frontend
cp .env.remote.example .env.local
npm install
npm run dev -- --host 0.0.0.0 --port 8080
```

Then open `http://localhost:8080`.

## API contract

- `GET /` (service info)
- `GET /api/v1/scenes`
- `POST /api/v1/reconstruction/jobs`
- `GET /api/v1/reconstruction/jobs/{job_id}`
- `GET /api/v1/layers/recent`
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

Monte Carlo drift forecast (uses existing `storage/layers/*/route_grid.npz`):

```powershell
.\.venv\Scripts\python.exe -m ml.drift_forecast --n-sim 2000 --horizon 24 --dt 1 --mode inertial
```

## Runtime model modes

`POST /api/v1/reconstruction/jobs` supports:
- `fast`: temporal fill baseline (no neural net)
- `balanced`: tiled Temporal U-Net reconstruction with moderate overlap
- `precise`: tiled Temporal U-Net reconstruction with larger overlap

## Why CPU/GPU can stay under 20%

Main bottleneck is input pipeline:
- each training sample reads large GeoTIFF rasters from disk (`IceClass` + `Composite`);
- `Composite` gap masks are expensive to decode repeatedly;
- with small batch/crop the GPU compute step is short, so it waits for data.

Mitigations included in this repo:
- LRU cache for class/gap maps in `SceneTemporalDataset` (`--cache-items`, default `24`);
- tiled inference and low-VRAM defaults (`batch_size=1`, `grad_accum`, `group` norm);
- CLI controls for `--workers` and `--cache-items`.

Example:

```powershell
.\.venv\Scripts\python.exe -m ml.train_mvp --workers 2 --cache-items 48
```

## Demo scenario (ice motion + model impact)

Run:

```powershell
cd C:\Users\maksi\projects\vizard-arctic
.\.venv\Scripts\python.exe .\scripts\demo_scenario.py --model-mode balanced
```

Outputs:
- `storage/reports/demo_scenario.json`
- `storage/reports/demo_scenario.md`
- `storage/reports/demo_ice_motion_*.gif`
- demo layers are auto-registered in `storage/metadata.db` for UI reuse

UI demo shortcut:
- in AI panel click `Загрузить готовый демо-слой` to open latest precomputed layer without waiting for a full run.
