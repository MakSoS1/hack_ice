import { Sparkles, Route, Layers } from "lucide-react";
import { cn } from "@/lib/utils";
import { useBreakpoint } from "@/hooks/use-mobile";

interface FloatingActionsProps {
  onLayers?: () => void;
  onAI: () => void;
  onRoute: () => void;
  aiActive?: boolean;
  routeActive?: boolean;
}

export function FloatingActions({ onLayers, onAI, onRoute, aiActive, routeActive }: FloatingActionsProps) {
  const { isMobile } = useBreakpoint();

  if (isMobile) {
    return (
      <div className="absolute top-2 left-2 z-30 pointer-events-auto flex flex-col gap-2">
        <ActionChip icon={Layers} label="Слои" onClick={onLayers} />
        <ActionChip icon={Sparkles} label="AI" onClick={onAI} active={aiActive} />
        <ActionChip icon={Route} label="Маршрут" onClick={onRoute} active={routeActive} />
      </div>
    );
  }

  return (
    <div className="absolute top-[60px] left-3 z-30 pointer-events-auto flex items-center gap-2">
      <ActionChip icon={Sparkles} label="AI-восстановление" onClick={onAI} active={aiActive} />
      <ActionChip icon={Route} label="Маршрут" onClick={onRoute} active={routeActive} />
    </div>
  );
}

function ActionChip({
  icon: Icon,
  label,
  onClick,
  active,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  onClick?: () => void;
  active?: boolean;
}) {
  const { isMobile } = useBreakpoint();

  if (isMobile) {
    return (
      <button
        onClick={onClick}
        className={cn(
          "h-10 w-10 rounded-full shadow-lg flex items-center justify-center transition-colors touch-manipulation",
          active
            ? "bg-primary text-primary-foreground"
            : "bg-card/95 backdrop-blur-sm text-foreground border border-border/50"
        )}
        aria-label={label}
      >
        <Icon className="h-5 w-5" />
      </button>
    );
  }

  return (
    <button
      onClick={onClick}
      className={cn(
        "bg-card/95 backdrop-blur-sm rounded-xl shadow-lg border border-border/50 flex items-center gap-2 pl-2.5 pr-3 h-9 text-sm font-medium transition-colors",
        active && "bg-primary text-primary-foreground border-primary"
      )}
    >
      <Icon className="h-4 w-4" />
      <span>{label}</span>
    </button>
  );
}
