import { useEffect, useState } from "react";
import { MapCanvas } from "@/components/vizard/MapCanvas";
import { InspectorContent } from "@/components/vizard/RightInspector";
import { ReportModal } from "@/components/vizard/ReportModal";
import { FloatingSearch } from "@/components/vizard/FloatingSearch";
import { FloatingLayers } from "@/components/vizard/FloatingLayers";
import { FloatingActions } from "@/components/vizard/FloatingActions";
import { FloatingTimeline } from "@/components/vizard/FloatingTimeline";
import { SlidePanel } from "@/components/vizard/SlidePanel";
import { useVizard } from "@/store/vizard-store";
import { InspectorMode } from "@/lib/vizard-types";
import { useBreakpoint } from "@/hooks/use-mobile";
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle } from "@/components/ui/drawer";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { LeftSidebar } from "@/components/vizard/LeftSidebar";

interface VizardShellProps {
  initialMode?: InspectorMode;
  reportOpen?: boolean;
  setReportOpen?: (b: boolean) => void;
}

export function VizardShell({ initialMode, reportOpen: extOpen, setReportOpen: extSetOpen }: VizardShellProps) {
  const { setInspectorMode, inspectorMode, activeLayerSummary, aiCompleted } = useVizard();
  const [localOpen, setLocalOpen] = useState(false);
  const open = extOpen ?? localOpen;
  const setOpen = extSetOpen ?? setLocalOpen;

  const [panelOpen, setPanelOpen] = useState(false);
  const [layersSheetOpen, setLayersSheetOpen] = useState(false);

  const { isMobile } = useBreakpoint();

  useEffect(() => {
    if (initialMode) setInspectorMode(initialMode);
  }, [initialMode, setInspectorMode]);

  useEffect(() => {
    if (inspectorMode !== "empty") {
      setPanelOpen(true);
    }
  }, [inspectorMode]);

  if (isMobile) {
    return (
      <div className="h-[100dvh] w-screen bg-chrome overflow-hidden">
        <MapCanvas />

        <FloatingSearch />
        <FloatingActions
          onLayers={() => setLayersSheetOpen(true)}
          onAI={() => { setInspectorMode("ai"); setPanelOpen(true); }}
          onRoute={() => { setInspectorMode("route"); setPanelOpen(true); }}
          aiActive={inspectorMode === "ai"}
          routeActive={inspectorMode === "route"}
        />
        <FloatingTimeline />

        {aiCompleted && activeLayerSummary && (
          <div className="absolute top-3 right-3 z-30 pointer-events-auto bg-card/95 backdrop-blur-sm rounded-xl shadow-lg p-2.5 min-w-[130px] border border-border/50">
            <div className="text-[10px] text-muted-foreground mb-0.5">Покрытие</div>
            <div className="text-xl font-bold text-status-current leading-none">
              {Math.round(activeLayerSummary.coverage_after * 100)}%
            </div>
            <div className="text-[10px] text-muted-foreground mt-0.5">
              +{activeLayerSummary.restored_area_km2.toFixed(0)} км²
            </div>
          </div>
        )}

        <Drawer open={panelOpen} onOpenChange={setPanelOpen}>
          <DrawerContent className="max-h-[70vh]">
            <DrawerHeader className="pb-1 pt-2">
              <DrawerTitle className="text-sm">
                {inspectorMode === "ai" && "AI-восстановление"}
                {inspectorMode === "route" && "Маршрут"}
                {inspectorMode === "vessel" && "Судно"}
                {inspectorMode === "layer" && "Слой"}
                {inspectorMode === "empty" && "Панель"}
              </DrawerTitle>
            </DrawerHeader>
            <div className="overflow-y-auto px-2 pb-safe">
              <InspectorContent compact />
            </div>
          </DrawerContent>
        </Drawer>

        <Sheet open={layersSheetOpen} onOpenChange={setLayersSheetOpen}>
          <SheetContent side="left" className="w-[280px] p-0">
            <SheetTitle className="sr-only">Слои</SheetTitle>
            <LeftSidebar inSheet />
          </SheetContent>
        </Sheet>

        <ReportModal open={open} onOpenChange={setOpen} />
      </div>
    );
  }

  return (
    <div className="h-screen w-screen bg-chrome overflow-hidden">
      <MapCanvas />

      <FloatingSearch />
      <FloatingLayers />
      <FloatingActions
        onLayers={() => {}}
        onAI={() => { setInspectorMode("ai"); setPanelOpen(true); }}
        onRoute={() => { setInspectorMode("route"); setPanelOpen(true); }}
        aiActive={inspectorMode === "ai"}
        routeActive={inspectorMode === "route"}
      />
      <FloatingTimeline />

      {aiCompleted && activeLayerSummary && (
        <div className="absolute top-3 right-3 z-30 pointer-events-auto bg-card/95 backdrop-blur-sm rounded-xl shadow-lg p-3 min-w-[150px] border border-border/50">
          <div className="text-[10px] text-muted-foreground mb-0.5">AI результат</div>
          <div className="text-2xl font-bold text-status-current leading-none">
            {Math.round(activeLayerSummary.coverage_after * 100)}%
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            +{activeLayerSummary.restored_area_km2.toFixed(0)} км² восстановлено
          </div>
          <div className="text-xs text-muted-foreground">
            Уверенность: <span className="text-foreground font-medium">{activeLayerSummary.mean_confidence.toFixed(2)}</span>
          </div>
        </div>
      )}

      {panelOpen && (
        <SlidePanel onClose={() => setPanelOpen(false)}>
          <InspectorContent />
        </SlidePanel>
      )}

      <ReportModal open={open} onOpenChange={setOpen} />
    </div>
  );
}
