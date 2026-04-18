"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Card, Pill, Empty } from "@/components/Card";

export default function ReportPage({ params }: { params: { id: string } }) {
  const [r, setR] = useState<any>(null);
  const [err, setErr] = useState("");
  const [pdfBusy, setPdfBusy] = useState(false);
  // Telegram nudge: show when the bot is configured but this user hasn't paired
  // their chat. Report pages are a high-intent moment — the user just saw value
  // from the MDT, so offering automatic delivery to Telegram lands well here.
  const [tg, setTg] = useState<{ show: boolean; dismissed: boolean }>({
    show: false,
    dismissed: false,
  });

  useEffect(() => {
    api.reports
      .mdtGet(Number(params.id))
      .then(setR)
      .catch((e) => setErr(e.message));

    // Dismissal persists in localStorage so we don't nag the same user on every report
    const dismissed =
      typeof window !== "undefined" && window.localStorage.getItem("hmdt_tg_nudge_dismissed") === "1";
    if (dismissed) {
      setTg({ show: false, dismissed: true });
      return;
    }
    api.telegram
      .status()
      .then((s) => setTg({ show: s.bot_configured && !s.paired, dismissed: false }))
      .catch(() => setTg({ show: false, dismissed: false }));
  }, [params.id]);

  function dismissTg() {
    if (typeof window !== "undefined") {
      window.localStorage.setItem("hmdt_tg_nudge_dismissed", "1");
    }
    setTg({ show: false, dismissed: true });
  }

  async function downloadPdf() {
    setPdfBusy(true);
    try {
      await api.reports.mdtPdf(Number(params.id));
    } catch (e: any) {
      alert("Не удалось сформировать PDF: " + e.message);
    } finally {
      setPdfBusy(false);
    }
  }

  if (err) return <div className="text-danger">Ошибка: {err}</div>;
  if (!r) return <div className="skeleton h-48" />;

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link href="/reports" className="text-xs text-fg-muted hover:text-fg">
            ← Все отчёты
          </Link>
          <h1 className="mt-2 text-lg font-semibold">
            MDT-отчёт от{" "}
            {new Date(r.created_at).toLocaleString("ru-RU", {
              day: "numeric",
              month: "long",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </h1>
        </div>
        <button
          onClick={downloadPdf}
          disabled={pdfBusy}
          className="inline-flex items-center gap-1.5 rounded-md bg-bg-elevated px-3 py-1.5 text-sm text-fg transition hover:bg-border/60 disabled:opacity-50"
          title="Скачать PDF для похода к живому врачу"
        >
          {pdfBusy ? "Формирую PDF…" : "PDF для врача"}
        </button>
      </div>

      {tg.show && <TelegramNudge onDismiss={dismissTg} />}

      <Card title="Синтез GP">
        <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-fg">{r.gp_synthesis}</p>
      </Card>

      {r.problem_list?.length > 0 && (
        <Card title="Список проблем">
          <ul className="space-y-2">
            {r.problem_list.map((p: any, i: number) => (
              <li key={i} className="flex items-start gap-3 rounded-md border border-border bg-bg-elevated p-3">
                <ProblemPill status={p.status} />
                <div className="flex-1 text-sm">
                  <div className="font-medium text-fg">{p.problem}</div>
                  {p.note && <div className="mt-0.5 text-fg-muted">{p.note}</div>}
                  {p.since && <div className="mt-1 text-xs text-fg-faint">с {p.since}</div>}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {r.safety_net?.length > 0 && (
        <Card title="Safety net — когда не ждать следующего брифа">
          <ul className="space-y-2">
            {r.safety_net.map((s: string, i: number) => (
              <li key={i} className="flex gap-2 rounded-md bg-warn/10 p-3 text-sm text-warn">
                <span>⚠️</span>
                <span>{s}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Ноты специалистов">
        <div className="grid gap-3 md:grid-cols-2">
          {Object.entries(r.specialist_notes || {}).map(([name, note]: [string, any]) => (
            <div
              key={name}
              className="rounded-md border border-border bg-bg-elevated p-3 text-sm"
            >
              <div className="mb-2 flex items-center gap-2">
                <span className="font-semibold capitalize text-fg">{note.role || name}</span>
                {note.confidence != null && (
                  <Pill tone="muted">conf {Math.round(note.confidence * 100)}%</Pill>
                )}
              </div>
              {note.narrative && <p className="text-fg-muted">{note.narrative}</p>}
              {note.soap?.assessment && (
                <details className="mt-2 text-xs">
                  <summary className="cursor-pointer text-fg-faint">SOAP</summary>
                  <div className="mt-2 space-y-1 text-fg-muted">
                    {["subjective", "objective", "assessment", "plan"].map((k) =>
                      note.soap[k] ? (
                        <div key={k}>
                          <span className="font-medium uppercase text-fg-faint">{k}: </span>
                          {note.soap[k]}
                        </div>
                      ) : null,
                    )}
                  </div>
                </details>
              )}
              {note.safety_flags?.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {note.safety_flags.map((f: string, i: number) => (
                    <Pill key={i} tone="warn">{f}</Pill>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </Card>

      {r.evidence?.length > 0 && (
        <Card title="Доказательная база (PubMed)">
          <ul className="space-y-2">
            {r.evidence.map((e: any) => (
              <li key={e.pmid} className="rounded-md border border-border bg-bg-elevated p-3 text-sm">
                <a
                  href={e.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="font-medium text-accent hover:underline"
                >
                  {e.title}
                </a>
                <div className="mt-1 text-xs text-fg-muted">
                  {e.journal}
                  {e.year && `, ${e.year}`} · PMID {e.pmid}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function ProblemPill({ status }: { status: string }) {
  const tones: Record<string, any> = {
    active: "danger",
    watchful: "warn",
    resolved: "ok",
  };
  return <Pill tone={tones[status] || "muted"}>{status}</Pill>;
}

function TelegramNudge({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-accent/20 bg-accent-soft/30 px-4 py-3">
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        className="mt-0.5 flex-shrink-0 text-accent"
        aria-hidden
      >
        <path d="M21 4L2.5 11.5c-.7.3-.7 1.3 0 1.6l4.5 1.7L18 7l-8 8.5.5 4.5c.2.9 1.4 1 1.9.3l2.3-3.3 4.5 3.3c.7.5 1.7.1 1.9-.7L22 5c.2-.8-.5-1.4-1-1z" />
      </svg>
      <div className="flex-1 text-sm">
        <span className="text-fg">Получать следующие отчёты прямо в Telegram</span>
        <span className="text-fg-muted"> — утренний бриф в 07:00, без захода в приложение. </span>
        <Link
          href="/settings#telegram"
          className="font-medium text-accent hover:underline"
        >
          Привязать бота →
        </Link>
      </div>
      <button
        onClick={onDismiss}
        className="text-xs text-fg-faint hover:text-fg"
        title="Больше не показывать"
        aria-label="Закрыть"
      >
        ×
      </button>
    </div>
  );
}
