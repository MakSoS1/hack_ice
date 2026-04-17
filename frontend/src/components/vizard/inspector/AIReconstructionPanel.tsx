import { useEffect, useMemo, useState } from "react";
import { useVizard } from "@/store/vizard-store";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sparkles, BoxSelect, Maximize2, Loader2, AlertTriangle } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import {
  useCreateReconstructionJobMutation,
  useLayerSummaryQuery,
  useRecentLayersQuery,
  useReconstructionJobQuery,
  useScenesQuery,
} from "@/hooks/use-vizard-api";

const VIEW_MODES = [
  { id: "observation", label: "Набл." },
  { id: "reconstruction", label: "Восст." },
  { id: "confidence", label: "Увер." },
  { id: "difference", label: "Разн." },
] as const;

const VIEW_MODES_FULL = [
  { id: "observation", label: "Наблюдение" },
  { id: "reconstruction", label: "Восстановление" },
  { id: "confidence", label: "Уверенность" },
  { id: "difference", label: "Разница" },
] as const;

const HISTORY_MAP: Record<string, number> = {
  "3": 1,
  "7": 2,
  "14": 3,
  "30": 4,
};

const MODEL_MODE_MAP: Record<string, "fast" | "balanced" | "precise"> = {
  fast: "fast",
  balanced: "balanced",
  precise: "precise",
};

function formatSceneLabel(sceneId: string): string {
  const parts = sceneId.split("_");
  if (parts.length < 6) return sceneId;
  const ts = parts[4];
  const y = ts.slice(0, 4);
  const m = ts.slice(4, 6);
  const d = ts.slice(6, 8);
  const hh = ts.slice(9, 11);
  const mm = ts.slice(11, 13);
  return `${d}.${m}.${y} ${hh}:${mm}`;
}

