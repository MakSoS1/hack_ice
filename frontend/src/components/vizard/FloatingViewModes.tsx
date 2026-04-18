import { useVizard } from "@/store/vizard-store";
import { cn } from "@/lib/utils";
import { Loader2 } from "lucide-react";

const VIEW_MODES = [
  { id: "observation" as const, short: "Набл", icon: "🧊" },
  { id: "reconstruction" as const, short: "Восст", icon: "✨" },
  { id: "confidence" as const, short: "Увер.", icon: "📊" },
  { id: "difference" as const, short: "Разн.", icon: "🔄" },
] as const;

const AI_VIEW_LAYERS = ["ai-observed", "ai-reconstructed", "ai-confidence", "ai-diff"];

const VIEW_TO_LAYER: Record<string, string> = {
  observation: "ai-observed",
  reconstruction: "ai-reconstructed",
  confidence: "ai-confidence",
  difference: "ai-diff",
};

export function FloatingViewModes() {
  const { aiView, setAiView, aiRunning, aiCompleted, aiProgress, enableLayers, disableLayers } = useVizard();

  function handleViewChange(viewId: string) {
    setAiView(viewId);
    const layerId = VIEW_TO_LAYER[viewId];
    const others = AI_VIEW_LAYERS.filter((l) => l !== layerId);
    disableLayers(others);
    enableLayers([layerId]);
  }

  if (aiRunning) {
    return (
      <div className="absolute bottom-28 left-1/2 -translate-x-1/2 z-30 pointer-events-none">
        <div className="bg-card/95 backdrop-blur-sm rounded-xl shadow-lg border border-accent-blue/40 px-4 py-2.5 flex items-center gap-2.5">
          <Loader2 className="h-4 w-4 text-accent-blue animate-spin" />
          <span className="text-xs font-medium text-foreground">Загрузка спутниковых данных…</span>
          <div className="w-24 h-1.5 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-accent-blue rounded-full transition-all duration-300"
              style={{ width: `${Math.round(aiProgress * 100)}%` }}
            />
          </div>
          <span className="text-[10px] text-muted-foreground font-mono">{Math.round(aiProgress * 100)}%</span>
        </div>
      </div>
    );
  }

  if (!aiCompleted) return null;

  return (
    <div className="absolute bottom-28 left-1/2 -translate-x-1/2 z-30 pointer-events-auto">
      <div className="bg-card/95 backdrop-blur-sm rounded-xl shadow-lg border border-border/50 px-1 py-1 flex items-center gap-0.5">
        {VIEW_MODES.map((m) => {
          const active = aiView === m.id;
          return (
            <button
              key={m.id}
              onClick={() => handleViewChange(m.id)}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-medium transition-all whitespace-nowrap",
                active
                  ? "bg-accent-blue text-accent-blue-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/60",
              )}
            >
              <span className="mr-1">{m.icon}</span>
              {m.short}
            </button>
          );
        })}
      </div>
    </div>
  );
}
