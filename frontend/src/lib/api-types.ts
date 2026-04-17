export type JobStatus = "queued" | "running" | "completed" | "failed";
export type ModelMode = "fast" | "balanced" | "precise";

export interface SceneMetadata {
  scene_id: string;
  acquisition_start: string;
  acquisition_end: string;
  iceclass_path: string;
  composite_path: string;
  gap_ratio: number | null;
  bounds: [number, number, number, number] | null;
}

export interface SceneListResponse {
  total: number;
  scenes: SceneMetadata[];
}

export interface ReconstructionJobCreate {
  scene_id: string;
  history_steps: number;
  model_mode: ModelMode;
  aoi_bbox?: [number, number, number, number] | null;
}

export interface ReconstructionJobCreated {
  job_id: string;
  status: JobStatus;
}

export interface ReconstructionJobStatus {
  job_id: string;
  status: JobStatus;
  progress: number;
  scene_id: string;
  created_at: string;
  updated_at: string;
  layer_id: string | null;
  error: string | null;
}

export type LayerViewName = "observed" | "reconstructed" | "confidence" | "difference";

export interface LayerViewManifest {
  name: LayerViewName;
  url: string;
  opacity: number;
}

export interface LayerManifestResponse {
  layer_id: string;
  scene_id: string;
  bounds: [number, number, number, number];
  coordinates: [number, number][];
  created_at: string;
  views: LayerViewManifest[];
}

export interface LayerSummaryResponse {
  layer_id: string;
  scene_id: string;
  coverage_before: number;
  coverage_after: number;
  restored_area_km2: number;
  mean_confidence: number;
  high_confidence_ratio: number;
  low_confidence_ratio: number;
  changed_pixels_ratio: number;
}

export interface RouteSolveRequest {
  layer_id: string;
  start_lon: number;
  start_lat: number;
  end_lon: number;
  end_lat: number;
  vessel_class: "Arc4" | "Arc5" | "Arc6" | "Arc7" | "Arc9";
  confidence_penalty: number;
}

export interface RoutePoint {
  lon: number;
  lat: number;
}

export interface RoutePath {
  route_id: string;
  score: number;
  distance_km: number;
  eta_hours: number;
  risk_score: number;
  confidence_score: number;
  points: RoutePoint[];
}

export interface RouteSolveResponse {
  layer_id: string;
  primary: RoutePath;
  alternatives: RoutePath[];
}
