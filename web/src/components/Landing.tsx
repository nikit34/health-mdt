"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { PrimaryCTA, PublicHeader } from "./PrimaryCTA";

export function Landing() {
  return (
    <div className="-mx-4 -mt-4 md:-mx-6">
      <PublicHeader />
      <Hero />
      <SocialProofStrip />
      <HowItWorks />
      <Pricing />
      <WaitlistSection />
      <Footer />
    </div>
  );
}

/* ───────── Hero ───────── */

function Hero() {
  return (
    <section className="relative overflow-hidden border-b border-border bg-gradient-to-b from-accent-soft/40 to-bg px-4 pb-20 pt-12 md:px-8 md:pt-20">
      <div className="mx-auto max-w-5xl">
        <div className="inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent-soft/60 px-3 py-1 text-xs font-medium text-accent">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          Cardiometabolic MDT · in private beta
        </div>

        <h1 className="mt-6 text-4xl font-semibold leading-[1.1] tracking-tight text-fg md:text-6xl">
          Understand your
          <br />
          <span className="text-accent">cardiometabolic risk</span> —<br />
          не когда-нибудь, а сейчас.
        </h1>

        <p className="mt-6 max-w-2xl text-base leading-relaxed text-fg-muted md:text-lg">
          Загрузи анализы (липиды, HbA1c, CBC) — команда из 9&nbsp;ИИ-специалистов прочитает их вместе с
          данными Apple&nbsp;Watch и Withings (вес, АД, body comp) и выдаст отчёт: что изменилось, что важно, и 3 конкретных действия на&nbsp;сегодня.
          <br />
          <span className="mt-2 inline-block text-fg">
            Первый отчёт — бесплатно. Без регистрации.
          </span>
        </p>

        <div className="mt-8 flex flex-col gap-3 sm:flex-row">
          <PrimaryCTA size="lg" />
          <a
            href="#how"
            className="inline-flex items-center justify-center rounded-lg border border-border bg-bg-elevated px-6 py-3.5 text-sm font-medium text-fg transition hover:border-fg-muted"
          >
            Как это работает
          </a>
        </div>

        <p className="mt-6 text-xs text-fg-faint">
          Информационный инструмент. Не заменяет врача. Используется как decision-support для осознанного разговора с кардиологом и терапевтом.
        </p>
      </div>

      {/* Decorative metric tiles */}
      <div className="pointer-events-none absolute -right-24 top-1/2 hidden -translate-y-1/2 gap-3 lg:flex">
        <MetricTileDeco label="LDL-C" value="3.6" unit="mmol/L" trend="up" delta="+13%" />
        <MetricTileDeco label="HbA1c" value="5.9" unit="%" trend="up" delta="+0.2" offset={40} />
        <MetricTileDeco label="HRV" value="48" unit="ms" trend="down" delta="-15%" offset={-20} />
      </div>
    </section>
  );
}

function MetricTileDeco({
  label,
  value,
  unit,
  trend,
  delta,
  offset = 0,
}: {
  label: string;
  value: string;
  unit: string;
  trend: "up" | "down";
  delta: string;
  offset?: number;
}) {
  const color = trend === "up" ? "text-warn" : "text-danger";
  return (
    <div
      className="w-40 rounded-xl border border-border bg-bg-card/80 p-4 shadow-xl backdrop-blur"
      style={{ transform: `translateY(${offset}px)` }}
    >
      <div className="text-xs uppercase tracking-wide text-fg-faint">{label}</div>
      <div className="mt-1 flex items-baseline gap-1">
        <div className="text-2xl font-semibold tabular-nums">{value}</div>
        <div className="text-xs text-fg-muted">{unit}</div>
      </div>
      <div className={`mt-2 text-xs font-medium ${color}`}>{delta} · 30d</div>
    </div>
  );
}

/* ───────── Social proof strip ───────── */

function SocialProofStrip() {
  return (
    <section className="border-b border-border bg-bg-elevated/50 px-4 py-6 md:px-8">
      <div className="mx-auto grid max-w-5xl grid-cols-2 gap-4 text-center md:grid-cols-4">
        <Stat value="9" label="специалистов в команде" />
        <Stat value="30s" label="до первого отчёта" />
        <Stat value="PubMed" label="evidence на каждое суждение" />
        <Stat value="$0" label="за первую интерпретацию" />
      </div>
    </section>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <div className="text-2xl font-semibold tracking-tight text-fg md:text-3xl">{value}</div>
      <div className="mt-1 text-xs uppercase tracking-wide text-fg-muted">{label}</div>
    </div>
  );
}

