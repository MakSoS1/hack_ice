import { LayerDef, Vessel } from "./vizard-types";

export const LAYER_GROUPS: { id: string; label: string; layers: LayerDef[] }[] = [
  {
    id: "ships",
    label: "Суда",
    layers: [
      { id: "ship-positions", group: "ships", label: "Положение судов", status: "current", swatch: "bg-accent-blue" },
      { id: "ship-tracks", group: "ships", label: "Треки", status: "current", swatch: "bg-status-current" },
      { id: "ports", group: "ships", label: "Порты", status: "current", swatch: "bg-primary" },
    ],
  },
  {
    id: "meteo",
    label: "Метео",
    layers: [
      { id: "temperature", group: "meteo", label: "Температура", status: "forecast", swatch: "bg-status-forecast" },
      { id: "pressure", group: "meteo", label: "Давление", status: "forecast", swatch: "bg-status-forecast" },
      { id: "wind", group: "meteo", label: "Ветер", status: "current", swatch: "bg-accent-blue" },
      { id: "currents", group: "meteo", label: "Течения", status: "current", swatch: "bg-map-water-deep" },
      { id: "clouds", group: "meteo", label: "Облачность", status: "nodata", swatch: "bg-status-nodata" },
    ],
  },
  {
    id: "ice",
    label: "Лёд",
    layers: [
      {
        id: "ice-concentration",
        group: "ice",
        label: "Сплоченность льда",
        status: "current",
        swatch: "bg-map-ice-high",
        source: "Composite (AMSR2 + Sentinel-1)",
        updated: "16 декабря 2023, 18:00 UTC+3",
        type: "Растровый, GeoTIFF",
        coverage: "68%",
        confidence: "Высокая",
        description:
          "Слой сплоченности морского льда по композитной продукции на основе спутниковых наблюдений. Значения от 0 до 100%.",
      },
      { id: "ice-cover", group: "ice", label: "Ледяной покров", status: "current", swatch: "bg-map-ice-mid" },
      { id: "snow-cover", group: "ice", label: "Снежный покров", status: "forecast", swatch: "bg-map-ice-low" },
      { id: "ice-drift", group: "ice", label: "Дрейф льда", status: "current", swatch: "bg-accent-blue" },
      { id: "ice-conditions", group: "ice", label: "Ледовые условия", status: "forecast", swatch: "bg-status-forecast" },
    ],
  },
  {
    id: "ai",
    label: "AI",
    layers: [
      { id: "ai-gaps", group: "ai", label: "Пропуски данных", status: "nodata", swatch: "bg-status-nodata" },
      { id: "ai-reconstructed", group: "ai", label: "Восстановленная карта", status: "ai", swatch: "bg-status-ai" },
      { id: "ai-confidence", group: "ai", label: "Карта уверенности", status: "ai", swatch: "bg-status-ai" },
      { id: "ai-diff", group: "ai", label: "Разница с наблюдением", status: "ai", swatch: "bg-status-ai" },
    ],
  },
  {
    id: "tools",
    label: "Инструменты",
    layers: [
      { id: "tool-ruler", group: "tools", label: "Линейка", status: "current" },
      { id: "tool-area", group: "tools", label: "Площадь", status: "current" },
      { id: "tool-grid", group: "tools", label: "Координатная сетка", status: "current" },
      { id: "tool-snapshot", group: "tools", label: "Снимок карты", status: "current" },
    ],
  },
];

export const DEFAULT_ENABLED_LAYERS = new Set<string>([
  "ship-positions",
  "ship-tracks",
  "ice-concentration",
  "tool-grid",
]);

export const VESSELS: Vessel[] = [
  {
    id: "v1",
    name: "Капитан Драницын",
    callsign: "UFAQ",
    imo: "7625984",
    mmsi: "273312000",
    course: 47,
    speed: 8.4,
    lat: 76.812,
    lon: 65.214,
    lastFix: "16.12.2023, 20:42 UTC+3",
    iceClass: "Arc7",
    x: 0.42,
    y: 0.46,
  },
  {
    id: "v2",
    name: "Ямал",
    callsign: "UDNB",
    imo: "9077549",
    mmsi: "273215100",
    course: 92,
    speed: 12.1,
    lat: 78.341,
    lon: 71.502,
    lastFix: "16.12.2023, 20:50 UTC+3",
    iceClass: "Arc9 (атомный)",
    x: 0.55,
    y: 0.34,
  },
  {
    id: "v3",
    name: "50 лет Победы",
    callsign: "UBHJ",
    imo: "9152959",
    mmsi: "273456900",
    course: 311,
    speed: 14.2,
    lat: 79.124,
    lon: 58.741,
    lastFix: "16.12.2023, 20:55 UTC+3",
    iceClass: "Arc9 (атомный)",
    x: 0.34,
    y: 0.28,
  },
  {
    id: "v4",
    name: "Норильский никель",
    callsign: "UEAH",
    imo: "9334732",
    mmsi: "273512040",
    course: 218,
    speed: 9.8,
    lat: 75.423,
    lon: 81.612,
    lastFix: "16.12.2023, 20:38 UTC+3",
    iceClass: "Arc7",
    x: 0.68,
    y: 0.58,
  },
];

export const PORTS = [
  { id: "dudinka", name: "Дудинка", x: 0.78, y: 0.74 },
  { id: "dikson", name: "Диксон", x: 0.62, y: 0.66 },
  { id: "sabetta", name: "Сабетта", x: 0.46, y: 0.62 },
];

export interface TimelineSegment {
  hour: number; // 0..47
  status: "observation" | "reconstruction" | "forecast" | "nodata" | "lowconf";
}

export const TIMELINE: TimelineSegment[] = Array.from({ length: 48 }, (_, i) => {
  // Build a realistic mix
  if (i < 14) return { hour: i, status: "observation" };
  if (i < 18) return { hour: i, status: "nodata" };
  if (i < 24) return { hour: i, status: "reconstruction" };
  if (i < 28) return { hour: i, status: "lowconf" };
  if (i < 36) return { hour: i, status: "observation" };
  return { hour: i, status: "forecast" };
});

export const TIMELINE_LEGEND: { id: TimelineSegment["status"]; label: string; cls: string }[] = [
  { id: "observation", label: "Наблюдения", cls: "bg-status-current" },
  { id: "reconstruction", label: "Восстановление", cls: "bg-status-ai" },
  { id: "forecast", label: "Прогноз", cls: "bg-status-forecast" },
  { id: "nodata", label: "Нет данных", cls: "bg-status-nodata" },
  { id: "lowconf", label: "Низкая уверенность", cls: "bg-status-error" },
];
