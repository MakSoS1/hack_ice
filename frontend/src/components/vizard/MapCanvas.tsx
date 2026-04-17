import { useEffect, useMemo, useRef } from "react";
import maplibregl, { LngLatBoundsLike, Map as MapLibreMap } from "maplibre-gl";
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

function upsertImageLayer(
  map: MapLibreMap,
  { id, url, coordinates, opacity, visible }: {
    id: string; url: string; coordinates: [number, number][]; opacity: number; visible: boolean;
  },
) {
  const sourceId = `img-src-${id}`;
  const layerId = `img-layer-${id}`;
  const source = map.getSource(sourceId) as maplibregl.ImageSource | undefined;
  if (source && typeof source.updateImage === "function") {
    source.updateImage({ url, coordinates: coordinates as unknown as [[number, number], [number, number], [number, number], [number, number]] });
  } else {
    map.addSource(sourceId, { type: "image", url, coordinates: coordinates as unknown as [[number, number], [number, number], [number, number], [number, number]] });
  }
  if (!map.getLayer(layerId)) {
    map.addLayer({ id: layerId, type: "raster", source: sourceId, paint: { "raster-opacity": opacity } });
  } else {
    map.setPaintProperty(layerId, "raster-opacity", opacity);
  }
  map.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none");
}

function upsertLineLayer(map: MapLibreMap, id: string, coordinates: [number, number][], color: string, width: number, dash?: number[]) {
  const sourceId = `route-src-${id}`;
  const layerId = `route-layer-${id}`;
  const data: GeoJSON.Feature<GeoJSON.LineString> = { type: "Feature", geometry: { type: "LineString", coordinates }, properties: {} };
  const source = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
  if (source) { source.setData(data); } else { map.addSource(sourceId, { type: "geojson", data }); }
  if (!map.getLayer(layerId)) {
    map.addLayer({ id: layerId, type: "line", source: sourceId, paint: { "line-color": color, "line-width": width, "line-opacity": 0.95, ...(dash ? { "line-dasharray": dash } : {}) } });
  }
}

