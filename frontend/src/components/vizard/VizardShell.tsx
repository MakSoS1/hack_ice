import { useEffect, useRef, useState } from "react";
import { MapCanvas } from "@/components/vizard/MapCanvas";
import { InspectorContent } from "@/components/vizard/RightInspector";
import { ReportModal } from "@/components/vizard/ReportModal";
import { FloatingSearch } from "@/components/vizard/FloatingSearch";
import { FloatingLayers } from "@/components/vizard/FloatingLayers";
import { FloatingActions } from "@/components/vizard/FloatingActions";
import { FloatingTimeline } from "@/components/vizard/FloatingTimeline";
import { FloatingViewModes } from "@/components/vizard/FloatingViewModes";
import { SlidePanel } from "@/components/vizard/SlidePanel";
import { useVizard } from "@/store/vizard-store";
import { InspectorMode } from "@/lib/vizard-types";
import { useBreakpoint } from "@/hooks/use-mobile";
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle } from "@/components/ui/drawer";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { LeftSidebar } from "@/components/vizard/LeftSidebar";
import { listRecentLayers } from "@/lib/api-client";

interface VizardShellProps {
  initialMode?: InspectorMode;
  reportOpen?: boolean;
  setReportOpen?: (b: boolean) => void;
}

export function VizardShell({ initialMode, reportOpen: extOpen, setReportOpen: extSetOpen }: VizardShellProps) {
  const { setInspectorMode, inspectorMode, setAiStatus, enableLayers, disableLayers, setAiView } = useVizard();
  const autoloadRef = useRef(false);
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
    if (autoloadRef.current) return;
    autoloadRef.current = true;
    listRecentLayers(50, 0)
      .then((res) => {
        const layers = res.layers ?? [];
        if (layers.length === 0) {
          setInspectorMode("ai");
          setPanelOpen(true);
          return;
        }

        const recentWithGaps = layers.find((l) => {
          const coverageBefore = Number((l.summary as { coverage_before?: number }).coverage_before ?? 1);
          return coverageBefore < 0.98;
        });
        const fallbackBest = layers.find((l) => {
          const mode = (l.summary?.model_mode_effective as string | undefined) ?? "";
          return mode === "balanced" || mode === "precise";
        });
        const best = recentWithGaps ?? fallbackBest ?? layers[0];

        disableLayers(["ai-reconstructed", "ai-confidence", "ai-diff"]);
        enableLayers(["ai-observed"]);
        setAiView("observation");
        setAiStatus("completed", 1.0, best.layer_id);
        setInspectorMode("ai");
        setPanelOpen(true);
      })
      .catch(() => {
        setInspectorMode("ai");
        setPanelOpen(true);
      });
  }, [disableLayers, enableLayers, setAiStatus, setAiView, setInspectorMode]);

  useEffect(() => {
    if (inspectorMode !== "empty") {
      setPanelOpen(true);
    }
  }, [inspectorMode]);

  if (isMobile) {
    return (
      <div className="relative h-[100dvh] w-screen bg-chrome overflow-hidden">
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
        <FloatingViewModes />

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
    <div className="relative h-screen w-screen bg-chrome overflow-hidden">
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
      <FloatingViewModes />

      {panelOpen && (
        <SlidePanel onClose={() => setPanelOpen(false)}>
          <InspectorContent />
        </SlidePanel>
      )}

      <ReportModal open={open} onOpenChange={setOpen} />
    </div>
  );
}
