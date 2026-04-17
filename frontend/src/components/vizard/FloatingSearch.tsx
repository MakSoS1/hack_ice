import { useNavigate } from "react-router-dom";
import { Snowflake, Search, Calendar } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar as CalendarComp } from "@/components/ui/calendar";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { User, Settings, Ship, FileText } from "lucide-react";
import { useState } from "react";
import { format } from "date-fns";
import { ru } from "date-fns/locale";
import { Input } from "@/components/ui/input";
import { useBreakpoint } from "@/hooks/use-mobile";
import { cn } from "@/lib/utils";

const OVERFLOW = [
  { id: "vessels", label: "Суда", path: "/vessels", icon: Ship },
  { id: "reports", label: "Отчёты", path: "/reports", icon: FileText },
  { id: "settings", label: "Настройки", path: "/settings", icon: Settings },
];

export function FloatingSearch() {
  const nav = useNavigate();
  const [date, setDate] = useState<Date>(new Date(2023, 11, 16, 21, 0));
  const { isMobile } = useBreakpoint();

  return (
    <div className={cn(
      "absolute z-30 pointer-events-auto flex items-center gap-2",
      isMobile
        ? "top-2 left-2 right-2"
        : "top-3 left-3 right-3"
    )}>
      <div className={cn(
        "bg-card/95 backdrop-blur-sm rounded-xl shadow-lg border border-border/50 flex items-center gap-2 pl-3 pr-1.5",
        isMobile ? "h-10 flex-1" : "h-11 w-full max-w-[560px]"
      )}>
        <button onClick={() => nav("/")} aria-label="VIZARD" className="flex items-center gap-1.5 shrink-0">
          <div className="h-6 w-6 rounded-md bg-primary text-primary-foreground flex items-center justify-center">
            <Snowflake className="h-3.5 w-3.5" />
          </div>
          {!isMobile && <span className="font-semibold text-primary text-sm">VIZARD</span>}
        </button>

        <div className="h-5 w-px bg-border shrink-0" />

        <div className="flex-1 relative">
          <Search className="absolute left-0 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder={isMobile ? "Поиск…" : "Поиск по IMO, MMSI, координатам…"}
            className="border-0 bg-transparent h-full pl-5 text-sm focus-visible:ring-0 focus-visible:ring-offset-0 placeholder:text-muted-foreground/60"
          />
        </div>

        <Popover>
          <PopoverTrigger asChild>
            <button className="h-7 px-2 rounded-lg text-xs text-muted-foreground hover:bg-muted transition-colors font-mono shrink-0">
              {isMobile ? format(date, "dd.MM HH:mm", { locale: ru }) : format(date, "dd.MM.yyyy HH:mm", { locale: ru })}
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="end">
            <CalendarComp mode="single" selected={date} onSelect={(d) => d && setDate(d)} locale={ru} className="p-3 pointer-events-auto" />
          </PopoverContent>
        </Popover>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7 rounded-lg shrink-0">
              <User className="h-3.5 w-3.5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-44">
            {OVERFLOW.map((n) => (
              <DropdownMenuItem key={n.id} onClick={() => nav(n.path)}>
                <n.icon className="h-4 w-4 mr-2" />{n.label}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => nav("/profile")}>
              <User className="h-4 w-4 mr-2" />Профиль
            </DropdownMenuItem>
            <DropdownMenuItem className="text-destructive focus:text-destructive">Выход</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}

