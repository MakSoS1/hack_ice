import { useMemo, useState } from "react";
import { useVizard } from "@/store/vizard-store";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Route, X, AlertTriangle, Clock, Ruler, Snowflake, Info } from "lucide-react";
import { StatusChip } from "../StatusChip";
import { useLayerManifestQuery, useSolveRouteMutation } from "@/hooks/use-vizard-api";
import { cn } from "@/lib/utils";
import { ICE_CLASS_LEGEND } from "@/lib/vizard-data";

const ROUTE_POINTS = [
  { id: "murmansk", name: "Мурманск", lon: 33.08, lat: 68.97 },
  { id: "sabetta", name: "Сабетта", lon: 72.6, lat: 71.2 },
  { id: "dudinka", name: "Дудинка", lon: 86.18, lat: 69.41 },
  { id: "dikson", name: "Диксон", lon: 80.52, lat: 73.51 },
];

function pointInsideBounds(lon: number, lat: number, bounds: [number, number, number, number]): boolean {
  const [lonMin, latMin, lonMax, latMax] = bounds;
  return lon >= lonMin && lon <= lonMax && lat >= latMin && lat <= latMax;
}

function pointFromBounds(bounds: [number, number, number, number], tx: number, ty: number): { lon: number; lat: number } {
  const [lonMin, latMin, lonMax, latMax] = bounds;
  return {
    lon: lonMin + (lonMax - lonMin) * tx,
    lat: latMin + (latMax - latMin) * ty,
  };
}

