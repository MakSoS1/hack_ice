import { X } from "lucide-react";
import { Button } from "@/components/ui/button";

export function SlidePanel({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="absolute top-0 right-0 bottom-0 z-40 w-[340px] max-w-[40vw] pointer-events-auto">
      <div className="h-full bg-card/98 backdrop-blur-sm border-l border-border/50 shadow-2xl flex flex-col">
        <div className="flex items-center justify-between px-3 py-2 border-b border-border/50">
          <span className="text-xs text-muted-foreground">Панель</span>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {children}
        </div>
      </div>
    </div>
  );
}
