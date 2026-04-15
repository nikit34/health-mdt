"use client";

import { useEffect, useState } from "react";
import { api, setSession } from "@/lib/api";

export default function LoginPage() {
  const [pin, setPin] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  // Allow QR/deep-link: #pin=XXXXXX
  useEffect(() => {
    const hash = window.location.hash;
    const match = hash.match(/pin=([0-9]+)/);
    if (match) {
      setPin(match[1]);
      submit(match[1]).catch(() => {});
    }
  }, []);

  async function submit(value = pin) {
    setBusy(true);
    setErr("");
    try {
      const res = await api.login(value);
      setSession(res.token);
      // Check onboarding status
      const status = await api.status();
      window.location.href = status.user_onboarded ? "/" : "/onboarding";
    } catch (e: any) {
      setErr("Неверный PIN");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto mt-12 max-w-sm">
      <div className="mb-6 text-center">
        <div className="mx-auto mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full bg-accent-soft">
          <span className="h-3 w-3 rounded-full bg-accent" />
        </div>
        <h1 className="text-lg font-semibold">health-mdt</h1>
        <p className="mt-1 text-sm text-fg-muted">Введи PIN, который выдал деплой-скрипт.</p>
      </div>
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
      <p className="mt-6 text-center text-xs text-fg-faint">
        Забыл PIN? Посмотри в файле <code className="text-fg-muted">data/access.pin</code> на сервере
        или перегенерируй, перезапустив стек.
      </p>
    </div>
  );
}