export function RoutingPanel({ compact }: { compact?: boolean } = {}) {
  const {
    routeBuilt,
    activeLayerId,
    routeResult,
    setRouteResult,
    clearRoute,
    enableLayers,
    disableLayers,
    setAiView,
    activeLayerSummary,
  } = useVizard();
  const solveRouteMutation = useSolveRouteMutation();
  const manifestQuery = useLayerManifestQuery(activeLayerId);

  const [pointA, setPointA] = useState("murmansk");
  const [pointB, setPointB] = useState("sabetta");
  const [vesselClass, setVesselClass] = useState<"Arc4" | "Arc5" | "Arc6" | "Arc7" | "Arc9">("Arc7");
  const [confidencePenalty, setConfidencePenalty] = useState("2.0");
  const [routingNote, setRoutingNote] = useState<string | null>(null);

  const pA = useMemo(() => ROUTE_POINTS.find((p) => p.id === pointA) ?? ROUTE_POINTS[0], [pointA]);
  const pB = useMemo(() => ROUTE_POINTS.find((p) => p.id === pointB) ?? ROUTE_POINTS[1], [pointB]);

  async function handleBuildRoute() {
    if (!activeLayerId) return;
    const bounds = manifestQuery.data?.bounds as [number, number, number, number] | undefined;

    let start = { lon: pA.lon, lat: pA.lat };
    let end = { lon: pB.lon, lat: pB.lat };
    let adjusted = false;

    if (bounds) {
      const autoStart = pointFromBounds(bounds, 0.18, 0.32);
      const autoEnd = pointFromBounds(bounds, 0.82, 0.68);

      if (!pointInsideBounds(start.lon, start.lat, bounds)) {
        start = autoStart;
        adjusted = true;
      }
      if (!pointInsideBounds(end.lon, end.lat, bounds)) {
        end = autoEnd;
        adjusted = true;
      }

      if (Math.abs(start.lon - end.lon) < 1e-6 && Math.abs(start.lat - end.lat) < 1e-6) {
        end = pointFromBounds(bounds, 0.78, 0.22);
        adjusted = true;
      }
    }

    const payload = {
      layer_id: activeLayerId,
      start_lon: start.lon,
      start_lat: start.lat,
      end_lon: end.lon,
      end_lat: end.lat,
      vessel_class: vesselClass,
      confidence_penalty: Number(confidencePenalty),
    } as const;

    const data = await solveRouteMutation.mutateAsync(payload);
    setRoutingNote(
      adjusted
        ? "Выбранные порты вышли за границы активного слоя. Для корректного расчета точки автоматически смещены внутрь покрытия."
        : null,
    );
    disableLayers(["ai-observed", "ai-confidence", "ai-diff"]);
    enableLayers(["ai-reconstructed"]);
    setAiView("reconstruction");
    setRouteResult(data);
  }

  function handleClear() {
    clearRoute();
  }

  const primary = routeResult?.primary;
  const alternatives = routeResult?.alternatives ?? [];
  const diagnostics = routeResult?.diagnostics;
  const effectiveMode = activeLayerSummary?.model_mode_effective ?? null;
  const isFallback = Boolean(effectiveMode && effectiveMode.includes("fallback"));

  return (
    <div className="flex flex-col">
      {!compact && (
        <header className="px-4 py-3 border-b border-border">
          <div className="text-xs text-muted-foreground uppercase tracking-wider">Маршрутизация</div>
          <h2 className="text-base font-semibold text-foreground mt-0.5">Маршрут</h2>
        </header>
      )}

      <div className={cn("space-y-3", compact ? "px-3 py-3" : "px-4 py-4 space-y-4")}>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label className="text-xs text-muted-foreground">Точка А</Label>
            <Select value={pointA} onValueChange={setPointA}>
              <SelectTrigger className="h-9 mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROUTE_POINTS.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs text-muted-foreground">Точка Б</Label>
            <Select value={pointB} onValueChange={setPointB}>
              <SelectTrigger className="h-9 mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROUTE_POINTS.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label className="text-xs text-muted-foreground">Класс судна</Label>
            <Select value={vesselClass} onValueChange={(v) => setVesselClass(v as typeof vesselClass)}>
              <SelectTrigger className="h-9 mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Arc4">Arc4</SelectItem>
                <SelectItem value="Arc5">Arc5</SelectItem>
                <SelectItem value="Arc6">Arc6</SelectItem>
                <SelectItem value="Arc7">Arc7</SelectItem>
                <SelectItem value="Arc9">Arc9</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs text-muted-foreground">Штраф увер.</Label>
            <Select value={confidencePenalty} onValueChange={setConfidencePenalty}>
              <SelectTrigger className="h-9 mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1.0">1.0</SelectItem>
                <SelectItem value="2.0">2.0</SelectItem>
                <SelectItem value="3.0">3.0</SelectItem>
                <SelectItem value="4.0">4.0</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <Button
            onClick={handleBuildRoute}
            className="gap-2 bg-accent-blue text-accent-blue-foreground hover:bg-accent-blue/90 h-10"
            disabled={!activeLayerId || solveRouteMutation.isPending || pointA === pointB}
          >
            <Route className="h-4 w-4" />
            {solveRouteMutation.isPending ? "Считаем…" : "Построить"}
          </Button>
          <Button variant="outline" onClick={handleClear} className="gap-2 h-10">
            <X className="h-4 w-4" />
            Очистить
          </Button>
        </div>

        {!activeLayerId && (
          <div className="bg-muted/40 border border-border rounded-md p-2 text-xs text-muted-foreground">
            Сначала выполните AI-восстановление для построения маршрута.
          </div>
        )}

        {solveRouteMutation.isError && (
          <div className="bg-status-error/10 border border-status-error/30 rounded-md p-2 flex items-start gap-2 text-xs">
            <AlertTriangle className="h-3.5 w-3.5 text-status-error shrink-0 mt-0.5" />
            <div className="text-muted-foreground">{(solveRouteMutation.error as Error).message}</div>
          </div>
        )}

        {routingNote && (
          <div className="bg-amber-500/10 border border-amber-500/30 rounded-md p-2 flex items-start gap-2 text-xs">
            <Info className="h-3.5 w-3.5 text-amber-500 shrink-0 mt-0.5" />
            <div className="text-muted-foreground">{routingNote}</div>
          </div>
        )}

        {routeBuilt && primary && (
          <div className="space-y-2 pt-1">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Результат</div>

            {effectiveMode && (
              <div className={cn("border rounded-md p-2 text-xs", isFallback ? "bg-amber-500/10 border-amber-500/30" : "bg-emerald-500/10 border-emerald-500/30")}>
                <div className="text-foreground font-medium">Режим реконструкции: {effectiveMode}</div>
                <div className="text-muted-foreground mt-0.5">
                  {isFallback
                    ? "Слой построен эвристикой (fallback), а не нейросетью. Для демо это важно озвучить."
                    : "Слой построен моделью без fallback."}
                </div>
              </div>
            )}

            {diagnostics && (
              <div className="border border-border rounded-md p-2.5 bg-muted/40">
                <div className="text-xs font-medium text-foreground mb-1.5">Проверка, что маршрут учитывает лед</div>
                <div className="grid grid-cols-2 gap-1.5 text-xs">
                  <Metric label="Прямая дистанция" value={`${diagnostics.direct_distance_km.toFixed(0)} км`} />
                  <Metric label="Базовый shortest" value={`${diagnostics.baseline_distance_km.toFixed(0)} км`} />
                  <Metric
                    label="Снижение риска vs shortest"
                    value={`${diagnostics.risk_reduction_vs_baseline_pct.toFixed(1)}%`}
                    highlight
                  />
                  <Metric
                    label="Отклонение по длине"
                    value={`${diagnostics.distance_over_baseline_km >= 0 ? "+" : ""}${diagnostics.distance_over_baseline_km.toFixed(0)} км (${diagnostics.distance_over_baseline_pct >= 0 ? "+" : ""}${diagnostics.distance_over_baseline_pct.toFixed(1)}%)`}
                  />
                </div>
              </div>
            )}

            <RouteCard
              title="Основной"
              accent="bg-accent-blue"
              meta={[
                { icon: Clock, label: "Время", value: `${primary.eta_hours.toFixed(1)} ч` },
                { icon: Ruler, label: "Длина", value: `${primary.distance_km.toFixed(0)} км` },
              ]}
            >
              <div className="flex items-center gap-1.5 flex-wrap">
                <StatusChip status="forecast" label={`Риск: ${primary.risk_score.toFixed(2)}`} />
                <StatusChip status="ai" label={`Увер.: ${primary.confidence_score.toFixed(2)}`} />
              </div>
            </RouteCard>

            {alternatives.map((alt, idx) => (
              <RouteCard
                key={alt.route_id}
                title={`Альт. ${idx + 1}`}
                accent="bg-status-ai"
                meta={[
                  { icon: Clock, label: "Время", value: `${alt.eta_hours.toFixed(1)} ч` },
                  { icon: Ruler, label: "Длина", value: `${alt.distance_km.toFixed(0)} км` },
                ]}
              >
                <div className="flex items-center gap-1.5 flex-wrap">
                  <StatusChip status="current" label={`Риск: ${alt.risk_score.toFixed(2)}`} />
                  <StatusChip status="ai" label={`Увер.: ${alt.confidence_score.toFixed(2)}`} />
                </div>
              </RouteCard>
            ))}

            <div className="bg-accent-blue/10 border border-accent-blue/30 rounded-md p-2 flex items-start gap-2 text-xs">
              <Snowflake className="h-3.5 w-3.5 text-accent-blue shrink-0 mt-0.5" />
              <div>
              <div className="text-foreground font-medium">Маршрут по AI-карте льда</div>
                <div className="text-muted-foreground mt-0.5">
                  Карта автоматически переключена на слой "Восстановление". Маркеры A/B и линия показывают расчет по предсказанному льду.
                </div>
                <div className="flex flex-wrap gap-x-2 gap-y-0.5 mt-1">
                  {ICE_CLASS_LEGEND.slice(0, 4).map((c) => (
                    <span key={c.id} className="flex items-center gap-1">
                      <span className="inline-block h-2 w-2 rounded-sm" style={{ backgroundColor: c.rgb }} />
                      <span className="text-[9px] text-muted-foreground">{c.name}</span>
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function RouteCard({
  title,
  accent,
  meta,
  children,
}: {
  title: string;
  accent: string;
  meta: { icon: React.ComponentType<{ className?: string }>; label: string; value: string }[];
  children: React.ReactNode;
}) {
  return (
    <div className="border border-border rounded-md overflow-hidden">
      <div className="flex items-center gap-2 px-2.5 py-1.5 bg-muted/40 border-b border-border">
        <span className={`h-2 w-2 rounded-full ${accent}`} />
        <span className="text-xs font-medium text-foreground">{title}</span>
      </div>
      <div className="px-2.5 py-2 space-y-1.5">
        <div className="grid grid-cols-2 gap-1.5 text-xs">
          {meta.map((m, i) => (
            <div key={i} className="flex items-center gap-1 text-muted-foreground">
              <m.icon className="h-3 w-3" />
              <span>{m.label}:</span>
              <span className="font-mono text-foreground font-medium">{m.value}</span>
            </div>
          ))}
        </div>
        {children}
      </div>
    </div>
  );
}

function Metric({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-1.5">
      <span className="text-muted-foreground">{label}:</span>
      <span className={cn("font-mono font-medium text-right", highlight ? "text-status-current" : "text-foreground")}>{value}</span>
    </div>
  );
}
