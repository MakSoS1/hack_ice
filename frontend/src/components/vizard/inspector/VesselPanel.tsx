import { Vessel } from "@/lib/vizard-types";
import { useVizard } from "@/store/vizard-store";
import { Button } from "@/components/ui/button";
import { Route, FileText, MapPin, Ship } from "lucide-react";
import { cn } from "@/lib/utils";

export function VesselPanel({ vessel, compact }: { vessel: Vessel; compact?: boolean }) {
  const { trackRange, setTrackRange, setShowTrack, showTrack, setInspectorMode } = useVizard();

  return (
    <div className="flex flex-col h-full">
      {!compact && (
        <header className="px-4 py-3 border-b border-border">
          <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
            <Ship className="h-3 w-3" />
            Карточка судна
          </div>
          <h2 className="text-base font-semibold text-foreground mt-0.5">{vessel.name}</h2>
          <div className="text-xs text-muted-foreground mt-0.5">Класс {vessel.iceClass}</div>
        </header>
      )}

      <div className={cn("flex-1 space-y-2", compact ? "px-3 py-3" : "px-4 py-4 space-y-3")}>
        {compact && (
          <div>
            <h3 className="text-sm font-semibold text-foreground">{vessel.name}</h3>
            <div className="text-[11px] text-muted-foreground">Класс {vessel.iceClass}</div>
          </div>
        )}
        <div className="grid grid-cols-2 gap-2">
          <Field label="Курс" value={`${vessel.course}°`} mono />
          <Field label="Скорость" value={`${vessel.speed} уз`} mono />
        </div>
        <Field label="Координаты" value={`${vessel.lat}° с.ш., ${vessel.lon}° в.д.`} mono icon={MapPin} />
        <Field label="Фиксация" value={vessel.lastFix} mono />
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">Период трека</div>
          <div className="grid grid-cols-3 gap-1 p-1 bg-muted rounded-md">
            {(["12", "24", "48"] as const).map((r) => (
              <button
                key={r}
                onClick={() => setTrackRange(r)}
                className={cn(
                  "py-1.5 text-xs rounded transition-colors",
                  trackRange === r ? "bg-card text-foreground shadow-sm font-medium" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {r} ч
              </button>
            ))}
          </div>
        </div>
      </div>

      <footer className={cn("border-t border-border space-y-1.5", compact ? "px-3 py-2" : "px-4 py-3 space-y-2")}>
        <Button
          variant="outline"
          size="sm"
          className="w-full justify-start gap-1.5 h-8 text-xs"
          onClick={() => setShowTrack(!showTrack)}
        >
          <Route className="h-3.5 w-3.5" />
          {showTrack ? "Скрыть трек" : "Показать трек"}
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="w-full justify-start gap-1.5 h-8 text-xs"
          onClick={() => setInspectorMode("route")}
        >
          <Route className="h-3.5 w-3.5" />
          Маршрут до судна
        </Button>
      </footer>
    </div>
  );
}

function Field({
  label,
  value,
  mono,
  icon: Icon,
}: {
  label: string;
  value: string;
  mono?: boolean;
  icon?: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={`text-sm text-foreground flex items-center gap-1 ${mono ? "font-mono" : ""}`}>
        {Icon && <Icon className="h-3 w-3 text-muted-foreground" />}
        {value}
      </div>
    </div>
  );
}
