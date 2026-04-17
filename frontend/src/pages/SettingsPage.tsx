import { useNavigate } from "react-router-dom";
import { TopBar } from "@/components/vizard/TopBar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ArrowLeft, User, Ruler, Globe2, Database, Bell, KeyRound, Layout } from "lucide-react";

const SECTIONS = [
  { id: "profile", label: "Профиль", icon: User },
  { id: "units", label: "Единицы измерения", icon: Ruler },
  { id: "timezone", label: "Часовой пояс", icon: Globe2 },
  { id: "sources", label: "Источники данных", icon: Database },
  { id: "notifications", label: "Уведомления", icon: Bell },
  { id: "api", label: "Доступ и API-ключи", icon: KeyRound },
  { id: "appearance", label: "Внешний вид", icon: Layout },
];

const SettingsPage = () => {
  const nav = useNavigate();
  return (
    <div className="h-screen w-screen flex flex-col bg-chrome overflow-hidden">
      <TopBar />
      <div className="flex-1 flex overflow-hidden">
        <aside className="w-64 shrink-0 bg-card border-r border-border p-3">
          <Button variant="ghost" size="sm" className="gap-2 mb-3" onClick={() => nav("/")}>
            <ArrowLeft className="h-4 w-4" />
            Назад к карте
          </Button>
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground px-2 mb-2">
            Настройки
          </div>
          <nav className="space-y-0.5">
            {SECTIONS.map((s) => (
              <a
                key={s.id}
                href={`#${s.id}`}
                className="flex items-center gap-2 px-2 py-1.5 rounded text-sm text-foreground hover:bg-muted"
              >
                <s.icon className="h-4 w-4 text-muted-foreground" />
                {s.label}
              </a>
            ))}
          </nav>
        </aside>

        <main className="flex-1 overflow-y-auto">
          <div className="max-w-3xl mx-auto px-8 py-8 space-y-8">
            <div>
              <h1 className="text-2xl font-semibold text-foreground">Настройки</h1>
              <p className="text-sm text-muted-foreground mt-1">
                Параметры вашего рабочего пространства и платформы.
              </p>
            </div>

            <Section id="profile" title="Профиль">
              <div className="grid grid-cols-2 gap-4">
                <Field label="Имя">
                  <Input defaultValue="Иван Петров" />
                </Field>
                <Field label="Должность">
                  <Input defaultValue="Старший ледовый аналитик" />
                </Field>
                <Field label="Email">
                  <Input defaultValue="i.petrov@vizard.ru" type="email" className="font-mono" />
                </Field>
                <Field label="Телефон">
                  <Input defaultValue="+7 921 555-12-34" className="font-mono" />
                </Field>
              </div>
            </Section>

            <Section id="units" title="Единицы измерения">
              <div className="grid grid-cols-2 gap-4">
                <Field label="Расстояние">
                  <Select defaultValue="nm">
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="nm">Морские мили</SelectItem>
                      <SelectItem value="km">Километры</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
                <Field label="Скорость">
                  <Select defaultValue="kn">
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="kn">Узлы</SelectItem>
                      <SelectItem value="kmh">км/ч</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
              </div>
            </Section>

            <Section id="timezone" title="Часовой пояс">
              <Field label="Часовой пояс">
                <Select defaultValue="msk">
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="utc">UTC</SelectItem>
                    <SelectItem value="msk">Москва (UTC+3)</SelectItem>
                    <SelectItem value="krasnoyarsk">Красноярск (UTC+7)</SelectItem>
                    <SelectItem value="vladivostok">Владивосток (UTC+10)</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
            </Section>

            <Section id="sources" title="Источники данных по умолчанию">
              <div className="space-y-3">
                {["Composite (рекомендовано)", "AMSR2", "Sentinel-1", "IceClass"].map((s, i) => (
                  <div key={s} className="flex items-center justify-between py-1">
                    <Label className="font-normal">{s}</Label>
                    <Switch defaultChecked={i < 2} />
                  </div>
                ))}
              </div>
            </Section>

            <Section id="notifications" title="Уведомления">
              <div className="space-y-3">
                {["Новые зоны риска", "Обновление слоёв", "Завершение AI-восстановления", "Изменения маршрута"].map((s, i) => (
                  <div key={s} className="flex items-center justify-between py-1">
                    <Label className="font-normal">{s}</Label>
                    <Switch defaultChecked={i !== 1} />
                  </div>
                ))}
              </div>
            </Section>

            <Section id="api" title="Доступ и API-ключи">
              <Field label="API-ключ">
                <div className="flex gap-2">
                  <Input defaultValue="vzd_live_4f8a9c1d3e7b2a5f6h" className="font-mono" readOnly />
                  <Button variant="outline">Перевыпустить</Button>
                </div>
              </Field>
            </Section>

            <Section id="appearance" title="Внешний вид">
              <Field label="Плотность интерфейса">
                <Select defaultValue="comfortable">
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="compact">Компактная</SelectItem>
                    <SelectItem value="comfortable">Комфортная</SelectItem>
                    <SelectItem value="spacious">Просторная</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
            </Section>

            <div className="flex justify-end gap-2 pb-8">
              <Button variant="outline">Отмена</Button>
              <Button className="bg-primary text-primary-foreground">Сохранить изменения</Button>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
};

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="panel p-6">
      <h2 className="text-base font-semibold text-foreground mb-4">{title}</h2>
      {children}
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {children}
    </div>
  );
}

export default SettingsPage;
