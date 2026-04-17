
# VIZARD — Arctic Ice Monitoring Platform

A high-fidelity, map-first web GIS prototype for maritime/Arctic operations. Russian UI throughout, light professional theme, structured panels over a stylized Arctic basemap.

## Design system

- **Theme:** light, gray-blue chrome (`#F4F6F9` chrome, `#FFFFFF` panels, `#0E2A47` deep navy for primary text/brand, `#1E5AA8` accent blue, soft `#E5EAF1` borders).
- **Status palette (paired with icon + label, never color-only):** green `#2F8F5A` "Актуально", amber `#C9852B` "Прогноз", violet `#6E4FB3` "AI", neutral gray `#7A8597` "Нет данных", red `#B5371F` "Ошибка/Низкая уверенность".
- **Typography:** Inter (headings + UI), JetBrains Mono for coordinates/IDs. Strong contrast, 14px base, 12px secondary.
- **Shape:** 8px radius panels, soft single-layer shadows, 1px hairline borders.
- **Accessibility:** every status has icon + text; focus rings on all interactive elements; tooltips on compact controls; min 36px hit targets.

## Layout (persistent shell)

1. **Top app bar (56px):** VIZARD wordmark + ice glyph · nav tabs (Оперативная обстановка / AI-восстановление / Маршрутизация / Суда / Отчёты) · center cluster: Дата и время picker, chips "Источник: Composite", "Покрытие: 68%", "Уверенность: высокая" · right: notifications, user menu (Профиль / Настройки / Выход).
2. **Left sidebar (collapsible, 280px → 56px mini):** 5 grouped sections (Суда, Метео, Лёд, AI, Инструменты) as accordions. Each row: toggle switch · label · tiny legend swatch · status chip · settings cog. Search field at top of sidebar.
3. **Map canvas (center, dominates):** stylized Arctic basemap (SVG — coastline of Novaya Zemlya, Kara Sea, Severnaya Zemlya, simplified bathymetry). Overlays mocked as semi-transparent SVG patches (ice concentration gradient, AI-reconstructed regions with hatched pattern, confidence heatmap, vessel markers, route polyline).
   - Top-left: search bar "Поиск по IMO, MMSI, позывному, координатам".
   - Bottom-left: scale bar + north indicator.
   - Bottom-right: compact controls cluster (text+icon): +, −, Сброс, Сетка, Линейка, Маршрут, Отчёт.
4. **Right inspector (360px, contextual):** swaps based on mode A/B/C/D.
5. **Bottom strip (fixed, ~180px):**
   - Summary row (4 cards): Покрытие данных 68%→96%, Пропуски закрыты 2 430 км², Зоны низкой уверенности 2, Влияние на маршрут — Среднее. Plus inline change tags: "Новые зоны риска", "Маршрут требует пересчёта", "Низкая уверенность в 2 участках".
   - Timeline "Шкала времени и доступности данных": horizontal track with labeled segments (Наблюдения / Восстановление / Прогноз / Нет данных / Низкая уверенность), each as a distinct pattern + color, hourly ticks, scrubber, hover tooltip with timestamp/source/status/confidence, legend on right.

## Screens / states to deliver

1. **Главный экран — Оперативная обстановка** (Mode A inspector): selected ice concentration layer info (Название, Источник, Время обновления, Тип данных, Покрытие, Уверенность, Описание + actions Показать легенду / Скачать GeoTIFF / Скачать PNG / Скопировать ссылку).
2. **AI-восстановление** (Mode B): area selection (Выделить область / Использовать видимый экстент), параметры (Дата, Историческое окно, Режим модели), primary CTA "Заполнить пропуски", result block (Было 68% / Стало 96% / Восстановлено 28% / Уверенность 0.87), segmented control "Наблюдение / Восстановление / Уверенность / Разница" — map overlay updates accordingly. Includes "Восстановление выполняется…" progress state.
3. **Маршрутизация** (Mode C): Точка А / Точка Б / Класс судна / Осадка / Ограничения, buttons Построить / Очистить, result cards Основной маршрут, Альтернативный маршрут, Риск по льду, Доля AI-участков, Ожидаемое время, Длина маршрута. Map shows two route polylines with risk-coded segments.
4. **Карточка судна** (Mode D): name, позывной, IMO, MMSI, курс, скорость, координаты, последняя фиксация. Buttons Показать трек / Построить маршрут до судна / Сформировать сводку. Track range segmented "12 ч / 24 ч / 48 ч". Map shows track polyline.
5. **Модал «Сформировать отчёт»**: checkboxes (Текущий вид карты, Выбранные слои, Добавить легенду / координатную сетку / шкалу / сводку AI), buttons Сформировать отчёт / Скачать PDF / Скачать PNG.
6. **Экран «Настройки»** (separate route `/settings`): sections — Профиль, Единицы измерения (морские мили/км, узлы/км·ч), Часовой пояс, Источники данных по умолчанию, Уведомления, Доступ и API-ключи, Внешний вид (плотность интерфейса).

## Interaction & state coverage

- Mode switching via top nav + map selection drives right inspector content.
- Layer toggles update overlays on stylized map.
- Timeline scrubber updates the global Дата и время chip and a small "Слой обновлён" toast.
- Loading toasts/banners: "Загрузка данных…", "Расчёт маршрута…", "Восстановление выполняется…", "Слой обновлён", "Нет данных за выбранный интервал", "Ошибка обработки. Повторите попытку."
- Empty states in inspector: "Выберите слой слева…", "Нет активного маршрута.", "Выделите область на карте…", "Судно не выбрано."

## Implementation approach

- **Routing:** `/` operational view (default Mode A), `/ai` (Mode B), `/routing` (Mode C), `/vessels` (vessel list + Mode D on select), `/reports` (opens modal + history list), `/settings`.
- **Components:** TopBar, LeftSidebar with LayerGroup/LayerRow, MapCanvas (SVG-based stylized Arctic map with overlay slots), MapControls, MapSearch, RightInspector with sub-panels (LayerInfoPanel, AIReconstructionPanel, RoutingPanel, VesselPanel, EmptyPanel), BottomStrip (SummaryCards + Timeline + Legend), ReportModal, SettingsPage.
- **Mock data:** vessels (e.g. «Капитан Драницын», «Ямал», «50 лет Победы»), Arctic coordinates, layer metadata, timeline segments, AI reconstruction stats — all realistic Russian dummy values.
- **Tech:** React + Tailwind + shadcn/ui (Tabs, Accordion, Switch, Popover for date picker, Dialog for report, Tooltip, Select, Slider for timeline scrubber, Toast via sonner). lucide-react icons paired with text. Light theme tokens defined in `index.css` (HSL).
- **Stylized map:** hand-built SVG with coastline paths, graticule, ice concentration gradient patches, hatched AI regions, confidence heatmap layer, vessel pins, route polylines — all toggleable via sidebar state.

Deliverable: a single cohesive prototype that boots into the Operational view and lets the reviewer click through all 6 states.
