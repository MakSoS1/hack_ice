import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { LngLatBoundsLike, Map as MapLibreMap } from "maplibre-gl";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useVizard, VESSELS } from "@/store/vizard-store";
import { PORTS, ICE_CLASS_LEGEND } from "@/lib/vizard-data";
import { Plus, Minus, RotateCcw, Compass } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { apiImageUrl } from "@/lib/api-client";
import { useLayerManifestQuery } from "@/hooks/use-vizard-api";
import { useBreakpoint } from "@/hooks/use-mobile";

const BASE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [
    {
      id: "osm",
      type: "raster",
      source: "osm",
      paint: {
        "raster-opacity": 0.9,
        "raster-saturation": -0.15,
      },
    },
  ],
};

const WEBGL_FALLBACK_MESSAGE =
  "Карта работает в 2D-режиме (без WebGL). Это нормально для браузеров/окружений, где GPU-контекст недоступен.";
const BLANK_FRAME_FALLBACK_MESSAGE =
  "Обнаружен пустой кадр карты. Автоматически переключили отображение на стабильный 2D-режим.";
const RENDERER_STORAGE_KEY = "vizard_map_renderer_mode";
const CAMERA_MODE_STORAGE_KEY = "vizard_map_camera_mode";

type CameraMode = "2d" | "3d";

function readRendererModeFromStorage(): RendererMode {
  if (typeof window === "undefined") return "maplibre";
  try {
    const raw = window.localStorage.getItem(RENDERER_STORAGE_KEY);
    return raw === "leaflet" ? "leaflet" : "maplibre";
  } catch {
    return "maplibre";
  }
}

function persistRendererMode(mode: RendererMode): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(RENDERER_STORAGE_KEY, mode);
  } catch {
    // noop
  }
}

function readCameraModeFromStorage(): CameraMode {
  if (typeof window === "undefined") return "3d";
  try {
    const raw = window.localStorage.getItem(CAMERA_MODE_STORAGE_KEY);
    return raw === "2d" ? "2d" : "3d";
  } catch {
    return "3d";
  }
}

function persistCameraMode(mode: CameraMode): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(CAMERA_MODE_STORAGE_KEY, mode);
  } catch {
    // noop
  }
}

function isWebGLError(error: unknown): boolean {
  const raw = error instanceof Error ? error.message : String(error);
  return /failed to initialize webgl|webglcontextcreationerror|webgl/i.test(raw);
}

function mapErrorText(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error);
  if (isWebGLError(raw)) {
    return WEBGL_FALLBACK_MESSAGE;
  }
  return `Ошибка карты: ${raw}`;
}

function upsertImageLayer(
  map: MapLibreMap,
  {
    id,
    url,
    coordinates,
    opacity,
    visible,
  }: {
    id: string;
    url: string;
    coordinates: [number, number][];
    opacity: number;
    visible: boolean;
  },
) {
  const sourceId = `img-src-${id}`;
  const layerId = `img-layer-${id}`;
  const source = map.getSource(sourceId) as maplibregl.ImageSource | undefined;
  const coords = coordinates as unknown as [[number, number], [number, number], [number, number], [number, number]];

  if (source && typeof source.updateImage === "function") {
    source.updateImage({ url, coordinates: coords });
  } else {
    map.addSource(sourceId, { type: "image", url, coordinates: coords });
  }

  if (!map.getLayer(layerId)) {
    map.addLayer({ id: layerId, type: "raster", source: sourceId, paint: { "raster-opacity": opacity } });
  } else {
    map.setPaintProperty(layerId, "raster-opacity", opacity);
  }

  map.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none");
}

function upsertLineLayer(
  map: MapLibreMap,
  id: string,
  coordinates: [number, number][],
  color: string,
  width: number,
  dash?: number[],
) {
  const sourceId = `route-src-${id}`;
  const layerId = `route-layer-${id}`;
  const data: GeoJSON.Feature<GeoJSON.LineString> = {
    type: "Feature",
    geometry: { type: "LineString", coordinates },
    properties: {},
  };
  const source = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;

  if (source) {
    source.setData(data);
  } else {
    map.addSource(sourceId, { type: "geojson", data });
  }

  if (!map.getLayer(layerId)) {
    map.addLayer({
      id: layerId,
      type: "line",
      source: sourceId,
      paint: {
        "line-color": color,
        "line-width": width,
        "line-opacity": 0.95,
        ...(dash ? { "line-dasharray": dash } : {}),
      },
    });
  }
}

