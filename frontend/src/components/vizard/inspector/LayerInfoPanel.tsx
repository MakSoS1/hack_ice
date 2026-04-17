import { LayerDef } from "@/lib/vizard-types";
import { Button } from "@/components/ui/button";
import { StatusChip } from "../StatusChip";
import { Download, Link as LinkIcon, Image as ImageIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function LayerInfoPanel({ layer, compact }: { layer: LayerDef; compact?: boolean }) {
  return (
    <div className="flex flex-col h-full">
      {!compact && (
        <header className="px-4 py-3 border-b border-border">
          <div className="text-xs text-muted-foreground uppercase tracking-wider">Информация по слою</div>
          <h2 className="text-base font-semibold text-foreground mt-0.5">{layer.label}</h2>
        </header>
      )}

      <div className={cn("flex-1 space-y-3", compact ? "px-3 py-3" : "px-4 py-4 space-y-4")}>
        {compact && <h3 className="text-sm font-semibold text-foreground">{layer.label}</h3>}
        <Field label="Источник" value={layer.source ?? "Composite"} mono />
        <Field label="Обновление" value={layer.updated ?? "16.12.2023, 18:00"} mono />
        <Field label="Тип" value={layer.type ?? "Растровый, GeoTIFF"} />
        <div className="flex items-center justify-between">
          <Field label="Покрытие" value={layer.coverage ?? "68%"} mono />
          <div>
            <div className="text-xs text-muted-foreground mb-0.5">Уверенность</div>
            <StatusChip status="current" label={layer.confidence ?? "Высокая"} className="!text-[10px]" />
          </div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground mb-0.5">Описание</div>
          <p className="text-xs text-foreground leading-relaxed">
            {layer.description ??
              "Растровый слой данных для оперативного мониторинга и принятия решений."}
          </p>
        </div>
      </div>

      <footer className={cn("border-t border-border space-y-1.5", compact ? "px-3 py-2" : "px-4 py-3 space-y-2")}>
        <div className="grid grid-cols-2 gap-1.5">
          <Button variant="outline" size="sm" className="gap-1.5 h-8 text-xs">
            <Download className="h-3.5 w-3.5" />
            GeoTIFF
          </Button>
          <Button variant="outline" size="sm" className="gap-1.5 h-8 text-xs">
            <ImageIcon className="h-3.5 w-3.5" />
            PNG
          </Button>
        </div>
        <Button variant="ghost" size="sm" className="w-full justify-start gap-1.5 text-muted-foreground h-8 text-xs">
          <LinkIcon className="h-3.5 w-3.5" />
          Скопировать ссылку
        </Button>
      </footer>
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={`text-sm text-foreground ${mono ? "font-mono" : ""}`}>{value}</div>
    </div>
  );
}