/* ───────── How it works ───────── */

function HowItWorks() {
  return (
    <section id="how" className="px-4 py-20 md:px-8">
      <div className="mx-auto max-w-5xl">
        <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
          Как это работает
        </h2>
        <p className="mt-3 max-w-2xl text-fg-muted">
          Три шага до отчёта, четвёртый — чтобы он стал привычкой.
        </p>

        <div className="mt-12 grid gap-5 md:grid-cols-3">
          <Step
            n={1}
            title="Загрузи свои данные"
            body="PDF анализов (любая лаборатория), экспорт Apple Health, OAuth с Withings (весы, АД, body comp). Всё опционально — можно даже без них, на одних чек-инах."
            meta="Claude vision читает PDF, извлекает референсы и значения автоматически."
          />
          <Step
            n={2}
            title="9 специалистов смотрят вместе"
            body="Кардиолог, эндокринолог, нутрициолог, психиатр и 5 других — каждый оценивает данные через призму своей дисциплины. Это не &laquo;единый ИИ&raquo;, это команда."
            meta="Методологии: ESC · ADA · ESMO · KDIGO · RCGP."
          />
          <Step
            n={3}
            title="GP синтезирует план"
            body="Семейный врач (координатор) собирает мнения в единое клиническое суждение. Проблем-лист, 3 действия, safety net, PDF для живого визита."
            meta="SOAP-структура · watchful waiting · evidence из PubMed+Semantic Scholar."
          />
        </div>

        <TelegramHabit />
      </div>
    </section>
  );
}

