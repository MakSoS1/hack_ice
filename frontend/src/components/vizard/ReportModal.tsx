import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Download, FileText, Image as ImageIcon } from "lucide-react";
import { toast } from "sonner";

const OPTIONS = [
  { id: "current-view", label: "Текущий вид карты", default: true },
  { id: "selected-layers", label: "Выбранные слои", default: true },
  { id: "legend", label: "Добавить легенду", default: true },
  { id: "grid", label: "Добавить координатную сетку", default: false },
  { id: "scale", label: "Добавить шкалу", default: true },
  { id: "ai-summary", label: "Добавить сводку AI", default: true },
];

export function ReportModal({ open, onOpenChange }: { open: boolean; onOpenChange: (b: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>Сформировать отчёт</DialogTitle>
          <DialogDescription>
            Выберите содержимое отчёта. Будет использовано текущее состояние карты и активные слои.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          {OPTIONS.map((o) => (
            <div key={o.id} className="flex items-center gap-3">
              <Checkbox id={o.id} defaultChecked={o.default} />
              <Label htmlFor={o.id} className="text-sm font-normal cursor-pointer">
                {o.label}
              </Label>
            </div>
          ))}
        </div>

        <DialogFooter className="flex-row gap-2 sm:justify-between">
          <Button
            className="gap-2 bg-primary text-primary-foreground"
            onClick={() => {
              toast.success("Отчёт сформирован");
              onOpenChange(false);
            }}
          >
            <FileText className="h-4 w-4" />
            Сформировать отчёт
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" className="gap-2" onClick={() => toast.info("Скачивание PDF…")}>
              <Download className="h-4 w-4" />
              PDF
            </Button>
            <Button variant="outline" className="gap-2" onClick={() => toast.info("Скачивание PNG…")}>
              <ImageIcon className="h-4 w-4" />
              PNG
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
