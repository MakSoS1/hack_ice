export type LayerStatus = "current" | "forecast" | "ai" | "nodata" | "error";

export interface LayerDef {
  id: string;
  label: string;
  status: LayerStatus;
  group: string;
  swatch?: string; // CSS color or class hint
  description?: string;
  source?: string;
  updated?: string;
  type?: string;
  coverage?: string;
  confidence?: string;
}

export interface Vessel {
  id: string;
  name: string;
  callsign: string;
  imo: string;
  mmsi: string;
  course: number;
  speed: number;
  lat: number;
  lon: number;
  lastFix: string;
  iceClass: string;
  // map projected coords (0..1 within map viewbox)
  x: number;
  y: number;
}

export type InspectorMode = "layer" | "ai" | "route" | "vessel" | "empty";

export type AiViewMode = "observation" | "reconstruction" | "confidence" | "difference";
