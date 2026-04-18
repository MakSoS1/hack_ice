import { create } from "zustand";
import { DEFAULT_ENABLED_LAYERS, VESSELS } from "@/lib/vizard-data";
import { LayerSummaryResponse, RouteSolveResponse } from "@/lib/api-types";
import { AiViewMode, InspectorMode, Vessel } from "@/lib/vizard-types";

interface VizardState {
  enabledLayers: Set<string>;
  toggleLayer: (id: string) => void;
  enableLayers: (ids: string[]) => void;
  disableLayers: (ids: string[]) => void;

  selectedLayerId: string | null;
  selectLayer: (id: string | null) => void;

  inspectorMode: InspectorMode;
  setInspectorMode: (m: InspectorMode) => void;

  selectedVessel: Vessel | null;
  selectVessel: (v: Vessel | null) => void;

  aiView: AiViewMode;
  setAiView: (v: AiViewMode) => void;
  aiRunning: boolean;
  aiCompleted: boolean;
  aiJobId: string | null;
  aiProgress: number;
  activeSceneId: string | null;
  activeLayerId: string | null;
  activeLayerSummary: LayerSummaryResponse | null;
  setAiJob: (jobId: string, sceneId: string) => void;
  setAiStatus: (status: "queued" | "running" | "completed" | "failed", progress: number, layerId?: string | null) => void;
  setActiveLayerSummary: (summary: LayerSummaryResponse | null) => void;
  resetAi: () => void;

  routeBuilt: boolean;
  routeResult: RouteSolveResponse | null;
  setRouteResult: (r: RouteSolveResponse | null) => void;
  buildRoute: () => void;
  clearRoute: () => void;

  timelineHour: number;
  setTimelineHour: (h: number) => void;

  trackRange: "12" | "24" | "48";
  setTrackRange: (r: "12" | "24" | "48") => void;

  showTrack: boolean;
  setShowTrack: (b: boolean) => void;
}

export const useVizard = create<VizardState>((set, get) => ({
  enabledLayers: new Set(DEFAULT_ENABLED_LAYERS),
  toggleLayer: (id) =>
    set((s) => {
      const next = new Set(s.enabledLayers);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { enabledLayers: next };
    }),
  enableLayers: (ids) =>
    set((s) => {
      const next = new Set(s.enabledLayers);
      for (const id of ids) next.add(id);
      return { enabledLayers: next };
    }),
  disableLayers: (ids) =>
    set((s) => {
      const next = new Set(s.enabledLayers);
      for (const id of ids) next.delete(id);
      return { enabledLayers: next };
    }),

  selectedLayerId: "ice-concentration",
  selectLayer: (id) => set({ selectedLayerId: id, inspectorMode: id ? "layer" : "empty" }),

  inspectorMode: "layer",
  setInspectorMode: (m) => set({ inspectorMode: m }),

  selectedVessel: null,
  selectVessel: (v) => set({ selectedVessel: v, inspectorMode: v ? "vessel" : get().inspectorMode }),

  aiView: "observation",
  setAiView: (v) => set({ aiView: v }),
  aiRunning: false,
  aiCompleted: false,
  aiJobId: null,
  aiProgress: 0,
  activeSceneId: null,
  activeLayerId: null,
  activeLayerSummary: null,
  setAiJob: (jobId, sceneId) =>
    set({
      aiJobId: jobId,
      activeSceneId: sceneId,
      aiRunning: true,
      aiCompleted: false,
      aiProgress: 0,
      activeLayerId: null,
      activeLayerSummary: null,
      aiView: "observation",
    }),
  setAiStatus: (status, progress, layerId) =>
    set((s) => {
      const next: Partial<VizardState> = {
        aiProgress: progress,
        aiRunning: status === "queued" || status === "running",
        aiCompleted: status === "completed" && Boolean(layerId),
      };
      if (status === "completed" && layerId) {
        next.activeLayerId = layerId;
        const layers = new Set(s.enabledLayers);
        layers.add("ai-observed");
        next.enabledLayers = layers;
      }
      return next as VizardState;
    }),
  setActiveLayerSummary: (summary) => set({ activeLayerSummary: summary }),
  resetAi: () =>
    set({
      aiCompleted: false,
      aiRunning: false,
      aiProgress: 0,
      aiJobId: null,
      activeLayerId: null,
      activeLayerSummary: null,
      aiView: "observation",
      routeBuilt: false,
      routeResult: null,
    }),

  routeBuilt: false,
  routeResult: null,
  setRouteResult: (r) => set({ routeResult: r, routeBuilt: Boolean(r) }),
  buildRoute: () => set({ routeBuilt: true }),
  clearRoute: () => set({ routeBuilt: false, routeResult: null }),

  timelineHour: 21,
  setTimelineHour: (h) => set({ timelineHour: h }),

  trackRange: "24",
  setTrackRange: (r) => set({ trackRange: r }),

  showTrack: false,
  setShowTrack: (b) => set({ showTrack: b }),
}));

export { VESSELS };
