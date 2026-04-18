"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Step = "profile" | "sources" | "done";

export default function Onboarding() {
  const [step, setStep] = useState<Step>("profile");
  const [status, setStatus] = useState<any>(null);
  const [form, setForm] = useState({
    name: "",
    birthdate: "",
    sex: "",
    height_cm: "",
    weight_kg: "",
    context: "",
  });
  const [withingsBusy, setWithingsBusy] = useState(false);
  const [appleBusy, setAppleBusy] = useState(false);
  const [appleResult, setAppleResult] = useState<string>("");
  const [withingsResult, setWithingsResult] = useState<string>("");
  const [withingsConnected, setWithingsConnected] = useState(false);

  useEffect(() => {
    api.status().then(setStatus).catch(() => {});
    api.me
      .get()
      .then((u) => {
        if (!u) return;
        setForm({
          name: u.name ?? "",
          birthdate: u.birthdate ?? "",
          sex: u.sex ?? "",
          height_cm: u.height_cm != null ? String(u.height_cm) : "",
          weight_kg: u.weight_kg != null ? String(u.weight_kg) : "",
          context: u.context ?? "",
        });
      })
      .catch(() => {});
    api.withings
      .status()
      .then((s) => setWithingsConnected(s.connected))
      .catch(() => {});
  }, []);

  async function saveProfile() {
    await api.me.update({
      name: form.name || undefined,
      birthdate: form.birthdate || undefined,
      sex: form.sex || undefined,
      height_cm: form.height_cm ? Number(form.height_cm) : undefined,
      weight_kg: form.weight_kg ? Number(form.weight_kg) : undefined,
      context: form.context || undefined,
    });
    setStep("sources");
  }

  async function importApple(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setAppleBusy(true);
    try {
      await api.sources.appleHealthImport(file);
      setAppleResult("Импорт запущен в фоне. Данные появятся в течение 1-2 минут.");
    } catch (err: any) {
      setAppleResult(`Ошибка: ${err.message}`);
    } finally {
      setAppleBusy(false);
    }
  }

  async function connectWithings() {
    setWithingsBusy(true);
    try {
      const r = await api.withings.connect();
      // Redirect the browser to Withings consent page
      window.location.href = r.authorize_url;
    } catch (err: any) {
      setWithingsResult(`Ошибка: ${err.message}`);
      setWithingsBusy(false);
    }
  }

  return (
    <div className="mx-auto mt-8 max-w-xl">
      <Progress step={step} />

      {step === "profile" && (
        <section className="rounded-xl border border-border bg-bg-card p-6">
          <h1 className="text-xl font-semibold">Пара слов о себе</h1>
          <p className="mt-1 text-sm text-fg-muted">
            Чем точнее контекст, тем полезнее суждения. Всё хранится локально в твоей БД.
          </p>
          <ul className="mt-4 space-y-2 text-sm">
            {[
              ["LLM-агенты", status?.capabilities?.llm],
              ["Withings API", status?.capabilities?.withings],
              ["Telegram бот", status?.capabilities?.telegram],
            ].map(([label, ok]) => (
              <li key={label as string} className="flex items-center gap-2">
                <span
                  className={`inline-block h-2 w-2 rounded-full ${
                    ok ? "bg-ok" : "bg-fg-faint"
                  }`}
                />
                <span className="text-fg-muted">{label as string}</span>
                <span className="text-xs text-fg-faint">{ok ? "настроен" : "выключен"}</span>
              </li>
            ))}
          </ul>
          <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Input label="Имя" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
            <Input
              label="Дата рождения"
              type="date"
              value={form.birthdate}
              onChange={(v) => setForm({ ...form, birthdate: v })}
            />
            <Select
              label="Пол"
              value={form.sex}
              onChange={(v) => setForm({ ...form, sex: v })}
              options={[
                ["", "—"],
                ["M", "М"],
                ["F", "Ж"],
                ["other", "другое"],
              ]}
            />
            <Input
              label="Рост, см"
              type="number"
              value={form.height_cm}
              onChange={(v) => setForm({ ...form, height_cm: v })}
            />
            <Input
              label="Вес, кг"
              type="number"
              value={form.weight_kg}
              onChange={(v) => setForm({ ...form, weight_kg: v })}
            />
          </div>
          <label className="mt-4 block">
            <span className="mb-1 block text-xs uppercase tracking-wide text-fg-faint">
              Контекст (состояния, лекарства, цели)
            </span>
            <textarea
              value={form.context}
              onChange={(e) => setForm({ ...form, context: e.target.value })}
              rows={5}
              placeholder="Например: бросил курить 6 мес назад, принимаю X, цель — снизить ЛПНП, есть семейная история ИБС…"
              className="w-full rounded-md border border-border bg-bg-elevated p-3 text-sm outline-none focus:border-accent"
            />
          </label>
          <div className="mt-6 flex justify-end">
            <button
              onClick={saveProfile}
              className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-bg"
            >
              Сохранить и дальше →
            </button>
          </div>
        </section>
      )}

      {step === "sources" && (
        <section className="space-y-4">
          <div className="rounded-xl border border-border bg-bg-card p-6">
            <h2 className="text-lg font-semibold">Источники данных</h2>
            <p className="mt-1 text-sm text-fg-muted">
              Подключи сколько хочешь. Агенты будут работать и с частичными данными.
            </p>
          </div>

          <SourceCard
            title="Withings (весы, BP, body composition)"
            enabled={!!status?.capabilities?.withings}
            description={
              !status?.capabilities?.withings
                ? "Приложение Withings не настроено владельцем инстанса. Для подключения зарегистрируй приложение на developer.withings.com и добавь WITHINGS_CLIENT_ID/SECRET в .env."
                : withingsConnected
                ? "Аккаунт подключён. Данные синхронизируются автоматически каждые 6 часов."
                : "Подключись через OAuth — откроется страница Withings для разрешения. Забираем вес, АД, body fat, pulse wave velocity, сон."
            }
            actionLabel={
              withingsBusy ? "…" : withingsConnected ? "Подключено ✓" : "Подключить Withings"
            }
            onAction={connectWithings}
            disabled={!status?.capabilities?.withings || withingsBusy || withingsConnected}
            result={withingsResult}
          />

          <div className="rounded-xl border border-border bg-bg-card p-5">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1">
                <h3 className="font-semibold">Apple Health</h3>
                <p className="mt-1 text-sm text-fg-muted">
                  iPhone → Health → профиль → Export All Health Data → export.zip. Загрузи сюда.
                  Парсим стриминг — файл в сотни мегабайт не проблема.
                </p>
                {appleResult && (
                  <div className="mt-2 text-xs text-fg-muted">{appleResult}</div>
                )}
              </div>
              <label className="cursor-pointer">
                <span className="rounded-md bg-bg-elevated px-3 py-2 text-sm hover:bg-border/60">
                  {appleBusy ? "Загружаю…" : "Загрузить .zip"}
                </span>
                <input
                  type="file"
                  className="hidden"
                  accept=".zip,.xml"
                  disabled={appleBusy}
                  onChange={importApple}
                />
              </label>
            </div>
          </div>

          <div className="flex justify-between">
            <button
              onClick={() => setStep("profile")}
              className="rounded-md border border-border px-4 py-2 text-sm text-fg-muted hover:text-fg"
            >
              ← Назад
            </button>
            <button
              onClick={() => (window.location.href = "/")}
              className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-bg"
            >
              Готово — открыть дашборд →
            </button>
          </div>
        </section>
      )}
    </div>
  );
}

