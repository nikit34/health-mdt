"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { PrimaryCTA, PublicHeader } from "@/components/PrimaryCTA";

type DemoReport = Awaited<ReturnType<typeof api.public.demoReport>>;

export default function DemoPage() {
  const [report, setReport] = useState<DemoReport | null>(null);
  const [err, setErr] = useState<string>("");

  useEffect(() => {
    api.public
      .demoReport()
      .then(setReport)
      .catch((e) => setErr(String(e?.message || e)));
  }, []);

  if (err) {
    return (
      <div className="mx-auto mt-16 max-w-xl rounded-xl border border-danger/30 bg-danger/5 p-6 text-center">
        <div className="font-semibold text-danger">Не удалось загрузить пример</div>
        <div className="mt-2 text-sm text-fg-muted">{err}</div>
        <Link href="/" className="mt-4 inline-block text-sm text-accent hover:underline">
          ← назад на главную
        </Link>
      </div>
    );
  }

  if (!report) {
    return <ReportSkeleton />;
  }

  return (
    <div className="-mx-4 -mt-4 md:-mx-6">
      <PublicHeader />
      <DemoContextBar />
      <ReportBody report={report} />
      <CallToAction />
    </div>
  );
}

/* ───────── Context bar: just tells the visitor "this is someone else's report" ───────── */

function DemoContextBar() {
  return (
    <div className="border-b border-border bg-accent-soft/30 px-4 py-2 text-center md:px-8">
      <span className="text-xs font-medium text-accent">
        это пример отчёта — сделай свой, нажав «Войти в приложение» сверху
      </span>
    </div>
  );
}

/* ───────── Report body ───────── */

