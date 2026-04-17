import { useState } from "react";
import { VizardShell } from "@/components/vizard/VizardShell";

const ReportsPage = () => {
  const [open, setOpen] = useState(true);
  return <VizardShell initialMode="layer" reportOpen={open} setReportOpen={setOpen} />;
};
export default ReportsPage;
