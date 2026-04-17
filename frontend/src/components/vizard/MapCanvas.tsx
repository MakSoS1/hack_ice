import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { LngLatBoundsLike, Map as MapLibreMap } from "maplibre-gl";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useVizard, VESSELS } from "@/store/vizard-store";
import { PORTS } from "@/lib/vizard-data";
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

function clearMapLibreRoutes(map: MapLibreMap) {
  for (const id of ["primary", "alt_1", "alt_2"]) {
    const lid = `route-layer-${id}`;
    const sid = `route-src-${id}`;
    if (map.getLayer(lid)) map.removeLayer(lid);
    if (map.getSource(sid)) map.removeSource(sid);
  }
}

type RendererMode = "maplibre" | "leaflet";

export function MapCanvas() {
  const { enabledLayers, aiView, aiCompleted, activeLayerId, routeResult, selectVessel } = useVizard();
  const { isMobile } = useBreakpoint();

  const containerRef = useRef<HTMLDivElement | null>(null);
  const maplibreRef = useRef<MapLibreMap | null>(null);
  const leafletRef = useRef<L.Map | null>(null);
  const leafletOverlaysRef = useRef<Record<string, L.ImageOverlay>>({});
  const leafletRoutesRef = useRef<Record<string, L.Polyline>>({});
  const hasFittedRef = useRef(false);

  const [rendererMode, setRendererMode] = useState<RendererMode>("maplibre");
  const [mapError, setMapError] = useState<string | null>(null);

  const manifestQuery = useLayerManifestQuery(activeLayerId);

  const showObserved = aiView === "observation" || !aiCompleted;
  const showReconstructed = aiCompleted && (aiView === "reconstruction" || enabledLayers.has("ai-reconstructed"));
  const showConfidence = aiCompleted && (aiView === "confidence" || enabledLayers.has("ai-confidence"));
  const showDifference = aiCompleted && (aiView === "difference" || enabledLayers.has("ai-diff"));

  const defaultBounds = useMemo<LngLatBoundsLike>(() => [[20, 66], [130, 82]], []);
  const defaultLeafletBounds = useMemo(() => L.latLngBounds([66, 20], [82, 130]), []);

  useEffect(() => {
    if (!containerRef.current) return;

    if (rendererMode === "maplibre") {
      // Cleanup fallback map if we are switching back.
      if (leafletRef.current) {
        leafletRef.current.remove();
        leafletRef.current = null;
        leafletOverlaysRef.current = {};
        leafletRoutesRef.current = {};
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
          maxPitch: 0,
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

      const onError = (ev: maplibregl.ErrorEvent) => {
        const err = (ev as { error?: unknown }).error;
        if (!err) return;
        if (isWebGLError(err)) {
          map.remove();
          maplibreRef.current = null;
          hasFittedRef.current = false;
          setRendererMode("leaflet");
          setMapError(WEBGL_FALLBACK_MESSAGE);
          return;
        }
        setMapError(mapErrorText(err));
      };

      map.on("error", onError);
      map.on("load", () => {
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
        map.remove();
        if (maplibreRef.current === map) maplibreRef.current = null;
      };
    }

    // Leaflet fallback (no WebGL required).
    if (maplibreRef.current) {
      maplibreRef.current.remove();
      maplibreRef.current = null;
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

    map.fitBounds(defaultLeafletBounds, { padding: [20, 20], animate: false });
    setMapError(WEBGL_FALLBACK_MESSAGE);

    return () => {
      map.remove();
      if (leafletRef.current === map) leafletRef.current = null;
      leafletOverlaysRef.current = {};
      leafletRoutesRef.current = {};
    };
  }, [rendererMode, defaultBounds, defaultLeafletBounds, selectVessel]);

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
          visible: showDifference,
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
      { key: "difference", visible: showDifference },
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
  }, [rendererMode, manifestQuery.data, showObserved, showReconstructed, showConfidence, showDifference]);

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
      return;
    }

    const map = leafletRef.current;
    if (!map) return;

    const clearLeafletRoutes = () => {
      for (const layer of Object.values(leafletRoutesRef.current)) {
        if (map.hasLayer(layer)) map.removeLayer(layer);
      }
      leafletRoutesRef.current = {};
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

  return (
    <TooltipProvider delayDuration={200}>
      <div className="absolute inset-0 bg-map-water">
        <div ref={containerRef} className="absolute inset-0" />
        {mapError && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 z-40 pointer-events-auto bg-status-error/10 border border-status-error/40 text-foreground rounded-md px-3 py-2 text-xs max-w-[90vw]">
            {mapError}
          </div>
        )}

        <div className="absolute bottom-14 left-3 flex items-end gap-2 pointer-events-none z-10">
          <div className="bg-card/90 backdrop-blur-sm rounded-lg p-1 flex flex-col items-center shadow-lg border border-border/30 hidden sm:flex">
            <Compass className="h-3.5 w-3.5 text-primary" />
            <span className="text-[8px] font-semibold text-foreground mt-0.5">С</span>
          </div>
          <div className="bg-card/90 backdrop-blur-sm rounded-lg px-2 py-1 shadow-lg border border-border/30 hidden sm:block">
            <div className="flex items-end gap-0">
              <div className="h-2 w-6 border border-foreground bg-foreground" />
              <div className="h-2 w-6 border border-foreground bg-card" />
              <div className="h-2 w-6 border border-foreground bg-foreground" />
            </div>
            <div className="flex justify-between text-[8px] font-mono mt-0.5 text-muted-foreground">
              <span>0</span>
              <span>50</span>
              <span>100 км</span>
            </div>
          </div>
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
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
