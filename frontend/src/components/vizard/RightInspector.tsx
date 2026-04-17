import { useVizard } from "@/store/vizard-store";
import { LAYER_GROUPS } from "@/lib/vizard-data";
import { LayerInfoPanel } from "./inspector/LayerInfoPanel";
import { AIReconstructionPanel } from "./inspector/AIReconstructionPanel";
import { RoutingPanel } from "./inspector/RoutingPanel";
import { VesselPanel } from "./inspector/VesselPanel";
import { EmptyPanel } from "./inspector/EmptyPanel";

export function RightInspector() {
  const { inspectorMode, selectedLayerId, selectedVessel } = useVizard();

  const layer = LAYER_GROUPS.flatMap((g) => g.layers).find((l) => l.id === selectedLayerId);

  return (
    <aside className="w-[300px] shrink-0 bg-card border-l border-border flex flex-col overflow-y-auto">
      {inspectorMode === "layer" && layer && <LayerInfoPanel layer={layer} />}
      {inspectorMode === "ai" && <AIReconstructionPanel />}
      {inspectorMode === "route" && <RoutingPanel />}
      {inspectorMode === "vessel" && selectedVessel && <VesselPanel vessel={selectedVessel} />}
      {inspectorMode === "empty" && <EmptyPanel />}
    </aside>
  );
}

export function InspectorContent({ compact }: { compact?: boolean } = {}) {
  const { inspectorMode, selectedLayerId, selectedVessel } = useVizard();

  const layer = LAYER_GROUPS.flatMap((g) => g.layers).find((l) => l.id === selectedLayerId);

  return (
    <>
      {inspectorMode === "layer" && layer && <LayerInfoPanel layer={layer} compact={compact} />}
      {inspectorMode === "ai" && <AIReconstructionPanel compact={compact} />}
      {inspectorMode === "route" && <RoutingPanel compact={compact} />}
      {inspectorMode === "vessel" && selectedVessel && <VesselPanel vessel={selectedVessel} compact={compact} />}
      {inspectorMode === "empty" && <EmptyPanel />}
    </>
  );
}
