"use client";

import { useEffect, useState } from "react";
import { api, setSession } from "@/lib/api";

export default function LoginPage() {
  const [mode, setMode] = useState<"pin" | "oauth" | "loading">("loading");
  const [pin, setPin] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // PIN auto-login from URL hash
    const hash = window.location.hash;
    const match = hash.match(/pin=([0-9]+)/);
    if (match) {
      setPin(match[1]);
      submit(match[1]).catch(() => {});
      return;
    }
    fetch("/api/auth/mode")
      .then((r) => r.json())
      .then((r) => setMode(r.mode === "oauth" ? "oauth" : "pin"))
      .catch(() => setMode("pin"));
  }, []);

  async function submit(value = pin) {
    setBusy(true);
    setErr("");
    try {
      const res = await api.login(value);
      setSession(res.token);
      const status = await api.status();
      window.location.href = status.user_onboarded ? "/" : "/onboarding";
    } catch (e: any) {
      setErr("Неверный PIN");
    } finally {
      setBusy(false);
    }
  }

  if (mode === "loading") {
    return <div className="skeleton mx-auto mt-24 h-64 w-80" />;
  }

  return (
    <div className="mx-auto mt-12 max-w-sm">
      <div className="mb-6 text-center">
        <div className="mx-auto mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full bg-accent-soft">
          <span className="h-3 w-3 rounded-full bg-accent" />
        </div>
        <h1 className="text-lg font-semibold">health-mdt</h1>
        <p className="mt-1 text-sm text-fg-muted">
          {mode === "oauth" ? "Войди через Google." : "Введи PIN, который выдал деплой-скрипт."}
        </p>
      </div>

      {mode === "oauth" ? (
        <a
          href="/api/auth/oauth/google"
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-border bg-bg-elevated py-3 text-sm font-medium text-fg transition hover:bg-border/50"
        >
          <GoogleLogo /> Войти через Google
        </a>
      ) : (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <input
            value={pin}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 6))}
            inputMode="numeric"
            autoFocus
            placeholder="000000"
            className="w-full rounded-lg border border-border bg-bg-elevated px-4 py-3 text-center text-2xl tabular-nums tracking-[0.6em] outline-none focus:border-accent"
          />
          {err && <div className="text-sm text-danger">{err}</div>}
          <button
            type="submit"
            disabled={busy || pin.length < 1}
            className="w-full rounded-lg bg-accent py-3 text-sm font-semibold text-bg transition disabled:opacity-40"
          >
            {busy ? "…" : "Войти"}
          </button>
        </form>
      )}

      <p className="mt-6 text-center text-xs text-fg-faint">
        {mode === "oauth"
          ? "Allowlist email-ов настраивается через OAUTH_ALLOWED_EMAILS в .env."
          : "Забыл PIN? Смотри в data/access.pin или перегенерируй перезапуском стека."}
      </p>
    </div>
  );
}

function GoogleLogo() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden>
      <path fill="#4285F4" d="M22.5 12.2c0-.8-.1-1.6-.2-2.3H12v4.4h5.9c-.3 1.4-1 2.5-2.2 3.3v2.8h3.6c2.1-2 3.2-4.8 3.2-8.2z"/>
      <path fill="#34A853" d="M12 23c2.9 0 5.4-1 7.2-2.6l-3.6-2.8c-1 .7-2.2 1.1-3.6 1.1-2.8 0-5.1-1.9-6-4.4H2.2v2.8C4 20.9 7.7 23 12 23z"/>
      <path fill="#FBBC05" d="M6 14.3c-.2-.6-.3-1.2-.3-2s.1-1.4.3-2V7.5H2.2C1.4 9 1 10.4 1 12s.4 3 1.2 4.5L6 14.3z"/>
      <path fill="#EA4335" d="M12 5.6c1.6 0 3 .6 4.1 1.6l3.1-3.1C17.4 2.3 14.9 1 12 1 7.7 1 4 3.1 2.2 7.5L6 10.3c.9-2.5 3.2-4.7 6-4.7z"/>
    </svg>
  );
}
