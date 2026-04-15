"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Card, Button, Empty, Pill } from "@/components/Card";

export default function ReportsPage() {
  const [reports, setReports] = useState<any[]>([]);
  const [briefs, setBriefs] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.reports.mdtList(20).then(setReports).catch(() => {});
    api.reports.briefs(14).then(setBriefs).catch(() => {});
  }, []);

  async function runMdt() {
    setBusy(true);
    try {
      await api.reports.mdtRun({ kind: "weekly", window_days: 7 });
      alert(
        "MDT-консилиум запущен. Обычно занимает 30-60 сек — страница обновится через минуту.",
      );
      setTimeout(() => api.reports.mdtList(20).then(setReports), 45000);
    } catch (e: any) {
      alert("Ошибка: " + e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <Card
        title="MDT-отчёты"
        action={<Button onClick={runMdt} disabled={busy}>{busy ? "Запускаю…" : "Собрать консилиум"}</Button>}
      >
        {reports.length === 0 ? (
          <Empty
            title="Отчётов пока нет"
            hint="Консилиум собирается автоматически каждое воскресенье, или вручную по кнопке."
          />
        ) : (
          <ul className="space-y-2">
            {reports.map((r) => (
              <li key={r.id}>
                <Link
                  href={`/reports/${r.id}`}
                  className="block rounded-lg border border-border bg-bg-elevated p-3 transition hover:border-accent/40"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold">
                          {new Date(r.created_at).toLocaleDateString("ru-RU", {
                            day: "numeric",
                            month: "short",
                            year: "numeric",
                          })}
                        </span>
                        <Pill tone="accent">{r.kind}</Pill>
                        {r.problem_list?.length > 0 && (
                          <Pill tone="muted">{r.problem_list.length} проблем</Pill>
                        )}
                        {r.safety_net?.length > 0 && (
                          <Pill tone="warn">{r.safety_net.length} safety</Pill>
                        )}
                      </div>
                      <p className="mt-1 line-clamp-2 text-sm text-fg-muted">
                        {r.gp_synthesis}
                      </p>
                    </div>
                    <span className="text-fg-faint">→</span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Утренние брифы">
        {briefs.length === 0 ? (
          <Empty title="Пока нет брифов" hint="Появятся после первой генерации (автоматически в 06:30)." />
        ) : (
          <ul className="space-y-2">
            {briefs.map((b) => (
              <li key={b.id} className="rounded-lg border border-border bg-bg-elevated p-3">
                <div className="mb-1 flex items-center gap-2 text-xs text-fg-muted">
                  <span className="font-medium text-fg">{b.for_date}</span>
                  <span>·</span>
                  <span>{new Date(b.created_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</span>
                </div>
                <p className="whitespace-pre-wrap text-sm text-fg">{b.text}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