export function AIReconstructionPanel({ compact }: { compact?: boolean } = {}) {
  const {
    aiView,
    setAiView,
    aiRunning,
    aiCompleted,
    aiJobId,
    aiProgress,
    activeLayerId,
    activeLayerSummary,
    setAiJob,
    setAiStatus,
    setActiveLayerSummary,
    resetAi,
  } = useVizard();

  const [historyWindow, setHistoryWindow] = useState("7");
  const [modelMode, setModelMode] = useState("balanced");
  const [sceneId, setSceneId] = useState<string | null>(null);

  const scenesQuery = useScenesQuery();
  const createMutation = useCreateReconstructionJobMutation();
  const jobQuery = useReconstructionJobQuery(aiJobId, Boolean(aiJobId));
  const summaryQuery = useLayerSummaryQuery(activeLayerId);
  const recentLayersQuery = useRecentLayersQuery(30, true);

  const sortedScenes = useMemo(() => {
    const list = scenesQuery.data?.scenes ?? [];
    return [...list].sort((a, b) => (a.acquisition_start < b.acquisition_start ? 1 : -1));
  }, [scenesQuery.data?.scenes]);

  useEffect(() => {
    if (!sceneId && sortedScenes.length > 0) {
      setSceneId(sortedScenes[0].scene_id);
    }
  }, [sceneId, sortedScenes]);

  useEffect(() => {
    const data = jobQuery.data;
    if (!data) return;
    setAiStatus(data.status, data.progress, data.layer_id);
  }, [jobQuery.data, setAiStatus]);

  useEffect(() => {
    if (summaryQuery.data) {
      setActiveLayerSummary(summaryQuery.data);
    }
  }, [summaryQuery.data, setActiveLayerSummary]);

  async function handleRun() {
    if (!sceneId) return;
    const created = await createMutation.mutateAsync({
      scene_id: sceneId,
      history_steps: HISTORY_MAP[historyWindow] ?? 2,
      model_mode: MODEL_MODE_MAP[modelMode] ?? "balanced",
    });
    setAiJob(created.job_id, sceneId);
  }

  function handleUsePreparedDemo() {
    const layers = recentLayersQuery.data?.layers ?? [];
    if (layers.length === 0) return;
    const sameSceneLayers = sceneId ? layers.filter((l) => l.scene_id === sceneId) : [];
    const pickFrom = sameSceneLayers.length > 0 ? sameSceneLayers : layers;
    const best =
      pickFrom.find((l) => {
        const mode = (l.summary?.model_mode_effective as string | undefined) ?? "";
        return mode === "balanced" || mode === "precise";
      }) ?? pickFrom[0];
    setAiStatus("completed", 1.0, best.layer_id);
  }

  const latestJobError = jobQuery.data?.status === "failed" ? jobQuery.data.error : null;
  const modes = compact ? VIEW_MODES : VIEW_MODES_FULL;

  return (
    <div className="flex flex-col">
      {!compact && (
        <header className="px-4 py-3 border-b border-border">
          <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
            <Sparkles className="h-3 w-3" />
            AI
          </div>
          <h2 className="text-base font-semibold text-foreground mt-0.5">AI-восстановление</h2>
        </header>
      )}

      <div className={cn("space-y-4", compact ? "px-3 py-3" : "px-4 py-4 space-y-5")}>
        {!compact && (
          <Section title="Выбор области">
            <div className="grid grid-cols-2 gap-2">
              <Button variant="outline" size="sm" className="gap-2" disabled>
                <BoxSelect className="h-4 w-4" />
                Выделить
              </Button>
              <Button variant="outline" size="sm" className="gap-2" disabled>
                <Maximize2 className="h-4 w-4" />
                По экрану
              </Button>
            </div>
          </Section>
        )}

        <Section title="Параметры" compact={compact}>
          <div className="space-y-2.5">
            <div>
              <Label className="text-xs text-muted-foreground">Сцена</Label>
              <Select value={sceneId ?? ""} onValueChange={setSceneId} disabled={sortedScenes.length === 0}>
                <SelectTrigger className="h-9 mt-1">
                  <SelectValue placeholder="Выберите сцену" />
                </SelectTrigger>
                <SelectContent>
                  {sortedScenes.map((s) => (
                    <SelectItem key={s.scene_id} value={s.scene_id}>
                      {formatSceneLabel(s.scene_id)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs text-muted-foreground">Окно</Label>
                <Select value={historyWindow} onValueChange={setHistoryWindow}>
                  <SelectTrigger className="h-9 mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="3">3 сут</SelectItem>
                    <SelectItem value="7">7 сут</SelectItem>
                    <SelectItem value="14">14 сут</SelectItem>
                    <SelectItem value="30">30 сут</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Модель</Label>
                <Select value={modelMode} onValueChange={setModelMode}>
                  <SelectTrigger className="h-9 mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="fast">Быстрый</SelectItem>
                    <SelectItem value="balanced">Баланс</SelectItem>
                    <SelectItem value="precise">Точный</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
        </Section>

        <Section title="Запуск" compact={compact}>
          <Button
            className="w-full gap-2 bg-accent-blue text-accent-blue-foreground hover:bg-accent-blue/90 h-10"
            onClick={handleRun}
            disabled={aiRunning || !sceneId || createMutation.isPending}
          >
            {aiRunning || createMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Восстановление…
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4" />
                Заполнить пропуски
              </>
            )}
          </Button>
          {(aiRunning || createMutation.isPending) && <Progress value={Math.round(aiProgress * 100)} className="mt-2 h-1.5" />}
          <Button
            variant="outline"
            className="w-full mt-2 h-9"
            onClick={handleUsePreparedDemo}
            disabled={recentLayersQuery.isLoading || !recentLayersQuery.data || recentLayersQuery.data.layers.length === 0}
          >
            Загрузить готовый демо-слой
          </Button>
        </Section>

        {latestJobError && (
          <div className="bg-status-error/10 border border-status-error/30 rounded-md p-2 flex items-start gap-2 text-xs">
            <AlertTriangle className="h-3.5 w-3.5 text-status-error shrink-0 mt-0.5" />
            <div className="text-muted-foreground whitespace-pre-wrap">{latestJobError}</div>
          </div>
        )}

        {aiCompleted && activeLayerSummary && (
          <Section title="Результат" compact={compact}>
            <div className="bg-muted/50 border border-border rounded-md p-2.5 space-y-1.5">
              <Stat label="Было" value={`${Math.round(activeLayerSummary.coverage_before * 100)}%`} />
              <Stat label="Стало" value={`${Math.round(activeLayerSummary.coverage_after * 100)}%`} highlight />
              <Stat label="Восстановлено" value={`${activeLayerSummary.restored_area_km2.toFixed(0)} км²`} />
              <Stat label="Уверенность" value={activeLayerSummary.mean_confidence.toFixed(2)} />
            </div>
            <Button variant="ghost" size="sm" className="w-full mt-1.5 text-muted-foreground h-8" onClick={resetAi}>
              Сбросить
            </Button>
          </Section>
        )}

        <Section title="Режим отображения" compact={compact}>
          <div className="grid grid-cols-4 gap-1 p-1 bg-muted rounded-md">
            {modes.map((m) => (
              <button
                key={m.id}
                onClick={() => setAiView(m.id)}
                disabled={!aiCompleted && m.id !== "observation"}
                className={cn(
                  "py-1.5 text-xs rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
                  aiView === m.id ? "bg-card text-foreground shadow-sm font-medium" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {m.label}
              </button>
            ))}
          </div>
        </Section>
      </div>
    </div>
  );
}

function Section({ title, children, compact }: { title: string; children: React.ReactNode; compact?: boolean }) {
  return (
    <div>
      <div className={cn("font-semibold uppercase tracking-wider text-muted-foreground mb-1.5", compact ? "text-[10px]" : "text-xs")}>{title}</div>
      {children}
    </div>
  );
}

function Stat({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn("font-mono font-medium", highlight ? "text-status-current" : "text-foreground")}>{value}</span>
    </div>
  );
}