function Step({ n, title, body, meta }: { n: number; title: string; body: string; meta: string }) {
  return (
    <div className="relative rounded-xl border border-border bg-bg-card p-6 transition hover:border-fg-muted">
      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-soft text-sm font-semibold text-accent">
        {n}
      </div>
      <h3 className="mt-4 text-lg font-semibold text-fg">{title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-fg-muted">{body}</p>
      <p className="mt-4 border-t border-border pt-3 text-xs text-fg-faint">{meta}</p>
    </div>
  );
}

/**
 * Optional 4th step — Telegram bot. Intentionally quieter than the main 3:
 * full-width outlined card with dashed border, no accent-circled number.
 * The signal we want to send: "this is a nice extra, not another hoop".
 */
function TelegramHabit() {
  return (
    <div className="mt-5 flex flex-col items-start gap-4 rounded-xl border border-dashed border-border bg-bg-card/40 p-5 md:flex-row md:items-center md:gap-6">
      <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-bg-elevated text-accent">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
          <path d="M21 4L2.5 11.5c-.7.3-.7 1.3 0 1.6l4.5 1.7L18 7l-8 8.5.5 4.5c.2.9 1.4 1 1.9.3l2.3-3.3 4.5 3.3c.7.5 1.7.1 1.9-.7L22 5c.2-.8-.5-1.4-1-1z" />
        </svg>
      </div>
      <div className="flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-base font-semibold text-fg">
            Каждое утро — бриф в Telegram
          </h3>
          <span className="rounded-full border border-border px-2 py-0.5 text-[10px] uppercase tracking-wide text-fg-faint">
            опционально
          </span>
        </div>
        <p className="mt-1 text-sm leading-relaxed text-fg-muted">
          Привяжи бота в настройках — 4–7 предложений GP падают в чат в 07:00.
          В ответ можно писать `/ask`, `/checkin`, закрывать задачи через `/done`.
          На lock-screen, без открывания приложения.
        </p>
      </div>
    </div>
  );
}

/* ───────── Pricing ───────── */

function Pricing() {
  return (
    <section id="pricing" className="border-t border-border bg-bg-elevated/40 px-4 py-20 md:px-8">
      <div className="mx-auto max-w-6xl">
        <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">Цены</h2>
        <p className="mt-3 max-w-2xl text-fg-muted">
          Бесплатно — чтобы попробовать. Платно — когда станет ясно, что это инструмент, который ты хочешь рядом долго.
        </p>

        <div className="mt-12 grid gap-4 md:grid-cols-4">
          <PriceTier
            tier="free"
            price="Бесплатно"
            tagline="Один отчёт"
            features={[
              "1 загрузка анализов",
              "MDT-команда из 9 специалистов",
              "Проблем-лист + 3 действия",
              "PDF для живого визита",
            ]}
            cta="Начать сейчас"
            ctaHref="/demo"
          />
          <PriceTier
            tier="9"
            price="$9/мес"
            tagline="Tracker"
            features={[
              "Всё из Free",
              "Подключение Apple Health + Withings",
              "Lifestyle-апдейт раз в неделю",
              "История трендов 12 месяцев",
            ]}
            cta="В waitlist"
          />
          <PriceTier
            tier="29"
            price="$29/мес"
            tagline="Full MDT"
            featured
            features={[
              "Всё из Tracker",
              "Полный MDT еженедельно",
              "GP-чат в реальном времени",
              "Квартальная переинтерпретация лабов",
              "Telegram-бот, email-уведомления",
            ]}
            cta="В waitlist"
          />
          <PriceTier
            tier="79"
            price="$79/мес"
            tagline="Concierge"
            features={[
              "Всё из Full MDT",
              "Квартальный обзор с реальным NP/RD",
              "Человеческая подпись на плане",
              "Приоритетный доступ к новым функциям",
            ]}
            cta="В waitlist"
          />
        </div>

        <p className="mt-8 text-center text-xs text-fg-faint">
          Function Health — $499/год · InsideTracker — $299 без MDT-команды · ZOE — $299 + подписка.
          <br />
          Мы думаем, что доступ к команде специалистов должен стоить $29/мес, а не визит.
        </p>
      </div>
    </section>
  );
}

function PriceTier({
  tier,
  price,
  tagline,
  features,
  cta,
  ctaHref,
  featured,
}: {
  tier: string;
  price: string;
  tagline: string;
  features: string[];
  cta: string;
  ctaHref?: string;
  featured?: boolean;
}) {
  return (
    <div
      className={`relative flex flex-col rounded-xl border p-6 ${
        featured
          ? "border-accent bg-bg-card ring-1 ring-accent/30"
          : "border-border bg-bg-card"
      }`}
    >
      {featured && (
        <div className="absolute -top-3 left-6 rounded-full bg-accent px-3 py-0.5 text-[10px] font-bold uppercase tracking-wider text-bg">
          популярный
        </div>
      )}
      <div className="text-xs uppercase tracking-wide text-fg-faint">{tagline}</div>
      <div className="mt-1 text-2xl font-semibold text-fg">{price}</div>
      <ul className="mt-6 flex-1 space-y-2.5">
        {features.map((f, i) => (
          <li key={i} className="flex items-start gap-2 text-sm text-fg-muted">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#7cc4ff" strokeWidth="2.5" className="mt-0.5 flex-shrink-0">
              <path d="M5 12l5 5L20 7" />
            </svg>
            <span>{f}</span>
          </li>
        ))}
      </ul>
      <div className="mt-6">
        {ctaHref ? (
          // Free tier — uses the shared PrimaryCTA so label/destination stay in sync
          // with the rest of the site (currently → /demo for guests, → / for authed).
          <PrimaryCTA size="md" className="w-full" showArrow={false} />
        ) : (
          <a
            href={`#waitlist-${tier}`}
            className="block w-full rounded-lg border border-border bg-bg-elevated py-2.5 text-center text-sm font-medium text-fg-muted transition hover:border-accent hover:text-fg"
            onClick={(e) => {
              // Smooth-scroll + prefill tier into the waitlist form
              e.preventDefault();
              const el = document.getElementById("waitlist");
              if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
              const input = document.getElementById("waitlist-email") as HTMLInputElement | null;
              if (input) input.focus();
              (window as any).__waitlistTier = tier;
              const tierBadge = document.getElementById("waitlist-tier-badge");
              if (tierBadge) tierBadge.textContent = `$${tier}/мес`;
            }}
          >
            {cta}
          </a>
        )}
      </div>
    </div>
  );
}

/* ───────── Waitlist ───────── */

function WaitlistSection() {
  const [email, setEmail] = useState("");
  const [note, setNote] = useState("");
  const [tier, setTier] = useState("");
  const [busy, setBusy] = useState(false);
  const [state, setState] = useState<"idle" | "ok" | "dup" | "err">("idle");
  const [err, setErr] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const selectedTier = tier || (typeof window !== "undefined" && (window as any).__waitlistTier) || "";
      const r = await api.public.waitlist(email, selectedTier, note);
      setState(r.status === "already_on_list" ? "dup" : "ok");
    } catch (e: any) {
      setErr(String(e?.message || e));
      setState("err");
    } finally {
      setBusy(false);
    }
  }

  if (state === "ok" || state === "dup") {
    return (
      <section id="waitlist" className="px-4 py-20 md:px-8">
        <div className="mx-auto max-w-xl rounded-2xl border border-ok/30 bg-ok/5 p-10 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-ok/20">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#7ee09f" strokeWidth="2.5">
              <path d="M5 12l5 5L20 7" />
            </svg>
          </div>
          <h3 className="mt-5 text-xl font-semibold">
            {state === "dup" ? "Ты уже в списке" : "Записали"}
          </h3>
          <p className="mt-2 text-sm text-fg-muted">
            Напишем на <span className="text-fg">{email}</span>, когда откроем платные планы. А пока&nbsp;—{" "}
            <Link href="/demo" className="text-accent hover:underline">
              посмотри пример отчёта
            </Link>
            .
          </p>
        </div>
      </section>
    );
  }

  return (
    <section id="waitlist" className="px-4 py-20 md:px-8">
      <div className="mx-auto max-w-2xl">
        <div className="text-center">
          <h2 className="text-2xl font-semibold tracking-tight text-fg-muted md:text-3xl">
            Или оставь email — напишем, когда откроем платные планы
          </h2>
          <p className="mt-2 text-sm text-fg-faint">
            Free-отчёт уже работает — просто нажми <span className="text-accent">«Посмотреть демо»</span> выше.
            Waitlist — для тех, кто хочет больше, чем один отчёт.
          </p>
        </div>

        <form
          onSubmit={submit}
          className="mt-8 space-y-3 rounded-2xl border border-border bg-bg-card/60 p-6"
        >
          <div className="flex items-center justify-between text-xs text-fg-muted">
            <span>Email для инвайта</span>
            <span id="waitlist-tier-badge" className="text-accent">
              {tier ? `$${tier}/мес` : "любой план"}
            </span>
          </div>

          <input
            id="waitlist-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="w-full rounded-lg border border-border bg-bg-elevated px-4 py-3 text-fg placeholder:text-fg-faint outline-none focus:border-accent"
          />

          <div className="flex flex-wrap gap-2">
            {[
              { v: "", label: "Любой план" },
              { v: "9", label: "Tracker $9" },
              { v: "29", label: "Full MDT $29" },
              { v: "79", label: "Concierge $79" },
            ].map((t) => (
              <button
                key={t.v}
                type="button"
                onClick={() => setTier(t.v)}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                  tier === t.v
                    ? "border-accent bg-accent-soft text-accent"
                    : "border-border bg-bg-elevated text-fg-muted hover:border-fg-muted"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Что ты хочешь отслеживать? (опционально — помогает приоритизировать фичи)"
            rows={2}
            className="w-full rounded-lg border border-border bg-bg-elevated px-4 py-3 text-sm text-fg placeholder:text-fg-faint outline-none focus:border-accent"
          />

          {state === "err" && <div className="text-sm text-danger">Ошибка: {err}</div>}

          <button
            type="submit"
            disabled={busy || !email}
            className="w-full rounded-lg border border-border bg-bg-elevated py-2.5 text-sm font-medium text-fg-muted transition hover:border-accent hover:text-fg disabled:opacity-40"
          >
            {busy ? "…" : "Записаться в waitlist"}
          </button>

          <p className="text-center text-[11px] text-fg-faint">
            Email не продаётся. Отписаться — в первом же письме.
          </p>
        </form>
      </div>
    </section>
  );
}

/* ───────── Footer ───────── */

function Footer() {
  return (
    <footer className="border-t border-border bg-bg-elevated/40 px-4 py-10 text-center text-xs text-fg-faint md:px-8">
      <div className="mx-auto max-w-5xl space-y-2">
        <div className="flex items-center justify-center gap-2">
          <span className="h-2 w-2 rounded-full bg-accent" />
          <span className="font-semibold text-fg">Consilium</span>
          <span>· cardiometabolic MDT</span>
        </div>
        <p>
          Информационный инструмент. Не заменяет врача. Любые медицинские решения — только с квалифицированным специалистом.
        </p>
        <p>
          Данные хранятся локально у оператора инстанса. Code:{" "}
          <a href="https://github.com/nikit34/health-mdt" className="hover:text-fg">GitHub</a> · MIT.
        </p>
      </div>
    </footer>
  );
}