function ReportBody({ report }: { report: DemoReport }) {
  const created = new Date(report.created_at);
  const active = report.problem_list.filter((p) => p.status === "active");
  const watchful = report.problem_list.filter((p) => p.status === "watchful");
  const paragraphs = (report.gp_synthesis || "").split("\n\n").filter(Boolean);

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 md:px-8 md:py-14">
      {/* Title block */}
      <div className="mb-2 text-sm uppercase tracking-wider text-fg-faint">
        Твой MDT-отчёт · {created.toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" })}
      </div>
      <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">
        Что команда нашла в твоих данных
      </h1>
      <p className="mt-3 text-fg-muted">
        Это синтез 9&nbsp;специалистов — кардиолога, эндокринолога, нутрициолога и других —
        прочитавших твои анализы, данные носимых и чек-ины. Внизу ноты&nbsp;каждого.
      </p>

      {/* Patient card */}
      <PatientCard patient={report.patient} />

      {/* Big synthesis */}
      <section className="mt-10">
        <SectionLabel>Суждение GP</SectionLabel>
        <div className="mt-4 space-y-4">
          {paragraphs.map((p, i) => (
            <p key={i} className="text-[16px] leading-[1.65] text-fg">
              {p}
            </p>
          ))}
        </div>
      </section>

      {/* Problem list */}
      {(active.length > 0 || watchful.length > 0) && (
        <section className="mt-12">
          <SectionLabel>Активные проблемы</SectionLabel>
          <div className="mt-4 space-y-3">
            {active.map((p, i) => (
              <ProblemRow key={`a-${i}`} problem={p} tone="active" />
            ))}
            {watchful.map((p, i) => (
              <ProblemRow key={`w-${i}`} problem={p} tone="watchful" />
            ))}
          </div>
        </section>
      )}

      {/* Safety net — prominent */}
      {report.safety_net.length > 0 && (
        <section className="mt-12">
          <SectionLabel>Safety net</SectionLabel>
          <p className="mt-2 text-sm text-fg-muted">
            Триггеры, при которых <span className="text-fg">не ждёшь</span> следующего отчёта, а идёшь к живому врачу.
          </p>
          <div className="mt-4 space-y-2">
            {report.safety_net.map((s, i) => (
              <div
                key={i}
                className="flex items-start gap-3 rounded-lg border border-danger/20 bg-danger/5 p-4"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ff7a7a" strokeWidth="2" className="mt-0.5 flex-shrink-0">
                  <circle cx="12" cy="12" r="9" />
                  <path d="M12 7v5M12 16h.01" />
                </svg>
                <div className="text-sm text-fg">{s}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Evidence */}
      {report.evidence.length > 0 && (
        <section className="mt-12">
          <SectionLabel>На чём основаны суждения</SectionLabel>
          <p className="mt-2 text-sm text-fg-muted">
            Актуальная литература из PubMed и Semantic Scholar. Агенты формируют запросы из паттернов, найденных в твоих данных.
          </p>
          <ul className="mt-4 space-y-2">
            {report.evidence.slice(0, 6).map((e) => (
              <li key={e.pmid} className="rounded-lg border border-border bg-bg-card p-4 text-sm">
                <a
                  href={e.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-fg hover:text-accent"
                >
                  {e.title}
                </a>
                <div className="mt-1 text-xs text-fg-muted">
                  {e.journal}
                  {e.year ? ` · ${e.year}` : ""}
                  {" · PMID "}
                  <span className="font-mono">{e.pmid}</span>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Specialist notes collapsed */}
      <section className="mt-12">
        <SectionLabel>Ноты специалистов</SectionLabel>
        <p className="mt-2 text-sm text-fg-muted">
          Что сказал каждый агент отдельно. Разворачивай, если интересно заглянуть под капот.
        </p>
        <div className="mt-4 space-y-2">
          {Object.entries(report.specialist_notes).map(([name, note]) => (
            <SpecialistNote key={name} name={name} note={note} />
          ))}
        </div>
      </section>

      {/* PDF mockup */}
      <section className="mt-12 rounded-xl border border-border bg-bg-card p-5">
        <div className="flex items-center gap-4">
          <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-accent-soft">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#7cc4ff" strokeWidth="2">
              <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
              <path d="M14 3v6h6M9 17l3-3 3 3M12 14v5" />
            </svg>
          </div>
          <div className="flex-1">
            <div className="text-sm font-semibold text-fg">PDF для живого визита к врачу</div>
            <div className="text-xs text-fg-muted">
              Проблем-лист, GP-синтез, ноты специалистов, safety net, ссылки на литературу. A4, print-friendly.
            </div>
          </div>
          <button
            className="rounded-lg border border-border bg-bg-elevated px-3 py-1.5 text-xs font-medium text-fg-muted"
            disabled
          >
            доступно после регистрации
          </button>
        </div>
      </section>
    </div>
  );
}

/* ───────── Sub-components ───────── */

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-xs font-semibold uppercase tracking-widest text-accent">
      {children}
    </div>
  );
}

function PatientCard({ patient }: { patient: DemoReport["patient"] }) {
  return (
    <div className="mt-8 rounded-xl border border-border bg-bg-card p-5">
      <div className="flex items-start gap-4">
        <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="8" r="4" />
            <path d="M4 21v-2a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v2" />
          </svg>
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-xs uppercase tracking-wide text-fg-faint">пациент</div>
          <div className="mt-0.5 text-sm text-fg">
            {patient.age ? `${patient.age} лет` : "возраст не указан"}
            {patient.sex === "M" ? " · мужчина" : patient.sex === "F" ? " · женщина" : ""}
          </div>
          {patient.context && (
            <p className="mt-3 border-t border-border pt-3 text-sm leading-relaxed text-fg-muted">
              {patient.context}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function ProblemRow({
  problem,
  tone,
}: {
  problem: { problem: string; status: string; since?: string; note?: string };
  tone: "active" | "watchful";
}) {
  const toneCls =
    tone === "active"
      ? "border-warn/20 bg-warn/5"
      : "border-border bg-bg-card";
  const dotCls = tone === "active" ? "bg-warn" : "bg-fg-muted";
  const label = tone === "active" ? "активная" : "наблюдение";
  return (
    <div className={`flex items-start gap-3 rounded-lg border p-4 ${toneCls}`}>
      <span className={`mt-1.5 h-2 w-2 flex-shrink-0 rounded-full ${dotCls}`} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <div className="text-sm font-medium text-fg">{problem.problem}</div>
          <span className="rounded-full bg-border/60 px-2 py-0.5 text-[10px] uppercase tracking-wide text-fg-muted">
            {label}
          </span>
        </div>
        {problem.note && (
          <div className="mt-1 text-xs text-fg-muted">{problem.note}</div>
        )}
        {problem.since && (
          <div className="mt-1 text-[11px] text-fg-faint">
            с {new Date(problem.since).toLocaleDateString("ru-RU")}
          </div>
        )}
      </div>
    </div>
  );
}

function SpecialistNote({
  name,
  note,
}: {
  name: string;
  note: {
    role: string;
    narrative?: string;
    soap?: { subjective?: string; objective?: string; assessment?: string; plan?: string };
    recommendations?: { title: string; detail?: string; priority?: string }[];
    safety_flags?: string[];
  };
}) {
  const [open, setOpen] = useState(false);
  const snippet = note.narrative || note.soap?.assessment || "";
  return (
    <div className="rounded-lg border border-border bg-bg-card">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-3 p-4 text-left transition hover:bg-bg-elevated/60"
      >
        <span className="mt-1.5 h-2 w-2 flex-shrink-0 rounded-full bg-accent" />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-fg">{note.role}</div>
          {!open && snippet && (
            <div className="mt-1 line-clamp-2 text-sm text-fg-muted">{snippet}</div>
          )}
        </div>
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className={`mt-1.5 flex-shrink-0 text-fg-faint transition ${open ? "rotate-180" : ""}`}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div className="space-y-3 border-t border-border px-4 pb-4 pt-3 text-sm">
          {note.narrative && (
            <p className="leading-relaxed text-fg">{note.narrative}</p>
          )}
          {note.soap && (
            <div className="space-y-2 rounded-lg bg-bg-elevated/60 p-3 text-[13px] leading-relaxed">
              {note.soap.subjective && (
                <Row label="S" body={note.soap.subjective} />
              )}
              {note.soap.objective && <Row label="O" body={note.soap.objective} />}
              {note.soap.assessment && (
                <Row label="A" body={note.soap.assessment} />
              )}
              {note.soap.plan && <Row label="P" body={note.soap.plan} />}
            </div>
          )}
          {note.recommendations && note.recommendations.length > 0 && (
            <div>
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-fg-faint">
                рекомендации
              </div>
              <ul className="space-y-1">
                {note.recommendations.map((r, i) => (
                  <li key={i} className="text-fg-muted">
                    <span className="text-fg">{r.title}</span>
                    {r.detail && ` — ${r.detail}`}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {note.safety_flags && note.safety_flags.length > 0 && (
            <div className="rounded-lg border border-danger/20 bg-danger/5 p-3 text-xs text-danger">
              {note.safety_flags.join(" · ")}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Row({ label, body }: { label: string; body: string }) {
  return (
    <div className="flex gap-3">
      <span className="flex-shrink-0 font-mono text-xs text-fg-faint">{label}</span>
      <span className="text-fg-muted">{body}</span>
    </div>
  );
}

/* ───────── CTA ───────── */

function CallToAction() {
  return (
    <section className="border-t border-border bg-gradient-to-b from-bg to-accent-soft/20 px-4 py-16 md:px-8">
      <div className="mx-auto max-w-2xl text-center">
        <h2 className="text-3xl font-semibold tracking-tight">
          Это был чужой пример.
          <br />
          Сделай свой за 30&nbsp;секунд.
        </h2>
        <p className="mt-3 text-fg-muted">
          Загрузи PDF анализов или начни с чек-ина — получишь такой же отчёт, но про себя.
        </p>
        <div className="mt-6 flex flex-col items-center justify-center gap-2">
          <PrimaryCTA size="lg" />
          <Link
            href="/#waitlist"
            className="mt-1 text-xs text-fg-faint hover:text-fg-muted"
          >
            или оставить email для инвайта на платные планы →
          </Link>
        </div>
      </div>
    </section>
  );
}

/* ───────── Skeleton ───────── */

function ReportSkeleton() {
  return (
    <div className="-mx-4 -mt-4 space-y-6 md:-mx-6">
      <div className="border-b border-border bg-bg-elevated/60 px-4 py-3 md:px-8">
        <div className="skeleton mx-auto h-8 max-w-5xl" />
      </div>
      <div className="mx-auto max-w-3xl space-y-4 px-4 md:px-8">
        <div className="skeleton h-6 w-48" />
        <div className="skeleton h-12 w-full" />
        <div className="skeleton h-24 w-full" />
        <div className="skeleton h-40 w-full" />
        <div className="skeleton h-32 w-full" />
      </div>
    </div>
  );
}
