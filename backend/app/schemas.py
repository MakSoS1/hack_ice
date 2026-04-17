from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


JobStatus = Literal["queued", "running", "completed", "failed"]
ModelMode = Literal["fast", "balanced", "precise"]


class SceneMetadata(BaseModel):
    scene_id: str
    acquisition_start: datetime
    acquisition_end: datetime
    iceclass_path: str
    composite_path: str
    gap_ratio: float | None = None
    bounds: list[float] | None = None  # [lon_min, lat_min, lon_max, lat_max]


class SceneListResponse(BaseModel):
    total: int
    scenes: list[SceneMetadata]


class ReconstructionJobCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    scene_id: str
    history_steps: int = Field(default=2, ge=1, le=5)
    model_mode: ModelMode = "balanced"
    aoi_bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)


class ReconstructionJobCreated(BaseModel):
    job_id: str
    status: JobStatus


class ReconstructionJobStatus(BaseModel):
    job_id: str
    status: JobStatus
    progress: float = Field(ge=0.0, le=1.0)
    scene_id: str
    created_at: datetime
    updated_at: datetime
    layer_id: str | None = None
    error: str | None = None


class LayerViewManifest(BaseModel):
    name: Literal["observed", "reconstructed", "confidence", "difference"]
    url: str
    opacity: float = Field(ge=0.0, le=1.0)


class LayerManifestResponse(BaseModel):
    layer_id: str
    scene_id: str
    bounds: list[float]  # [lon_min, lat_min, lon_max, lat_max]
    coordinates: list[list[float]]  # maplibre image coordinates
    created_at: datetime
    views: list[LayerViewManifest]


class LayerListItem(BaseModel):
    layer_id: str
    scene_id: str
    created_at: datetime
    summary: dict


class LayerListResponse(BaseModel):
    total: int
    layers: list[LayerListItem]


class LayerSummaryResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    layer_id: str
    scene_id: str
    model_mode_requested: str | None = None
    model_mode_effective: str | None = None
    coverage_before: float
    coverage_after: float
    restored_area_km2: float
    mean_confidence: float
    high_confidence_ratio: float
    low_confidence_ratio: float
    changed_pixels_ratio: float


class RoutePoint(BaseModel):
    lon: float
    lat: float


class RoutePath(BaseModel):
    route_id: str
    score: float
    distance_km: float
    eta_hours: float
    risk_score: float
    confidence_score: float
    points: list[RoutePoint]


class RouteSolveRequest(BaseModel):
    layer_id: str
    start_lon: float
    start_lat: float
    end_lon: float
    end_lat: float
    vessel_class: Literal["Arc4", "Arc5", "Arc6", "Arc7", "Arc9"] = "Arc7"
    confidence_penalty: float = Field(default=2.0, ge=0.0, le=20.0)


class RouteSolveResponse(BaseModel):
    layer_id: str
    primary: RoutePath
    alternatives: list[RoutePath]
