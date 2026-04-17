import { useMemo, useState } from "react";
import { useVizard } from "@/store/vizard-store";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Route, X, AlertTriangle, Clock, Ruler } from "lucide-react";
import { StatusChip } from "../StatusChip";
import { useSolveRouteMutation } from "@/hooks/use-vizard-api";
import { cn } from "@/lib/utils";

const ROUTE_POINTS = [
  { id: "murmansk", name: "Мурманск", lon: 33.08, lat: 68.97 },
  { id: "sabetta", name: "Сабетта", lon: 72.6, lat: 71.2 },
  { id: "dudinka", name: "Дудинка", lon: 86.18, lat: 69.41 },
  { id: "dikson", name: "Диксон", lon: 80.52, lat: 73.51 },
];

export function RoutingPanel({ compact }: { compact?: boolean } = {}) {
  const { routeBuilt, activeLayerId, routeResult, setRouteResult, clearRoute } = useVizard();
  const solveRouteMutation = useSolveRouteMutation();

  const [pointA, setPointA] = useState("murmansk");
  const [pointB, setPointB] = useState("sabetta");
  const [vesselClass, setVesselClass] = useState<"Arc4" | "Arc5" | "Arc6" | "Arc7" | "Arc9">("Arc7");
  const [confidencePenalty, setConfidencePenalty] = useState("2.0");

  const pA = useMemo(() => ROUTE_POINTS.find((p) => p.id === pointA) ?? ROUTE_POINTS[0], [pointA]);
  const pB = useMemo(() => ROUTE_POINTS.find((p) => p.id === pointB) ?? ROUTE_POINTS[1], [pointB]);

  async function handleBuildRoute() {
    if (!activeLayerId) return;

    const payload = {
      layer_id: activeLayerId,
      start_lon: pA.lon,
      start_lat: pA.lat,
      end_lon: pB.lon,
      end_lat: pB.lat,
      vessel_class: vesselClass,
      confidence_penalty: Number(confidencePenalty),
    } as const;

    const data = await solveRouteMutation.mutateAsync(payload);
    setRouteResult(data);
  }

  function handleClear() {
    clearRoute();
  }

  const primary = routeResult?.primary;
  const alternatives = routeResult?.alternatives ?? [];

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

        {routeBuilt && primary && (
          <div className="space-y-2 pt-1">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Результат</div>

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

            <div className="bg-status-forecast/10 border border-status-forecast/30 rounded-md p-2 flex items-start gap-2 text-xs">
              <AlertTriangle className="h-3.5 w-3.5 text-status-forecast shrink-0 mt-0.5" />
              <div className="text-foreground font-medium">Маршрут по AI-слою</div>
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