function upsertPointLayer(
  map: MapLibreMap,
  id: string,
  coordinate: [number, number],
  color: string,
  radius = 5,
) {
  const sourceId = `route-point-src-${id}`;
  const layerId = `route-point-layer-${id}`;
  const data: GeoJSON.Feature<GeoJSON.Point> = {
    type: "Feature",
    geometry: { type: "Point", coordinates: coordinate },
    properties: {},
  };
  const source = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;

  if (source) {
    source.setData(data);
  } else {
    map.addSource(sourceId, { type: "geojson", data });
  }

  if (!map.getLayer(layerId)) {
    map.addLayer({
      id: layerId,
      type: "circle",
      source: sourceId,
      paint: {
        "circle-radius": radius,
        "circle-color": color,
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 1.5,
      },
    });
  } else {
    map.setPaintProperty(layerId, "circle-color", color);
    map.setPaintProperty(layerId, "circle-radius", radius);
  }
}

function clearMapLibreRoutes(map: MapLibreMap) {
  for (const id of ["primary", "alt_1", "alt_2"]) {
    const lid = `route-layer-${id}`;
    const sid = `route-src-${id}`;
    if (map.getLayer(lid)) map.removeLayer(lid);
    if (map.getSource(sid)) map.removeSource(sid);
  }
  for (const id of ["start", "end"]) {
    const lid = `route-point-layer-${id}`;
    const sid = `route-point-src-${id}`;
    if (map.getLayer(lid)) map.removeLayer(lid);
    if (map.getSource(sid)) map.removeSource(sid);
  }
}

type RendererMode = "maplibre" | "leaflet";

function applyMapLibreCameraMode(map: MapLibreMap, mode: CameraMode, animate = true): void {
  if (mode === "3d") {
    map.dragRotate.enable();
    map.touchZoomRotate.enableRotation();
    map.easeTo({
      pitch: 55,
      bearing: -20,
      duration: animate ? 550 : 0,
      essential: true,
    });
    return;
  }

  map.touchZoomRotate.disableRotation();
  map.dragRotate.disable();
  map.easeTo({
    pitch: 0,
    bearing: 0,
    duration: animate ? 450 : 0,
    essential: true,
  });
}

function safeRemoveMaplibreMap(map: MapLibreMap | null): void {
  if (!map) return;
  try {
    map.remove();
  } catch {
    // Guard against duplicate remove() during fast renderer switches / StrictMode.
  }
}

function safeRemoveLeafletMap(map: L.Map | null): void {
  if (!map) return;
  try {
    map.remove();
  } catch {
    // Guard against duplicate remove() during fast renderer switches / StrictMode.
  }
}