function Progress({ step }: { step: Step }) {
  const idx = { profile: 0, sources: 1, done: 2 }[step];
  const steps = ["Профиль", "Данные"];
  return (
    <div className="mb-6 flex items-center gap-3">
      {steps.map((label, i) => (
        <div key={label} className="flex flex-1 items-center gap-2">
          <div
            className={`flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
              i <= idx ? "bg-accent text-bg" : "bg-bg-elevated text-fg-faint"
            }`}
          >
            {i + 1}
          </div>
          <span className={`text-xs ${i <= idx ? "text-fg" : "text-fg-faint"}`}>{label}</span>
          {i < steps.length - 1 && (
            <div className={`h-px flex-1 ${i < idx ? "bg-accent/40" : "bg-border"}`} />
          )}
        </div>
      ))}
    </div>
  );
}

function Input({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs uppercase tracking-wide text-fg-faint">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm outline-none focus:border-accent"
      />
    </label>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs uppercase tracking-wide text-fg-faint">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm outline-none focus:border-accent"
      >
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </label>
  );
}

function SourceCard({
  title,
  description,
  enabled,
  actionLabel,
  onAction,
  disabled,
  result,
}: {
  title: string;
  description: string;
  enabled: boolean;
  actionLabel: string;
  onAction: () => void;
  disabled?: boolean;
  result?: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-bg-card p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold">{title}</h3>
            <span
              className={`inline-block h-2 w-2 rounded-full ${enabled ? "bg-ok" : "bg-fg-faint"}`}
            />
          </div>
          <p className="mt-1 text-sm text-fg-muted">{description}</p>
          {result && <div className="mt-2 text-xs text-fg-muted">{result}</div>}
        </div>
        <button
          onClick={onAction}
          disabled={disabled}
          className="rounded-md bg-bg-elevated px-3 py-2 text-sm hover:bg-border/60 disabled:opacity-50"
        >
          {actionLabel}
        </button>
      </div>
    </div>
  );
}
