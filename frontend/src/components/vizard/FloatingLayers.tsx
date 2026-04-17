import { useState } from "react";
import { useVizard } from "@/store/vizard-store";
import { LAYER_GROUPS } from "@/lib/vizard-data";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { Layers, ChevronDown } from "lucide-react";

export function FloatingLayers() {
  const { enabledLayers, toggleLayer, selectedLayerId, selectLayer } = useVizard();
  const [expanded, setExpanded] = useState(false);

  const activeLayers = LAYER_GROUPS.flatMap((g) => g.layers).filter((l) => enabledLayers.has(l.id));

  return (
    <div className="absolute top-[60px] right-3 z-30 pointer-events-auto flex flex-col items-end gap-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className={cn(
          "bg-card/95 backdrop-blur-sm rounded-xl shadow-lg border border-border/50 flex items-center gap-2 pl-3 pr-2 h-9 text-sm font-medium transition-colors",
          expanded && "bg-card"
        )}
      >
        <Layers className="h-4 w-4 text-muted-foreground" />
        <span>Слои</span>
        {activeLayers.length > 0 && (
          <span className="h-5 min-w-[20px] px-1 rounded-full bg-accent-blue text-accent-blue-foreground text-[11px] flex items-center justify-center font-medium">
            {activeLayers.length}
          </span>
        )}
        <ChevronDown className={cn("h-3.5 w-3.5 text-muted-foreground transition-transform", expanded && "rotate-180")} />
      </button>

      {expanded && (
        <div className="bg-card/95 backdrop-blur-sm rounded-xl shadow-lg border border-border/50 w-[240px] max-h-[50vh] overflow-y-auto">
          <div className="p-2">
            {LAYER_GROUPS.map((group) => (
              <div key={group.id} className="mb-2 last:mb-0">
                <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {group.label}
                </div>
                {group.layers.map((layer) => {
                  const on = enabledLayers.has(layer.id);
                  const sel = selectedLayerId === layer.id;
                  return (
                    <button
                      key={layer.id}
                      onClick={() => selectLayer(layer.id)}
                      className={cn(
                        "w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left transition-colors",
                        sel ? "bg-accent-blue/10" : "hover:bg-muted"
                      )}
                    >
                      <Switch
                        checked={on}
                        onCheckedChange={() => toggleLayer(layer.id)}
                        onClick={(e) => e.stopPropagation()}
                        className="data-[state=checked]:bg-accent-blue scale-[0.65] origin-left"
                      />
                      <span className={cn("h-2 w-2 rounded-sm shrink-0", layer.swatch ?? "bg-muted")} />
                      <span className="text-xs flex-1 truncate">{layer.label}</span>
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
