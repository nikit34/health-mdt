"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { hasSession } from "@/lib/api";

/**
 * Single source of truth for the "do the next thing" CTA across all public pages.
 *
 * Why this exists: we had 4 different primary-looking CTAs scrambling for attention
 * (Посмотреть пример / Хочу свой / Записаться в waitlist / Начать сейчас). Visitors
 * couldn't tell which action was the main one. The waitlist was winning by visual
 * weight even though it's the fallback path.
 *
 * The rule now: one filled-accent button on the page at a time, and its label +
 * destination change to always mean "the next step from where you are right now".
 * Waitlist is a secondary path; it reads as a quiet link, not a hero button.
 */
export function PrimaryCTA({
  size = "md",
  showArrow = true,
  className = "",
}: {
  size?: "sm" | "md" | "lg";
  showArrow?: boolean;
  className?: string;
}) {
  const pathname = usePathname();
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    setAuthed(hasSession());
  }, [pathname]);

  const { label, href } = resolveCTA(pathname, authed);

  const sizeCls = {
    sm: "px-3 py-1.5 text-xs",
    md: "px-4 py-2 text-sm",
    lg: "px-6 py-3.5 text-sm md:text-base",
  }[size];

  return (
    <Link
      href={href}
      className={`inline-flex items-center justify-center gap-2 rounded-lg bg-accent font-semibold text-bg transition hover:bg-accent/90 ${sizeCls} ${className}`}
    >
      {label}
      {showArrow && (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <path d="M5 12h14M13 6l6 6-6 6" />
        </svg>
      )}
    </Link>
  );
}

export function resolveCTA(
  pathname: string | null,
  authed: boolean,
): { label: string; href: string } {
  const path = pathname || "/";

  // Authed users' next action is always "keep using the product"
  if (authed) {
    if (path === "/" || path.startsWith("/demo") || path.startsWith("/login")) {
      return { label: "На дашборд", href: "/" };
    }
    // Inside protected routes the Navbar already shows navigation; fall back
    // to same label but it's rarely rendered there.
    return { label: "На дашборд", href: "/" };
  }

  // Unauthenticated funnel: / → /demo → /login
  if (path.startsWith("/demo")) {
    return { label: "Войти в приложение", href: "/login" };
  }
  if (path.startsWith("/login")) {
    // /login renders its own form; this CTA becomes a back-step / fallback.
    return { label: "Посмотреть демо", href: "/demo" };
  }
  // Landing and anything else.
  return { label: "Посмотреть демо", href: "/demo" };
}

/**
 * Sticky top header shown on public pages (/ landing, /demo, /login).
 * Single unified surface so the CTA is always visible regardless of scroll.
 */
export function PublicHeader() {
  return (
    <header className="sticky top-0 z-50 border-b border-border bg-bg/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 md:px-6">
        <Link href="/" className="flex items-center gap-2 text-sm font-semibold tracking-tight">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-accent" />
          health-mdt
        </Link>
        <nav className="hidden items-center gap-5 text-sm text-fg-muted md:flex">
          <a href="/#how" className="hover:text-fg">Как работает</a>
          <a href="/#pricing" className="hover:text-fg">Цены</a>
          <Link href="/demo" className="hover:text-fg">Пример</Link>
        </nav>
        <PrimaryCTA size="sm" />
      </div>
    </header>
  );
}
