import { useVizard } from "@/store/vizard-store";
import { TIMELINE } from "@/lib/vizard-data";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useBreakpoint } from "@/hooks/use-mobile";

const STATUS_CLS: Record<string, string> = {
  observation: "bg-status-current",
  reconstruction: "bg-status-ai",
  forecast: "bg-status-forecast",
  nodata: "bg-status-nodata",
  lowconf: "bg-status-error",
};

const STATUS_LABEL: Record<string, string> = {
  observation: "Наблюдение",
  reconstruction: "Восстановление",
  forecast: "Прогноз",
  nodata: "Нет данных",
  lowconf: "Низкая уверенность",
};

export function FloatingTimeline() {
  const { timelineHour, setTimelineHour } = useVizard();
  const { isMobile } = useBreakpoint();

  return (
    <div className={cn(
      "absolute z-30 pointer-events-auto",
      isMobile
        ? "bottom-2 left-2 right-2"
        : "bottom-3 left-1/2 -translate-x-1/2 w-[min(600px,60vw)]"
    )}>
      <TooltipProvider delayDuration={100}>
        <div className={cn(
          "bg-card/90 backdrop-blur-sm rounded-xl shadow-lg border border-border/50 overflow-hidden",
          isMobile ? "h-7" : "h-8"
        )}>
          <div className="h-full flex">
            {TIMELINE.map((seg, i) => (
              <Tooltip key={i}>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => setTimelineHour(i)}
                    className={cn(
                      "flex-1 h-full transition-all hover:brightness-110",
                      STATUS_CLS[seg.status],
                      timelineHour === i && "ring-2 ring-primary z-10",
                    )}
                    aria-label={`${formatHour(i)} — ${STATUS_LABEL[seg.status]}`}
                  />
                </TooltipTrigger>
                <TooltipContent side="top" className="text-xs">
                  <div className="font-medium">{formatHour(i)}</div>
                  <div className="text-muted-foreground">{STATUS_LABEL[seg.status]}</div>
                </TooltipContent>
              </Tooltip>
            ))}
          </div>
        </div>
      </TooltipProvider>
    </div>
  );
}

function formatHour(i: number) {
  const base = new Date(2023, 11, 15, 21, 0);
  const d = new Date(base.getTime() + i * 3600_000);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  return `${dd}.${mm} ${hh}:00`;
}
