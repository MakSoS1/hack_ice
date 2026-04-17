import { useVizard } from "@/store/vizard-store";
import { LAYER_GROUPS } from "@/lib/vizard-data";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

export function LeftSidebar({ inSheet }: { inSheet?: boolean } = {}) {
  const { enabledLayers, toggleLayer, selectedLayerId, selectLayer } = useVizard();

  return (
    <aside className={cn("flex flex-col", inSheet ? "w-full" : "w-56 shrink-0 border-r border-border", "bg-card")}>
      <div className="flex-1 overflow-y-auto py-2">
        {LAYER_GROUPS.map((group) => (
          <div key={group.id} className="mb-1">
            <div className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              {group.label}
            </div>
            <ul className="space-y-0.5 px-1.5">
              {group.layers.map((layer) => {
                const enabled = enabledLayers.has(layer.id);
                const selected = selectedLayerId === layer.id;
                return (
                  <li
                    key={layer.id}
                    className={cn(
                      "group flex items-center gap-2 px-2 py-1.5 rounded text-sm cursor-pointer transition-colors",
                      selected ? "bg-accent-blue/10 ring-1 ring-accent-blue/40" : "hover:bg-muted",
                    )}
                    onClick={() => selectLayer(layer.id)}
                  >
                    <Switch
                      checked={enabled}
                      onCheckedChange={() => toggleLayer(layer.id)}
                      onClick={(e) => e.stopPropagation()}
                      aria-label={`Включить слой ${layer.label}`}
                      className="data-[state=checked]:bg-accent-blue scale-75 origin-left"
                    />
                    <span
                      className={cn("h-2.5 w-2.5 rounded-sm border border-border shrink-0", layer.swatch ?? "bg-muted")}
                      aria-hidden
                    />
                    <span className="flex-1 truncate text-xs">{layer.label}</span>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </aside>
  );
}
