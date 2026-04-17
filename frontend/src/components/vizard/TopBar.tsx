import { useNavigate, useLocation } from "react-router-dom";
import { Snowflake, Calendar, MoreHorizontal, Ship, FileText, Settings, User, ChevronDown, Map, Sparkles, Route } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar as CalendarComp } from "@/components/ui/calendar";
import { useState } from "react";
import { format } from "date-fns";
import { ru } from "date-fns/locale";
import { cn } from "@/lib/utils";
import { useBreakpoint } from "@/hooks/use-mobile";

const MAIN_NAV = [
  { id: "ops", label: "Карта", path: "/", icon: Map },
  { id: "ai", label: "AI", path: "/ai", icon: Sparkles },
  { id: "routing", label: "Маршрут", path: "/routing", icon: Route },
];

const OVERFLOW_NAV = [
  { id: "vessels", label: "Суда", path: "/vessels", icon: Ship },
  { id: "reports", label: "Отчёты", path: "/reports", icon: FileText },
  { id: "settings", label: "Настройки", path: "/settings", icon: Settings },
];

export function TopBar() {
  const nav = useNavigate();
  const loc = useLocation();
  const [date, setDate] = useState<Date>(new Date(2023, 11, 16, 21, 0));
  const { isMobile } = useBreakpoint();

  if (isMobile) {
    return (
      <header className="h-11 shrink-0 bg-card border-b border-border flex items-center px-2 gap-1 pt-safe">
        <button
          onClick={() => nav("/")}
          className="flex items-center gap-1 h-8 px-1.5"
          aria-label="VIZARD главная"
        >
          <div className="h-6 w-6 rounded bg-primary text-primary-foreground flex items-center justify-center">
            <Snowflake className="h-3.5 w-3.5" />
          </div>
        </button>

        <div className="flex items-center gap-0.5 mx-1">
          {MAIN_NAV.map((n) => {
            const active = loc.pathname === n.path;
            return (
              <button
                key={n.id}
                onClick={() => nav(n.path)}
                className={cn(
                  "h-8 px-2 rounded text-xs font-medium transition-colors",
                  active
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted",
                )}
              >
                {n.label}
              </button>
            );
          })}
        </div>

        <div className="ml-auto flex items-center gap-1">
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="ghost" size="sm" className="h-8 gap-1 font-normal px-2">
                <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="font-mono text-[11px]">{format(date, "dd.MM HH:mm", { locale: ru })}</span>
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="end">
              <CalendarComp
                mode="single"
                selected={date}
                onSelect={(d) => d && setDate(d)}
                locale={ru}
                className="p-3 pointer-events-auto"
              />
            </PopoverContent>
          </Popover>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              {OVERFLOW_NAV.map((n) => (
                <DropdownMenuItem key={n.id} onClick={() => nav(n.path)}>
                  <n.icon className="h-4 w-4 mr-2" />
                  {n.label}
                </DropdownMenuItem>
              ))}
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => nav("/profile")}>
                <User className="h-4 w-4 mr-2" />
                Профиль
              </DropdownMenuItem>
              <DropdownMenuItem className="text-destructive focus:text-destructive">Выход</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>
    );
  }

  return (
    <header className="h-12 shrink-0 bg-card border-b border-border flex items-center px-3 md:px-4 gap-2 md:gap-3">
      <button
        onClick={() => nav("/")}
        className="flex items-center gap-1.5 pr-2 md:pr-3 border-r border-border h-8"
        aria-label="VIZARD главная"
      >
        <div className="h-6 w-6 rounded bg-primary text-primary-foreground flex items-center justify-center">
          <Snowflake className="h-3.5 w-3.5" />
        </div>
        <span className="font-semibold tracking-wider text-primary text-sm hidden sm:inline">VIZARD</span>
      </button>

      <nav className="flex items-center gap-0.5">
        {MAIN_NAV.map((n) => {
          const active = loc.pathname === n.path;
          return (
            <button
              key={n.id}
              onClick={() => nav(n.path)}
              className={cn(
                "h-8 px-2.5 md:px-3 rounded text-sm font-medium transition-colors",
                active
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted",
              )}
            >
              {n.label}
            </button>
          );
        })}

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-8 w-8 hidden lg:flex">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-44">
            {OVERFLOW_NAV.map((n) => (
              <DropdownMenuItem key={n.id} onClick={() => nav(n.path)}>
                <n.icon className="h-4 w-4 mr-2" />
                {n.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </nav>

      <div className="ml-auto flex items-center gap-2">
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm" className="h-8 gap-1.5 font-normal">
              <Calendar className="h-3.5 w-3.5" />
              <span className="font-mono text-xs hidden md:inline">{format(date, "dd.MM.yyyy HH:mm", { locale: ru })}</span>
              <span className="font-mono text-xs md:hidden">{format(date, "dd.MM HH:mm", { locale: ru })}</span>
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="end">
            <CalendarComp
              mode="single"
              selected={date}
              onSelect={(d) => d && setDate(d)}
              locale={ru}
              className="p-3 pointer-events-auto"
            />
          </PopoverContent>
        </Popover>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="h-8 gap-1.5 pl-1">
              <div className="h-6 w-6 rounded-full bg-accent-blue text-accent-blue-foreground flex items-center justify-center text-xs font-medium">
                ИП
              </div>
              <span className="text-sm hidden md:inline">И. Петров</span>
              <ChevronDown className="h-3 w-3 opacity-60" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-44">
            <DropdownMenuItem onClick={() => nav("/profile")}>
              <User className="h-4 w-4 mr-2" />
              Профиль
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => nav("/settings")}>Настройки</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="text-destructive focus:text-destructive">Выход</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
