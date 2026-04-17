from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from .db import MetadataDB
from .jobs import JobManager
from .palette import IceClassPalette, load_palette
from .route_solver import GridRoute, cell_to_lonlat, solve_astar
from .scene_index import SceneIndex
from .schemas import (
    LayerListItem,
    LayerListResponse,
    LayerManifestResponse,
    LayerSummaryResponse,
    LayerViewManifest,
    ReconstructionJobCreate,
    ReconstructionJobCreated,
    ReconstructionJobStatus,
    RoutePath,
    RoutePoint,
    RouteSolveRequest,
    RouteSolveResponse,
    SceneListResponse,
    SceneMetadata,
)
from .settings import Settings, get_settings


@dataclass
class AppState:
    settings: Settings
    db: MetadataDB
    palette: IceClassPalette
    scene_index: SceneIndex | None
    job_manager: JobManager | None


def _build_app_state(settings: Settings) -> AppState:
    db = MetadataDB(settings.sqlite_path)
    palette_path = Path(__file__).resolve().parents[2] / "configs" / "ice_palette.json"
    palette = load_palette(palette_path)

    if not settings.dataset_iceclass_dir.exists() or not settings.dataset_composite_dir.exists():
        return AppState(settings=settings, db=db, palette=palette, scene_index=None, job_manager=None)

    scene_index = SceneIndex(settings.dataset_iceclass_dir, settings.dataset_composite_dir)
    job_manager = JobManager(
        db=db,
        scene_index=scene_index,
        palette=palette,
        storage_dir=settings.storage_dir,
        preview_max_width=settings.preview_max_width,
        route_grid_size=settings.route_grid_size,
        model_checkpoint_path=settings.model_checkpoint_path,
        model_device=settings.model_device,
        model_input_size=settings.model_input_size,
        model_tile_overlap=settings.model_tile_overlap,
        workers=2,
    )
    return AppState(settings=settings, db=db, palette=palette, scene_index=scene_index, job_manager=job_manager)


