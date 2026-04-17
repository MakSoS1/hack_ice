import { useVizard } from "@/store/vizard-store";
import { Layers, Sparkles, Route } from "lucide-react";
import { Button } from "@/components/ui/button";

export function EmptyPanel() {
  const { setInspectorMode } = useVizard();
  return (
    <div className="flex flex-col items-center justify-center h-full p-4 text-center">
      <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center mb-2">
        <Layers className="h-4 w-4 text-muted-foreground" />
      </div>
      <h3 className="text-xs font-medium text-foreground">Выберите объект</h3>
      <p className="text-[11px] text-muted-foreground mt-1 max-w-[200px]">
        Слой, AI или маршрут
      </p>
      <div className="flex gap-2 mt-3">
        <Button variant="outline" size="sm" className="gap-1.5 h-8 text-xs" onClick={() => setInspectorMode("ai")}>
          <Sparkles className="h-3.5 w-3.5" />
          AI
        </Button>
        <Button variant="outline" size="sm" className="gap-1.5 h-8 text-xs" onClick={() => setInspectorMode("route")}>
          <Route className="h-3.5 w-3.5" />
          Маршрут
        </Button>
      </div>
    </div>
  );
}
