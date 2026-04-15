"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, hasSession } from "@/lib/api";
import { Card, Stat, Pill, Empty, Button } from "@/components/Card";
import { Sparkline } from "@/components/Sparkline";

export default function Dashboard() {
  const [status, setStatus] = useState<any>(null);
  const [brief, setBrief] = useState<any>(null);
  const [metrics, setMetrics] = useState<any>(null);
  const [tasks, setTasks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!hasSession()) {
      window.location.href = "/login";
      return;
    }
    loadAll();
  }, []);

  async function loadAll() {
    setLoading(true);
    try {
      const [st, br, mt, tk] = await Promise.all([
        api.status(),
        api.reports.briefLatest().catch(() => null),
        api.metrics(14).catch(() => null),
        api.tasks.list("open").catch(() => []),
      ]);
      setStatus(st);
      setBrief(br);
      setMetrics(mt);
      setTasks(tk);

      if (!st.user_onboarded) {
        window.location.href = "/onboarding";
      }
    } finally {
      setLoading(false);
    }
  }

  async function generateBrief() {
    setBusy(true);
    try {
      const b = await api.reports.briefGenerate();
      setBrief(b);
    } catch (e: any) {
      alert("Не удалось сгенерировать бриф: " + e.message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="skeleton h-32 w-full" />
        <div className="grid gap-4 md:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="skeleton h-24" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Brief */}
      <Card
        title={
          <span className="flex items-center gap-2">
            Утренний бриф
            {brief && <Pill tone="muted">{new Date(brief.created_at).toLocaleString("ru-RU")}</Pill>}
          </span>
        }
        action={
          <Button variant="ghost" onClick={generateBrief} disabled={busy || !status?.capabilities?.llm}>
            {busy ? "Генерирую…" : brief ? "Обновить" : "Сгенерировать"}
          </Button>
        }
      >
        {brief ? (
          <>
            <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-fg">{brief.text}</p>
            {brief.highlights?.length > 0 && (
              <ul className="mt-4 space-y-1">
                {brief.highlights.map((h: string, i: number) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-fg-muted">
                    <span className="mt-1 h-1 w-1 flex-shrink-0 rounded-full bg-accent" />
                    {h}
                  </li>
                ))}
              </ul>
            )}
            {brief.lifestyle_flags && Object.keys(brief.lifestyle_flags).length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2">
                {Object.entries(brief.lifestyle_flags).map(([agent, flags]: [string, any]) =>
                  (flags as string[]).map((f, i) => (
                    <Pill key={`${agent}-${i}`} tone="warn">
                      {agent}: {f}
                    </Pill>
                  )),
                )}
              </div>
            )}
          </>
        ) : (
          <Empty
            title={status?.capabilities?.llm ? "Брифа ещё нет" : "LLM не подключён"}
            hint={
              status?.capabilities?.llm
                ? "Нажми «Сгенерировать» — GP-агент прочитает данные за последние сутки."
                : "Укажи ANTHROPIC_API_KEY в .env и перезапусти стек, чтобы активировать агентов."
            }
          />
        )}
      </Card>

      {/* Metric grid */}
      <div className="grid gap-4 md:grid-cols-4">
        <MetricCard kind="resting_hr" label="RHR" unit="bpm" metrics={metrics} />
        <MetricCard kind="hrv_rmssd_night" label="HRV" unit="ms" metrics={metrics} />
        <MetricCard kind="sleep_duration" label="Сон" unit="ч" metrics={metrics} format={(v) => (v / 3600).toFixed(1)} />
        <MetricCard kind="steps" label="Шаги" unit="" metrics={metrics} />
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        {/* Tasks */}
        <Card
          title="Открытые задачи"
          action={<Link href="/tasks" className="text-xs text-accent hover:underline">Все →</Link>}
        >
          {tasks.length === 0 ? (
            <Empty title="Пока нет" hint="Задачи появятся после MDT-консилиума или из чек-инов." />
          ) : (
            <ul className="space-y-2">
              {tasks.slice(0, 5).map((t) => (
                <li key={t.id} className="flex items-start gap-3 rounded-lg border border-border bg-bg-elevated p-3">
                  <PriorityDot priority={t.priority} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-fg">{t.title}</div>
                    {t.detail && (
                      <div className="mt-0.5 truncate text-xs text-fg-muted">{t.detail}</div>
                    )}
                    <div className="mt-1 flex items-center gap-2 text-[11px] text-fg-faint">
                      <span>{t.created_by}</span>
                      <span>·</span>
                      <span>{t.age_days}д</span>
                      {t.due && (
                        <>
                          <span>·</span>
                          <span>до {t.due}</span>
                        </>
                      )}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* MDT team card */}
        <Card title="MDT-команда" action={<Link href="/reports" className="text-xs text-accent hover:underline">Отчёты →</Link>}>
          <ul className="grid grid-cols-2 gap-2 text-sm">
            {[
              { name: "Кардиолог", role: "specialist" },
              { name: "Эндокринолог", role: "specialist" },
              { name: "Нутрициолог", role: "specialist" },
              { name: "Психиатр", role: "specialist" },
              { name: "Sleep", role: "lifestyle" },
              { name: "Movement", role: "lifestyle" },
              { name: "Stress/HRV", role: "lifestyle" },
              { name: "Recovery", role: "lifestyle" },
            ].map((a) => (
              <li
                key={a.name}
                className="flex items-center gap-2 rounded-md border border-border bg-bg-elevated px-3 py-2"
              >
                <span
                  className={`h-2 w-2 rounded-full ${
                    a.role === "specialist" ? "bg-accent" : "bg-ok"
                  }`}
                />
                <span className="text-fg-muted">{a.name}</span>
              </li>
            ))}
          </ul>
          <div className="mt-4 rounded-md border border-border bg-bg-elevated p-3 text-xs text-fg-muted">
            <span className="text-fg">GP-координатор</span> синтезирует ноты в SOAP-отчёт,
            ведёт список проблем, формулирует safety net.
          </div>
        </Card>
      </div>
    </div>
  );
}

function MetricCard({
  kind,
  label,
  unit,
  metrics,
  format,
}: {
  kind: string;
  label: string;
  unit: string;
  metrics: any;
  format?: (v: number) => string;
}) {
  const series = metrics?.series?.[kind] || [];
  const values = series.map((p: any) => p.value);
  const latest = values[values.length - 1];
  const baseline = values.length > 3 ? values.slice(0, -3).reduce((a: number, b: number) => a + b, 0) / Math.max(1, values.length - 3) : undefined;

  const displayed = latest != null ? (format ? format(latest) : Math.round(latest).toString()) : "—";

  let trend: "up" | "down" | "flat" | undefined;
  let hint: string | undefined;
  if (latest != null && baseline != null && baseline > 0) {
    const delta = ((latest - baseline) / baseline) * 100;
    if (Math.abs(delta) > 2) {
      trend = delta > 0 ? "up" : "down";
      hint = `${delta > 0 ? "+" : ""}${delta.toFixed(1)}% к базе`;
    } else {
      hint = "в норме";
    }
  }

  return (
    <div className="rounded-xl border border-border bg-bg-card p-4">
      <div className="flex items-end justify-between">
        <Stat label={label} value={<>{displayed}{unit && <span className="text-sm font-normal text-fg-muted"> {unit}</span>}</>} hint={hint} trend={trend} />
        <Sparkline points={values} baseline={baseline} />
      </div>
    </div>
  );
}

function PriorityDot({ priority }: { priority: string }) {
  const color = { urgent: "bg-danger", normal: "bg-warn", low: "bg-fg-faint" }[priority] || "bg-warn";
  return <span className={`mt-1.5 h-2 w-2 flex-shrink-0 rounded-full ${color}`} />;
}
