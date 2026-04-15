"use client";

import { useEffect, useState } from "react";
import { api, clearSession } from "@/lib/api";
import { Card, Button, Pill } from "@/components/Card";

export default function SettingsPage() {
  const [status, setStatus] = useState<any>(null);
  const [me, setMe] = useState<any>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.status().then(setStatus).catch(() => {});
    api.me.get().then(setMe).catch(() => {});
  }, []);

  async function save() {
    setSaving(true);
    try {
      await api.me.update({
        name: me.name,
        birthdate: me.birthdate,
        sex: me.sex,
        height_cm: me.height_cm,
        weight_kg: me.weight_kg,
        timezone: me.timezone,
        context: me.context,
      });
    } finally {
      setSaving(false);
    }
  }

  if (!me) return <div className="skeleton h-48" />;

  return (
    <div className="space-y-4">
      <Card title="Профиль" action={<Button onClick={save} disabled={saving}>{saving ? "Сохраняю…" : "Сохранить"}</Button>}>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Имя" value={me.name ?? ""} onChange={(v) => setMe({ ...me, name: v })} />
          <Input label="Часовой пояс" value={me.timezone ?? ""} onChange={(v) => setMe({ ...me, timezone: v })} />
          <Input label="Дата рождения" type="date" value={me.birthdate ?? ""} onChange={(v) => setMe({ ...me, birthdate: v })} />
          <Input label="Пол" value={me.sex ?? ""} onChange={(v) => setMe({ ...me, sex: v })} />
          <Input label="Рост, см" type="number" value={me.height_cm ?? ""} onChange={(v) => setMe({ ...me, height_cm: Number(v) })} />
          <Input label="Вес, кг" type="number" value={me.weight_kg ?? ""} onChange={(v) => setMe({ ...me, weight_kg: Number(v) })} />
        </div>
        <label className="mt-3 block">
          <span className="mb-1 block text-xs uppercase tracking-wide text-fg-faint">Контекст</span>
          <textarea
            value={me.context ?? ""}
            onChange={(e) => setMe({ ...me, context: e.target.value })}
            rows={5}
            className="w-full rounded-md border border-border bg-bg-elevated p-3 text-sm outline-none focus:border-accent"
          />
        </label>
      </Card>

      <Card title="Интеграции">
        <ul className="space-y-2 text-sm">
          <Integration label="Anthropic LLM" ok={status?.capabilities?.llm} hint="ANTHROPIC_API_KEY в .env" />
          <Integration label="Oura" ok={status?.capabilities?.oura} hint="OURA_PERSONAL_ACCESS_TOKEN в .env" />
          <Integration label="Telegram" ok={status?.capabilities?.telegram} hint={
            me.telegram_chat_id ? `Привязан chat_id ${me.telegram_chat_id}` : "Настрой TELEGRAM_BOT_TOKEN и отправь /start <PIN>"
          } />
        </ul>
      </Card>

      <Card title="Состояние данных">
        <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
          {Object.entries(status?.counts || {}).map(([k, v]) => (
            <div key={k} className="rounded-md border border-border bg-bg-elevated p-3">
              <div className="text-xs uppercase text-fg-faint">{k}</div>
              <div className="mt-1 text-lg font-semibold">{v as number}</div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Сессия">
        <Button
          variant="danger"
          onClick={() => {
            clearSession();
            window.location.href = "/login";
          }}
        >
          Выйти
        </Button>
      </Card>
    </div>
  );
}

function Input({ label, value, onChange, type = "text" }: { label: string; value: any; onChange: (v: string) => void; type?: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs uppercase tracking-wide text-fg-faint">{label}</span>
      <input
        type={type}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm outline-none focus:border-accent"
      />
    </label>
  );
}

function Integration({ label, ok, hint }: { label: string; ok: boolean; hint: string }) {
  return (
    <li className="flex items-center justify-between rounded-md border border-border bg-bg-elevated p-3">
      <div>
        <span className="font-medium">{label}</span>
        <span className="ml-2 text-xs text-fg-muted">{hint}</span>
      </div>
      <Pill tone={ok ? "ok" : "muted"}>{ok ? "активно" : "выключено"}</Pill>
    </li>
  );
}
