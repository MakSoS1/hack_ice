import {
  LayerListResponse,
  LayerManifestResponse,
  LayerSummaryResponse,
  ReconstructionJobCreate,
  ReconstructionJobCreated,
  ReconstructionJobStatus,
  RouteSolveRequest,
  RouteSolveResponse,
  SceneListResponse,
} from "@/lib/api-types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";
const API_PREFIX = "/api/v1";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API ${response.status}: ${text}`);
  }

  return (await response.json()) as T;
}

export function apiImageUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${API_BASE}${path}`;
}

export async function listScenes(limit = 300, offset = 0): Promise<SceneListResponse> {
  return requestJson<SceneListResponse>(`${API_PREFIX}/scenes?limit=${limit}&offset=${offset}`);
}

export async function createReconstructionJob(payload: ReconstructionJobCreate): Promise<ReconstructionJobCreated> {
  return requestJson<ReconstructionJobCreated>(`${API_PREFIX}/reconstruction/jobs`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getReconstructionJob(jobId: string): Promise<ReconstructionJobStatus> {
  return requestJson<ReconstructionJobStatus>(`${API_PREFIX}/reconstruction/jobs/${jobId}`);
}

export async function getLayerManifest(layerId: string): Promise<LayerManifestResponse> {
  return requestJson<LayerManifestResponse>(`${API_PREFIX}/layers/${layerId}/manifest`);
}

export async function getLayerSummary(layerId: string): Promise<LayerSummaryResponse> {
  return requestJson<LayerSummaryResponse>(`${API_PREFIX}/layers/${layerId}/summary`);
}

export async function listRecentLayers(limit = 20, offset = 0): Promise<LayerListResponse> {
  return requestJson<LayerListResponse>(`${API_PREFIX}/layers/recent?limit=${limit}&offset=${offset}`);
}

export async function solveRoute(payload: RouteSolveRequest): Promise<RouteSolveResponse> {
  return requestJson<RouteSolveResponse>(`${API_PREFIX}/routes/solve`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
