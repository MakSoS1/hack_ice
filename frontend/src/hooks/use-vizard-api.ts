import { useMutation, useQuery } from "@tanstack/react-query";
import {
  createReconstructionJob,
  getLayerManifest,
  getLayerSummary,
  getReconstructionJob,
  listRecentLayers,
  listScenes,
  solveRoute,
} from "@/lib/api-client";
import { ReconstructionJobCreate, RouteSolveRequest } from "@/lib/api-types";

export function useScenesQuery() {
  return useQuery({
    queryKey: ["scenes"],
    queryFn: () => listScenes(400, 0),
    staleTime: 60_000,
  });
}

export function useCreateReconstructionJobMutation() {
  return useMutation({
    mutationFn: (payload: ReconstructionJobCreate) => createReconstructionJob(payload),
  });
}

export function useReconstructionJobQuery(jobId: string | null, enabled = true) {
  return useQuery({
    queryKey: ["reconstruction-job", jobId],
    queryFn: () => {
      if (!jobId) throw new Error("jobId is null");
      return getReconstructionJob(jobId);
    },
    enabled: enabled && Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status) return 2500;
      if (status === "completed" || status === "failed") return false;
      return 2000;
    },
  });
}

export function useLayerManifestQuery(layerId: string | null) {
  return useQuery({
    queryKey: ["layer-manifest", layerId],
    queryFn: () => {
      if (!layerId) throw new Error("layerId is null");
      return getLayerManifest(layerId);
    },
    enabled: Boolean(layerId),
    staleTime: 10_000,
  });
}

export function useLayerSummaryQuery(layerId: string | null) {
  return useQuery({
    queryKey: ["layer-summary", layerId],
    queryFn: () => {
      if (!layerId) throw new Error("layerId is null");
      return getLayerSummary(layerId);
    },
    enabled: Boolean(layerId),
    staleTime: 10_000,
  });
}

export function useRecentLayersQuery(limit = 20, enabled = true) {
  return useQuery({
    queryKey: ["recent-layers", limit],
    queryFn: () => listRecentLayers(limit, 0),
    enabled,
    staleTime: 8_000,
  });
}

export function useSolveRouteMutation() {
  return useMutation({
    mutationFn: (payload: RouteSolveRequest) => solveRoute(payload),
  });
}
