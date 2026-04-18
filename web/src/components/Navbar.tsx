"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { clearSession, hasSession } from "@/lib/api";

const NAV = [
  { href: "/", label: "Бриф" },
  { href: "/reports", label: "Отчёты" },
  { href: "/tasks", label: "Задачи" },
  { href: "/chat", label: "Спросить" },
  { href: "/medications", label: "Лекарства" },
  { href: "/documents", label: "Документы" },
  { href: "/settings", label: "Настройки" },
];

export function Navbar() {
  const pathname = usePathname();
  const [logged, setLogged] = useState(false);

  useEffect(() => {
    setLogged(hasSession());
  }, [pathname]);

  if (pathname === "/login" || pathname === "/onboarding") return null;
  if (pathname?.startsWith("/demo")) return null;
  if (!logged) return null;

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-bg/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 md:px-6">
        <Link href="/" className="flex items-center gap-2 text-sm font-semibold tracking-tight">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-accent" />
          Consilium
        </Link>
        <nav className="hidden gap-1 md:flex">
          {NAV.map((n) => {
            const active = pathname === n.href || (n.href !== "/" && pathname.startsWith(n.href));
            return (
              <Link
                key={n.href}
                href={n.href}
                className={`rounded-md px-3 py-1.5 text-sm transition ${
                  active ? "bg-bg-card text-fg" : "text-fg-muted hover:text-fg"
                }`}
              >
                {n.label}
              </Link>
            );
          })}
        </nav>
        <div className="flex items-center gap-2">
          <button
            className="hidden text-xs text-fg-muted hover:text-fg md:block"
            onClick={() => {
              clearSession();
              window.location.href = "/login";
            }}
          >
            выйти
          </button>
          <MobileMenu />
        </div>
      </div>
    </header>
  );
}

function MobileMenu() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  useEffect(() => setOpen(false), [pathname]);
  return (
    <div className="md:hidden">
      <button
        className="rounded-md border border-border p-2 text-fg-muted"
        onClick={() => setOpen((v) => !v)}
        aria-label="Меню"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>
      {open && (
        <div className="absolute right-4 top-14 w-48 rounded-lg border border-border bg-bg-card py-2 shadow-lg">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className="block px-4 py-2 text-sm text-fg-muted hover:bg-bg-elevated hover:text-fg"
            >
              {n.label}
            </Link>
          ))}
          <button
            className="block w-full px-4 py-2 text-left text-sm text-fg-muted hover:bg-bg-elevated hover:text-fg"
            onClick={() => {
              clearSession();
              window.location.href = "/login";
            }}
          >
            выйти
          </button>
        </div>
      )}
    </div>
  );
}
