import { LayerStatus } from "@/lib/vizard-types";
import { CheckCircle2, CloudOff, Clock3, Sparkles, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

const META: Record<LayerStatus, { label: string; icon: React.ComponentType<{ className?: string }>; cls: string }> = {
  current: {
    label: "Актуально",
    icon: CheckCircle2,
    cls: "border-status-current/30 bg-status-current/10 text-status-current",
  },
  forecast: {
    label: "Прогноз",
    icon: Clock3,
    cls: "border-status-forecast/30 bg-status-forecast/10 text-status-forecast",
  },
  ai: {
    label: "AI",
    icon: Sparkles,
    cls: "border-status-ai/30 bg-status-ai/10 text-status-ai",
  },
  nodata: {
    label: "Нет данных",
    icon: CloudOff,
    cls: "border-status-nodata/30 bg-status-nodata/10 text-status-nodata",
  },
  error: {
    label: "Ошибка",
    icon: AlertTriangle,
    cls: "border-status-error/30 bg-status-error/10 text-status-error",
  },
};

export function StatusChip({ status, label, className }: { status: LayerStatus; label?: string; className?: string }) {
  const meta = META[status];
  const Icon = meta.icon;
  return (
    <span className={cn("chip", meta.cls, className)}>
      <Icon className="h-3 w-3" />
      <span>{label ?? meta.label}</span>
    </span>
  );
}