export function MapCanvas() {
  const { enabledLayers, aiView, aiCompleted, activeLayerId, routeResult, selectVessel } = useVizard();
  const { isMobile } = useBreakpoint();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const hasFittedRef = useRef(false);
  const manifestQuery = useLayerManifestQuery(activeLayerId);

  const showObserved = aiView === "observation" || !aiCompleted;
  const showReconstructed = aiCompleted && (aiView === "reconstruction" || enabledLayers.has("ai-reconstructed"));
  const showConfidence = aiCompleted && (aiView === "confidence" || enabledLayers.has("ai-confidence"));
  const showDifference = aiCompleted && (aiView === "difference" || enabledLayers.has("ai-diff"));

  const defaultBounds = useMemo<LngLatBoundsLike>(() => [[20, 66], [130, 82]], []);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current, style: BASE_STYLE, center: [78, 75], zoom: 3, minZoom: 2, maxZoom: 9, maxPitch: 0,
    });
    mapRef.current = map;

    map.on("load", () => {
      map.fitBounds(defaultBounds, { padding: 20, duration: 0 });
      map.addSource("vessels", { type: "geojson", data: { type: "FeatureCollection", features: VESSELS.map((v) => ({ type: "Feature", geometry: { type: "Point", coordinates: [v.lon, v.lat] }, properties: { id: v.id, name: v.name } })) } });
      map.addLayer({ id: "vessels-layer", type: "circle", source: "vessels", paint: { "circle-radius": 4, "circle-color": "#1C7ED6", "circle-stroke-color": "#ffffff", "circle-stroke-width": 1 } });
      map.on("click", "vessels-layer", (e) => { const id = e.features?.[0]?.properties?.id as string | undefined; if (!id) return; const vessel = VESSELS.find((v) => v.id === id); if (vessel) selectVessel(vessel); });
      map.addSource("ports", { type: "geojson", data: { type: "FeatureCollection", features: PORTS.map((p) => ({ type: "Feature", geometry: { type: "Point", coordinates: [45 + p.x * 60, 66 + (1 - p.y) * 14] }, properties: { id: p.id, name: p.name } })) } });
      map.addLayer({ id: "ports-layer", type: "circle", source: "ports", paint: { "circle-radius": 3, "circle-color": "#0B7285", "circle-stroke-color": "#ffffff", "circle-stroke-width": 1 } });
    });

    return () => { map.remove(); mapRef.current = null; };
  }, [defaultBounds, selectVessel]);

  useEffect(() => {
    const map = mapRef.current;
    const manifest = manifestQuery.data;
    if (!map || !manifest || !map.isStyleLoaded()) return;
    const coordinates = manifest.coordinates;
    const byName = Object.fromEntries(manifest.views.map((v) => [v.name, v] as const));
    if (byName.observed) upsertImageLayer(map, { id: "observed", url: apiImageUrl(byName.observed.url), coordinates, opacity: byName.observed.opacity, visible: showObserved });
    if (byName.reconstructed) upsertImageLayer(map, { id: "reconstructed", url: apiImageUrl(byName.reconstructed.url), coordinates, opacity: byName.reconstructed.opacity, visible: showReconstructed });
    if (byName.confidence) upsertImageLayer(map, { id: "confidence", url: apiImageUrl(byName.confidence.url), coordinates, opacity: byName.confidence.opacity, visible: showConfidence });
    if (byName.difference) upsertImageLayer(map, { id: "difference", url: apiImageUrl(byName.difference.url), coordinates, opacity: byName.difference.opacity, visible: showDifference });
    if (!hasFittedRef.current) { const [lonMin, latMin, lonMax, latMax] = manifest.bounds; map.fitBounds([[lonMin, latMin], [lonMax, latMax]], { padding: 40, duration: 900 }); hasFittedRef.current = true; }
  }, [manifestQuery.data, showObserved, showReconstructed, showConfidence, showDifference]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    if (!routeResult) { for (const id of ["primary", "alt_1", "alt_2"]) { const lid = `route-layer-${id}`; const sid = `route-src-${id}`; if (map.getLayer(lid)) map.removeLayer(lid); if (map.getSource(sid)) map.removeSource(sid); } return; }
    upsertLineLayer(map, "primary", routeResult.primary.points.map((p) => [p.lon, p.lat]), "#1C7ED6", 3.5);
    for (const [idx, alt] of routeResult.alternatives.entries()) { upsertLineLayer(map, `alt_${idx + 1}`, alt.points.map((p) => [p.lon, p.lat]), idx === 0 ? "#2F9E44" : "#E67700", 2.5, [2, 1.5]); }
  }, [routeResult]);

  return (
    <TooltipProvider delayDuration={200}>
      <div className="absolute inset-0 bg-map-water">
        <div ref={containerRef} className="absolute inset-0" />

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
              <span>0</span><span>50</span><span>100 км</span>
            </div>
          </div>
        </div>

        <div className="absolute bottom-14 right-3 flex flex-col gap-1 pointer-events-auto z-10">
          <div className="bg-card/90 backdrop-blur-sm rounded-lg shadow-lg border border-border/30 flex flex-col overflow-hidden">
            {[
              { icon: Plus, label: "Приблизить", action: () => mapRef.current?.zoomIn() },
              { icon: Minus, label: "Отдалить", action: () => mapRef.current?.zoomOut() },
              { icon: RotateCcw, label: "Сброс", action: () => { mapRef.current?.fitBounds(defaultBounds, { padding: 20, duration: 700 }); } },
            ].map((c, i) => (
              <Tooltip key={i}>
                <TooltipTrigger asChild>
                  <button
                    className={cn("h-8 w-8 flex items-center justify-center text-foreground hover:bg-muted/80 transition-colors", i < 2 && "border-b border-border/30")}
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