function isCanvasLikelyBlank(canvas: HTMLCanvasElement): boolean {
  try {
    const gl =
      (canvas.getContext("webgl2", { preserveDrawingBuffer: true }) as WebGL2RenderingContext | null) ??
      (canvas.getContext("webgl", { preserveDrawingBuffer: true }) as WebGLRenderingContext | null) ??
      (canvas.getContext("experimental-webgl", { preserveDrawingBuffer: true }) as WebGLRenderingContext | null);
    if (!gl) return true;

    const w = Math.max(1, gl.drawingBufferWidth || canvas.width);
    const h = Math.max(1, gl.drawingBufferHeight || canvas.height);
    if (w < 2 || h < 2) return true;

    const probes = [
      [0.18, 0.18], [0.5, 0.18], [0.82, 0.18],
      [0.18, 0.5], [0.5, 0.5], [0.82, 0.5],
      [0.18, 0.82], [0.5, 0.82], [0.82, 0.82],
    ] as const;
    const px = new Uint8Array(4);
    const unique = new Set<string>();
    let minL = Number.POSITIVE_INFINITY;
    let maxL = Number.NEGATIVE_INFINITY;

    for (const [nx, ny] of probes) {
      const x = Math.min(w - 1, Math.max(0, Math.floor(nx * w)));
      const y = Math.min(h - 1, Math.max(0, Math.floor(ny * h)));
      gl.readPixels(x, y, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
      const key = `${px[0]},${px[1]},${px[2]},${px[3]}`;
      unique.add(key);

      const luma = px[0] * 0.2126 + px[1] * 0.7152 + px[2] * 0.0722;
      minL = Math.min(minL, luma);
      maxL = Math.max(maxL, luma);
      if (unique.size > 5) return false;
    }

    return unique.size <= 2 || maxL - minL < 3;
  } catch {
    return false;
  }
}

export function MapCanvas() {
  const { enabledLayers, aiView, aiCompleted, activeLayerId, routeResult, selectVessel } = useVizard();
  const { isMobile } = useBreakpoint();

  const containerRef = useRef<HTMLDivElement | null>(null);
  const maplibreRef = useRef<MapLibreMap | null>(null);
  const leafletRef = useRef<L.Map | null>(null);
  const leafletOverlaysRef = useRef<Record<string, L.ImageOverlay>>({});
  const leafletRoutesRef = useRef<Record<string, L.Polyline>>({});
  const leafletRoutePointsRef = useRef<Record<string, L.CircleMarker>>({});
  const hasFittedRef = useRef(false);

  const [rendererMode, setRendererMode] = useState<RendererMode>(() => readRendererModeFromStorage());
  const [cameraMode, setCameraMode] = useState<CameraMode>(() => readCameraModeFromStorage());
  const [mapError, setMapError] = useState<string | null>(null);

  const manifestQuery = useLayerManifestQuery(activeLayerId);

  const showObserved = enabledLayers.has("ai-observed");
  const showGaps = aiCompleted && enabledLayers.has("ai-gaps");
  const showReconstructed = aiCompleted && enabledLayers.has("ai-reconstructed");
  const showConfidence = aiCompleted && enabledLayers.has("ai-confidence");
  const showDifference = aiCompleted && enabledLayers.has("ai-diff");
  const showIceLegend = showObserved || showReconstructed;

  const defaultBounds = useMemo<LngLatBoundsLike>(() => [[20, 66], [130, 82]], []);
  const defaultLeafletBounds = useMemo(() => L.latLngBounds([66, 20], [82, 130]), []);

  useEffect(() => {
    persistRendererMode(rendererMode);
  }, [rendererMode]);

  useEffect(() => {
    persistCameraMode(cameraMode);
  }, [cameraMode]);

  useEffect(() => {
    if (rendererMode !== "maplibre") return;
    const map = maplibreRef.current;
    if (!map) return;
    applyMapLibreCameraMode(map, cameraMode, true);
  }, [rendererMode, cameraMode]);

  useEffect(() => {
    if (!containerRef.current) return;

    if (rendererMode === "maplibre") {
      // Cleanup fallback map if we are switching back.
      if (leafletRef.current) {
        safeRemoveLeafletMap(leafletRef.current);
        leafletRef.current = null;
        leafletOverlaysRef.current = {};
        leafletRoutesRef.current = {};
        leafletRoutePointsRef.current = {};
      }

      if (typeof maplibregl.supported === "function" && !maplibregl.supported({ failIfMajorPerformanceCaveat: true })) {
        hasFittedRef.current = false;
        setRendererMode("leaflet");
        setMapError(WEBGL_FALLBACK_MESSAGE);
        return;
      }

      let map: MapLibreMap;
      try {
        map = new maplibregl.Map({
          container: containerRef.current,
          style: BASE_STYLE,
          center: [78, 75],
          zoom: 3,
          minZoom: 2,
          maxZoom: 9,
          pitch: cameraMode === "3d" ? 55 : 0,
          bearing: cameraMode === "3d" ? -20 : 0,
          maxPitch: 70,
          dragRotate: cameraMode === "3d",
          touchPitch: cameraMode === "3d",
        });
      } catch (error) {
        if (isWebGLError(error)) {
          hasFittedRef.current = false;
          setRendererMode("leaflet");
          setMapError(WEBGL_FALLBACK_MESSAGE);
          return;
        }
        setMapError(mapErrorText(error));
        return;
      }

      maplibreRef.current = map;
      setMapError(null);
      let healthInterval: number | null = null;
      let disposed = false;

      const disposeMap = () => {
        if (disposed) return;
        disposed = true;
        if (healthInterval !== null) {
          window.clearInterval(healthInterval);
          healthInterval = null;
        }
        map.off("error", onError);
        safeRemoveMaplibreMap(map);
        if (maplibreRef.current === map) maplibreRef.current = null;
      };

      const onError = (ev: maplibregl.ErrorEvent) => {
        const err = (ev as { error?: unknown }).error;
        if (!err) return;
        if (isWebGLError(err)) {
          disposeMap();
          hasFittedRef.current = false;
          setRendererMode("leaflet");
          setMapError(WEBGL_FALLBACK_MESSAGE);
          return;
        }
        setMapError(mapErrorText(err));
      };

      map.on("error", onError);
      let healthChecks = 0;
      healthInterval = window.setInterval(() => {
        if (maplibreRef.current !== map) {
          if (healthInterval !== null) {
            window.clearInterval(healthInterval);
            healthInterval = null;
          }
          return;
        }
        healthChecks += 1;
        const styleReady = map.isStyleLoaded();
        const tilesReady = typeof map.areTilesLoaded === "function" ? map.areTilesLoaded() : true;
        const shouldProbe = (styleReady && tilesReady) || healthChecks >= 6;
        if (!shouldProbe) return;

        if (healthInterval !== null) {
          window.clearInterval(healthInterval);
          healthInterval = null;
        }
        if (!isCanvasLikelyBlank(map.getCanvas())) return;

        disposeMap();
        hasFittedRef.current = false;
        setRendererMode("leaflet");
        setMapError(BLANK_FRAME_FALLBACK_MESSAGE);
      }, 2000);

      map.on("load", () => {
        applyMapLibreCameraMode(map, cameraMode, false);
        map.fitBounds(defaultBounds, { padding: 20, duration: 0 });

        map.addSource("vessels", {
          type: "geojson",
          data: {
            type: "FeatureCollection",
            features: VESSELS.map((v) => ({
              type: "Feature",
              geometry: { type: "Point", coordinates: [v.lon, v.lat] },
              properties: { id: v.id, name: v.name },
            })),
          },
        });
        map.addLayer({
          id: "vessels-layer",
          type: "circle",
          source: "vessels",
          paint: {
            "circle-radius": 4,
            "circle-color": "#1C7ED6",
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 1,
          },
        });
        map.on("click", "vessels-layer", (e) => {
          const id = e.features?.[0]?.properties?.id as string | undefined;
          if (!id) return;
          const vessel = VESSELS.find((v) => v.id === id);
          if (vessel) selectVessel(vessel);
        });

        map.addSource("ports", {
          type: "geojson",
          data: {
            type: "FeatureCollection",
            features: PORTS.map((p) => ({
              type: "Feature",
              geometry: {
                type: "Point",
                coordinates: [45 + p.x * 60, 66 + (1 - p.y) * 14],
              },
              properties: { id: p.id, name: p.name },
            })),
          },
        });
        map.addLayer({
          id: "ports-layer",
          type: "circle",
          source: "ports",
          paint: {
            "circle-radius": 3,
            "circle-color": "#0B7285",
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 1,
          },
        });
      });

      return () => {
        disposeMap();
      };
    }

    // Leaflet fallback (no WebGL required).
    if (maplibreRef.current) {
      const staleMaplibre = maplibreRef.current;
      maplibreRef.current = null;
      safeRemoveMaplibreMap(staleMaplibre);
    }
    if (leafletRef.current) return;

    // Remove leftover maplibre DOM/classes before mounting leaflet on the same container.
    containerRef.current.classList.remove("maplibregl-map");
    containerRef.current.removeAttribute("style");
    while (containerRef.current.firstChild) {
      containerRef.current.removeChild(containerRef.current.firstChild);
    }

    const map = L.map(containerRef.current, {
      zoomControl: false,
      attributionControl: true,
      preferCanvas: true,
      worldCopyJump: true,
    }).setView([75, 78], 3);

    leafletRef.current = map;
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "© OpenStreetMap contributors",
    }).addTo(map);

    const vesselLayer = L.layerGroup();
    for (const vessel of VESSELS) {
      const marker = L.circleMarker([vessel.lat, vessel.lon], {
        radius: 4,
        color: "#ffffff",
        weight: 1,
        fillColor: "#1C7ED6",
        fillOpacity: 1,
      });
      marker.on("click", () => selectVessel(vessel));
      marker.bindTooltip(vessel.name, { direction: "top" });
      vesselLayer.addLayer(marker);
    }
    vesselLayer.addTo(map);

    const portsLayer = L.layerGroup();
    for (const p of PORTS) {
      const lat = 66 + (1 - p.y) * 14;
      const lon = 45 + p.x * 60;
      const marker = L.circleMarker([lat, lon], {
        radius: 3,
        color: "#ffffff",
        weight: 1,
        fillColor: "#0B7285",
        fillOpacity: 1,
      });
      marker.bindTooltip(p.name, { direction: "top" });
      portsLayer.addLayer(marker);
    }
    portsLayer.addTo(map);

    fetch("/smp_regions.geojson")
      .then((r) => r.json())
      .then((geojson) => {
        const priority = new Set([1, 2, 3, 6, 7, 9, 10]);
        L.geoJSON(geojson, {
          style: (feature) => {
            const r = feature?.properties?.region ?? 0;
            return {
              color: priority.has(r) ? "#E67700" : "#868E96",
              weight: priority.has(r) ? 1.5 : 0.7,
              opacity: priority.has(r) ? 0.7 : 0.35,
              fillColor: "transparent",
              fillOpacity: 0,
              dashArray: priority.has(r) ? undefined : "3 3",
            };
          },
        }).addTo(map);
      })
      .catch(() => {});

    map.fitBounds(defaultLeafletBounds, { padding: [20, 20], animate: false });
    setMapError(WEBGL_FALLBACK_MESSAGE);

    return () => {
      safeRemoveLeafletMap(map);
      if (leafletRef.current === map) leafletRef.current = null;
      leafletOverlaysRef.current = {};
      leafletRoutesRef.current = {};
      leafletRoutePointsRef.current = {};
    };
  }, [rendererMode, cameraMode, defaultBounds, defaultLeafletBounds, selectVessel]);

  useEffect(() => {
    const manifest = manifestQuery.data;
    if (!manifest) return;

    if (rendererMode === "maplibre") {
      const map = maplibreRef.current;
      if (!map || !map.isStyleLoaded()) return;

      const coordinates = manifest.coordinates;
      const byName = Object.fromEntries(manifest.views.map((v) => [v.name, v] as const));
      if (byName.observed) {
        upsertImageLayer(map, {
          id: "observed",
          url: apiImageUrl(byName.observed.url),
          coordinates,
          opacity: byName.observed.opacity,
          visible: showObserved,
        });
      }
      if (byName.reconstructed) {
        upsertImageLayer(map, {
          id: "reconstructed",
          url: apiImageUrl(byName.reconstructed.url),
          coordinates,
          opacity: byName.reconstructed.opacity,
          visible: showReconstructed,
        });
      }
      if (byName.confidence) {
        upsertImageLayer(map, {
          id: "confidence",
          url: apiImageUrl(byName.confidence.url),
          coordinates,
          opacity: byName.confidence.opacity,
          visible: showConfidence,
        });
      }
      if (byName.difference) {
        upsertImageLayer(map, {
          id: "difference",
          url: apiImageUrl(byName.difference.url),
          coordinates,
          opacity: byName.difference.opacity,
          visible: showDifference || showGaps,
        });
      }
      if (!hasFittedRef.current) {
        const [lonMin, latMin, lonMax, latMax] = manifest.bounds;
        map.fitBounds(
          [
            [lonMin, latMin],
            [lonMax, latMax],
          ],
          { padding: 40, duration: 900 },
        );
        hasFittedRef.current = true;
      }
      return;
    }

    const map = leafletRef.current;
    if (!map) return;

    const [lonMin, latMin, lonMax, latMax] = manifest.bounds;
    const bounds = L.latLngBounds([latMin, lonMin], [latMax, lonMax]);
    const byName = Object.fromEntries(manifest.views.map((v) => [v.name, v] as const));

    const desiredViews: Array<{ key: "observed" | "reconstructed" | "confidence" | "difference"; visible: boolean }> = [
      { key: "observed", visible: showObserved },
      { key: "reconstructed", visible: showReconstructed },
      { key: "confidence", visible: showConfidence },
      { key: "difference", visible: showDifference || showGaps },
    ];

    for (const v of desiredViews) {
      const mf = byName[v.key];
      const existing = leafletOverlaysRef.current[v.key];
      if (!mf) {
        if (existing && map.hasLayer(existing)) map.removeLayer(existing);
        delete leafletOverlaysRef.current[v.key];
        continue;
      }

      const url = apiImageUrl(mf.url);
      let overlay = existing;
      if (!overlay) {
        overlay = L.imageOverlay(url, bounds, { opacity: mf.opacity, interactive: false });
        leafletOverlaysRef.current[v.key] = overlay;
      } else {
        overlay.setUrl(url);
        overlay.setBounds(bounds);
        overlay.setOpacity(mf.opacity);
      }

      if (v.visible) {
        if (!map.hasLayer(overlay)) overlay.addTo(map);
      } else if (map.hasLayer(overlay)) {
        map.removeLayer(overlay);
      }
    }

    if (!hasFittedRef.current) {
      map.fitBounds(bounds, { padding: [40, 40], animate: true });
      hasFittedRef.current = true;
    }
  }, [rendererMode, manifestQuery.data, showObserved, showGaps, showReconstructed, showConfidence, showDifference]);

  useEffect(() => {
    if (rendererMode === "maplibre") {
      const map = maplibreRef.current;
      if (!map || !map.isStyleLoaded()) return;
      if (!routeResult) {
        clearMapLibreRoutes(map);
        return;
      }
      upsertLineLayer(
        map,
        "primary",
        routeResult.primary.points.map((p) => [p.lon, p.lat]),
        "#1C7ED6",
        3.5,
      );
      for (const [idx, alt] of routeResult.alternatives.entries()) {
        upsertLineLayer(
          map,
          `alt_${idx + 1}`,
          alt.points.map((p) => [p.lon, p.lat]),
          idx === 0 ? "#2F9E44" : "#E67700",
          2.5,
          [2, 1.5],
        );
      }
      const fallbackStart = routeResult.primary.points[0];
      const fallbackEnd = routeResult.primary.points[routeResult.primary.points.length - 1];
      const start = routeResult.start ?? fallbackStart;
      const end = routeResult.end ?? fallbackEnd;
      if (start) upsertPointLayer(map, "start", [start.lon, start.lat], "#2F9E44", 5);
      if (end) upsertPointLayer(map, "end", [end.lon, end.lat], "#E03131", 5);
      return;
    }

    const map = leafletRef.current;
    if (!map) return;

    const clearLeafletRoutes = () => {
      for (const layer of Object.values(leafletRoutesRef.current)) {
        if (map.hasLayer(layer)) map.removeLayer(layer);
      }
      leafletRoutesRef.current = {};
      for (const marker of Object.values(leafletRoutePointsRef.current)) {
        if (map.hasLayer(marker)) map.removeLayer(marker);
      }
      leafletRoutePointsRef.current = {};
    };

    if (!routeResult) {
      clearLeafletRoutes();
      return;
    }

    const upsertLeafletRoute = (
      id: string,
      points: Array<{ lon: number; lat: number }>,
      color: string,
      weight: number,
      dashArray?: string,
    ) => {
      const latLngs = points.map((p) => [p.lat, p.lon] as [number, number]);
      let line = leafletRoutesRef.current[id];
      if (!line) {
        line = L.polyline(latLngs, { color, weight, opacity: 0.95, dashArray }).addTo(map);
        leafletRoutesRef.current[id] = line;
      } else {
        line.setLatLngs(latLngs);
        line.setStyle({ color, weight, opacity: 0.95, dashArray });
        if (!map.hasLayer(line)) line.addTo(map);
      }
    };

    upsertLeafletRoute("primary", routeResult.primary.points, "#1C7ED6", 4.0);
    for (const [idx, alt] of routeResult.alternatives.entries()) {
      upsertLeafletRoute(`alt_${idx + 1}`, alt.points, idx === 0 ? "#2F9E44" : "#E67700", 3.0, "6 4");
    }

    const upsertLeafletPoint = (id: string, lat: number, lon: number, color: string) => {
      let marker = leafletRoutePointsRef.current[id];
      if (!marker) {
        marker = L.circleMarker([lat, lon], {
          radius: 5,
          color: "#ffffff",
          weight: 1.5,
          fillColor: color,
          fillOpacity: 1,
        }).addTo(map);
        leafletRoutePointsRef.current[id] = marker;
      } else {
        marker.setLatLng([lat, lon]);
        marker.setStyle({ fillColor: color });
        if (!map.hasLayer(marker)) marker.addTo(map);
      }
    };
    const fallbackStart = routeResult.primary.points[0];
    const fallbackEnd = routeResult.primary.points[routeResult.primary.points.length - 1];
    const start = routeResult.start ?? fallbackStart;
    const end = routeResult.end ?? fallbackEnd;
    if (start) upsertLeafletPoint("start", start.lat, start.lon, "#2F9E44");
    if (end) upsertLeafletPoint("end", end.lat, end.lon, "#E03131");

    const activeIds = new Set(["primary", ...routeResult.alternatives.map((_, idx) => `alt_${idx + 1}`)]);
    for (const [id, layer] of Object.entries(leafletRoutesRef.current)) {
      if (!activeIds.has(id)) {
        if (map.hasLayer(layer)) map.removeLayer(layer);
        delete leafletRoutesRef.current[id];
      }
    }
  }, [rendererMode, routeResult]);

  const handleZoomIn = () => {
    if (rendererMode === "leaflet") {
      leafletRef.current?.zoomIn();
      return;
    }
    maplibreRef.current?.zoomIn();
  };

  const handleZoomOut = () => {
    if (rendererMode === "leaflet") {
      leafletRef.current?.zoomOut();
      return;
    }
    maplibreRef.current?.zoomOut();
  };

  const handleReset = () => {
    if (rendererMode === "leaflet") {
      leafletRef.current?.fitBounds(defaultLeafletBounds, { padding: [20, 20], animate: true });
      return;
    }
    maplibreRef.current?.fitBounds(defaultBounds, { padding: 20, duration: 700 });
  };

  const handleToggleCameraMode = () => {
    if (rendererMode === "leaflet") {
      hasFittedRef.current = false;
      setCameraMode("3d");
      setMapError("Пробуем снова включить 3D/WebGL...");
      setRendererMode("maplibre");
      return;
    }
    setCameraMode((prev) => (prev === "3d" ? "2d" : "3d"));
  };

  return (
    <TooltipProvider delayDuration={200}>
      <div className="absolute inset-0 bg-map-water z-0 isolate">
        <div ref={containerRef} className="absolute inset-0" />
        {mapError && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 z-40 pointer-events-auto bg-status-error/10 border border-status-error/40 text-foreground rounded-md px-3 py-2 text-xs max-w-[90vw]">
            {mapError}
          </div>
        )}

        <div className="absolute bottom-14 left-3 flex items-end gap-2 pointer-events-none z-10">
          {showIceLegend && (
            <div className="bg-card/90 backdrop-blur-sm rounded-lg px-2 py-1.5 shadow-lg border border-border/30">
              <div className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">Ледовые классы</div>
              <div className="space-y-0.5">
                {ICE_CLASS_LEGEND.map((c) => (
                  <div key={c.id} className="flex items-center gap-1.5">
                    <span className="inline-block h-2.5 w-2.5 rounded-sm border border-border/50 shrink-0" style={{ backgroundColor: c.rgb }} />
                    <span className="text-[8px] text-foreground leading-tight">{c.name}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="absolute bottom-14 right-3 flex flex-col gap-1 pointer-events-auto z-10">
          <div className="bg-card/90 backdrop-blur-sm rounded-lg shadow-lg border border-border/30 flex flex-col overflow-hidden">
            {[
              { icon: Plus, label: "Приблизить", action: handleZoomIn },
              { icon: Minus, label: "Отдалить", action: handleZoomOut },
              { icon: RotateCcw, label: "Сброс", action: handleReset },
            ].map((c, i) => (
              <Tooltip key={i}>
                <TooltipTrigger asChild>
                  <button
                    className={cn(
                      "h-8 w-8 flex items-center justify-center text-foreground hover:bg-muted/80 transition-colors",
                      i < 2 && "border-b border-border/30",
                    )}
                    aria-label={c.label}
                    onClick={c.action}
                  >
                    <c.icon className="h-3.5 w-3.5" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="left">{c.label}</TooltipContent>
              </Tooltip>
            ))}
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  className={cn("h-8 w-8 flex items-center justify-center text-foreground hover:bg-muted/80 transition-colors border-t border-border/30")}
                  aria-label={
                    rendererMode === "leaflet"
                      ? "Попробовать включить 3D/WebGL"
                      : cameraMode === "3d"
                        ? "Переключить в 2D"
                        : "Переключить в 3D"
                  }
                  onClick={handleToggleCameraMode}
                  title={rendererMode === "leaflet" ? "Попробовать снова включить 3D/WebGL" : undefined}
                >
                  <span className="text-[10px] font-semibold tracking-wide">{rendererMode === "leaflet" ? "3D" : cameraMode === "3d" ? "3D" : "2D"}</span>
                </button>
              </TooltipTrigger>
              <TooltipContent side="left">
                {rendererMode === "leaflet"
                  ? "Попробовать снова включить 3D/WebGL"
                  : cameraMode === "3d"
                    ? "Переключить в 2D"
                    : "Переключить в 3D"}
              </TooltipContent>
            </Tooltip>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