def _route_to_schema(route: GridRoute, *, route_id: str, bounds: list[float], shape_hw: tuple[int, int], vessel_class: str) -> RoutePath:
    # Downsample points for frontend payload size.
    step = max(1, len(route.path_cells) // 400)
    sampled = route.path_cells[::step]
    if sampled[-1] != route.path_cells[-1]:
        sampled.append(route.path_cells[-1])

    points = [
        RoutePoint(lon=float(cell_to_lonlat(y, x, bounds, shape_hw)[0]), lat=float(cell_to_lonlat(y, x, bounds, shape_hw)[1]))
        for y, x in sampled
    ]

    nominal_speed_kmh = {
        "Arc4": 17.0,
        "Arc5": 18.0,
        "Arc6": 20.0,
        "Arc7": 23.0,
        "Arc9": 26.0,
    }.get(vessel_class, 23.0)
    eta = route.distance_km / max(1.0, nominal_speed_kmh)

    return RoutePath(
        route_id=route_id,
        score=float(route.total_cost),
        distance_km=float(route.distance_km),
        eta_hours=float(eta),
        risk_score=float(route.risk_score),
        confidence_score=float(route.confidence_score),
        points=points,
    )


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title=settings.project_name)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    state = _build_app_state(settings)
    app.state.vizard = state

    def require_ready() -> AppState:
        st: AppState = app.state.vizard
        if st.scene_index is None or st.job_manager is None:
            raise HTTPException(
                status_code=503,
                detail="Dataset directories are unavailable. Check VIZARD_ICECLASS_DIR and VIZARD_COMPOSITE_DIR.",
            )
        return st

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "service": "Vizard Arctic API",
            "status": "ok",
            "health": "/health",
            "api_prefix": settings.api_prefix,
        }

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/health")
    def health() -> dict[str, str | int]:
        st: AppState = app.state.vizard
        return {
            "status": "ok",
            "scenes": st.scene_index.total if st.scene_index else 0,
        }

    @app.get(f"{settings.api_prefix}/scenes", response_model=SceneListResponse)
    def list_scenes(
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> SceneListResponse:
        st = require_ready()
        recs = st.scene_index.list_records()
        total = len(recs)
        subset = recs[offset : offset + limit]

        scenes = [
            SceneMetadata(
                scene_id=r.scene_id,
                acquisition_start=r.acquisition_start,
                acquisition_end=r.acquisition_end,
                iceclass_path=str(r.iceclass_path),
                composite_path=str(r.composite_path),
                gap_ratio=None,
                bounds=st.scene_index.get_geo_info(r.scene_id).bounds,
            )
            for r in subset
        ]
        return SceneListResponse(total=total, scenes=scenes)

    @app.post(f"{settings.api_prefix}/reconstruction/jobs", response_model=ReconstructionJobCreated)
    def create_job(req: ReconstructionJobCreate) -> ReconstructionJobCreated:
        st = require_ready()
        try:
            st.scene_index.get(req.scene_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown scene_id={req.scene_id}")

        params = {
            "scene_id": req.scene_id,
            "history_steps": req.history_steps,
            "model_mode": req.model_mode,
            "aoi_bbox": req.aoi_bbox,
        }
        job_id = st.db.create_job(scene_id=req.scene_id, params=params)
        st.job_manager.submit_reconstruction(
            job_id,
            scene_id=req.scene_id,
            history_steps=req.history_steps,
            model_mode=req.model_mode,
            aoi_bbox=req.aoi_bbox,
        )
        return ReconstructionJobCreated(job_id=job_id, status="queued")

    @app.get(f"{settings.api_prefix}/reconstruction/jobs/{{job_id}}", response_model=ReconstructionJobStatus)
    def get_job(job_id: str) -> ReconstructionJobStatus:
        st = require_ready()
        row = st.db.get_job(job_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Unknown job_id={job_id}")
        return ReconstructionJobStatus(
            job_id=row["id"],
            status=row["status"],
            progress=row["progress"],
            scene_id=row["scene_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            layer_id=row["layer_id"],
            error=row["error"],
        )

    def _layer_dir(layer_id: str) -> Path:
        st: AppState = app.state.vizard
        rec = st.db.get_layer_by_id(layer_id)
        if rec is None:
            raise HTTPException(status_code=404, detail=f"Unknown layer_id={layer_id}")
        p = Path(rec["path"])
        if not p.exists():
            raise HTTPException(status_code=404, detail=f"Layer artifacts missing for layer_id={layer_id}")
        return p

    @app.get(f"{settings.api_prefix}/layers/{{layer_id}}/manifest", response_model=LayerManifestResponse)
    def get_layer_manifest(layer_id: str) -> LayerManifestResponse:
        st: AppState = app.state.vizard
        layer_dir = _layer_dir(layer_id)
        rec = st.db.get_layer_by_id(layer_id)
        manifest_path = layer_dir / "manifest.json"
        if not manifest_path.exists():
            raise HTTPException(status_code=404, detail="Manifest file not found")
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))

        views = [
            LayerViewManifest(name=v["name"], url=v["url"], opacity=v.get("opacity", 0.9))
            for v in raw["views"]
        ]

        return LayerManifestResponse(
            layer_id=raw["layer_id"],
            scene_id=raw["scene_id"],
            bounds=raw["bounds"],
            coordinates=raw["coordinates"],
            created_at=rec["created_at"],
            views=views,
        )

    @app.get(f"{settings.api_prefix}/layers/{{layer_id}}/summary", response_model=LayerSummaryResponse)
    def get_layer_summary(layer_id: str) -> LayerSummaryResponse:
        st: AppState = app.state.vizard
        rec = st.db.get_layer_by_id(layer_id)
        if rec is None:
            raise HTTPException(status_code=404, detail=f"Unknown layer_id={layer_id}")
        s = rec["summary"]
        return LayerSummaryResponse(**s)

    @app.get(f"{settings.api_prefix}/layers/recent", response_model=LayerListResponse)
    def list_recent_layers(
        limit: int = Query(default=20, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> LayerListResponse:
        st: AppState = app.state.vizard
        total, layers = st.db.list_recent_layers(limit=limit, offset=offset)
        out = [
            LayerListItem(
                layer_id=row["id"],
                scene_id=row["scene_id"],
                created_at=row["created_at"],
                summary=row["summary"],
            )
            for row in layers
        ]
        return LayerListResponse(total=total, layers=out)

    @app.get(f"{settings.api_prefix}/layers/{{layer_id}}/{{view_name}}.png")
    def get_layer_image(layer_id: str, view_name: str) -> FileResponse:
        if view_name not in {"observed", "reconstructed", "confidence", "difference"}:
            raise HTTPException(status_code=404, detail=f"Unknown view={view_name}")
        layer_dir = _layer_dir(layer_id)
        f = layer_dir / f"{view_name}.png"
        if not f.exists():
            raise HTTPException(status_code=404, detail="View image not found")
        return FileResponse(f, media_type="image/png")

    @app.post(f"{settings.api_prefix}/routes/solve", response_model=RouteSolveResponse)
    def solve_route(req: RouteSolveRequest) -> RouteSolveResponse:
        layer_dir = _layer_dir(req.layer_id)
        grid_path = layer_dir / "route_grid.npz"
        if not grid_path.exists():
            raise HTTPException(status_code=404, detail="route_grid.npz not found")

        with np.load(grid_path) as npz:
            classes = npz["classes"].astype(np.uint8)
            confidence = npz["confidence"].astype(np.float32)
            bounds = npz["bounds"].astype(np.float64).tolist()

        st: AppState = app.state.vizard
        cost_grid = st.palette.class_cost_grid(classes)

        try:
            primary_route = solve_astar(
                cost_grid=cost_grid,
                confidence_grid=confidence,
                bounds=bounds,
                start_lon=req.start_lon,
                start_lat=req.start_lat,
                end_lon=req.end_lon,
                end_lat=req.end_lat,
                vessel_class=req.vessel_class,
                confidence_penalty=req.confidence_penalty,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        alt_routes: list[GridRoute] = []
        corridor_paths = [primary_route.path_cells]
        for _ in range(2):
            try:
                alt = solve_astar(
                    cost_grid=cost_grid,
                    confidence_grid=confidence,
                    bounds=bounds,
                    start_lon=req.start_lon,
                    start_lat=req.start_lat,
                    end_lon=req.end_lon,
                    end_lat=req.end_lat,
                    vessel_class=req.vessel_class,
                    confidence_penalty=req.confidence_penalty,
                    corridor_paths=corridor_paths,
                )
                alt_routes.append(alt)
                corridor_paths.append(alt.path_cells)
            except RuntimeError:
                break

        primary = _route_to_schema(
            primary_route,
            route_id="primary",
            bounds=bounds,
            shape_hw=cost_grid.shape,
            vessel_class=req.vessel_class,
        )

        alternatives = [
            _route_to_schema(
                route,
                route_id=f"alt_{i+1}",
                bounds=bounds,
                shape_hw=cost_grid.shape,
                vessel_class=req.vessel_class,
            )
            for i, route in enumerate(alt_routes)
        ]

        return RouteSolveResponse(layer_id=req.layer_id, primary=primary, alternatives=alternatives)

    return app


app = create_app()
