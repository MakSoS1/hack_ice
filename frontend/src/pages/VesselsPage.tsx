import { useEffect } from "react";
import { VizardShell } from "@/components/vizard/VizardShell";
import { useVizard, VESSELS } from "@/store/vizard-store";

const VesselsPage = () => {
  const { selectVessel } = useVizard();
  useEffect(() => {
    selectVessel(VESSELS[0]);
  }, [selectVessel]);
  return <VizardShell initialMode="vessel" />;
};
export default VesselsPage;
