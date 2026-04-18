"use client";

import { useEffect, useState } from "react";
import { api, clearSession } from "@/lib/api";
import { Card, Button, Pill } from "@/components/Card";

export default function SettingsPage() {
  const [status, setStatus] = useState<any>(null);
  const [me, setMe] = useState<any>(null);
  const [saving, setSaving] = useState(false);

  // Telegram
  const [tgStatus, setTgStatus] = useState<{ paired: boolean; chat_id: number | null; bot_configured: boolean } | null>(null);
  const [pairCode, setPairCode] = useState<string | null>(null);
  const [pairBusy, setPairBusy] = useState(false);

  // Push
  const [pushStatus, setPushStatus] = useState<{ enabled: boolean; subscriptions: number } | null>(null);
  const [pushBusy, setPushBusy] = useState(false);
  const [pushError, setPushError] = useState("");

  // Withings
  const [withings, setWithings] = useState<{
    app_configured: boolean;
    connected: boolean;
    expires_at: string | null;
    last_sync_at: string | null;
  } | null>(null);
  const [withingsBusy, setWithingsBusy] = useState(false);
  const [withingsMsg, setWithingsMsg] = useState("");

  useEffect(() => {
    api.status().then(setStatus).catch(() => {});
    api.me.get().then(setMe).catch(() => {});
    api.telegram.status().then(setTgStatus).catch(() => {});
    api.push.status().then(setPushStatus).catch(() => {});
    api.withings.status().then(setWithings).catch(() => {});

    // Surface the OAuth callback outcome from query params
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      if (url.searchParams.get("withings_connected") === "1") {
        setWithingsMsg("✓ Withings подключён. Начинаю синхронизацию.");
      } else if (url.searchParams.get("withings_error")) {
        setWithingsMsg(`Ошибка OAuth: ${url.searchParams.get("withings_error")}`);
      }
    }
  }, []);

  async function connectWithings() {
    setWithingsBusy(true);
    try {
      const r = await api.withings.connect();
      window.location.href = r.authorize_url;
    } catch (e: any) {
      setWithingsMsg("Ошибка: " + e.message);
      setWithingsBusy(false);
    }
  }

  async function syncWithings() {
    setWithingsBusy(true);
    try {
      const r = await api.withings.sync();
      setWithingsMsg(`Синхронизировано: ${r.inserted ?? 0} новых записей.`);
      const s = await api.withings.status();
      setWithings(s);
    } catch (e: any) {
      setWithingsMsg("Ошибка: " + e.message);
    } finally {
      setWithingsBusy(false);
    }
  }

  async function disconnectWithings() {
    if (!confirm("Отключить Withings и стереть токены?")) return;
    await api.withings.disconnect();
    setWithings({ ...withings!, connected: false });
    setWithingsMsg("Отключено.");
  }

  async function save() {
    setSaving(true);
    try {
      await api.me.update({
        name: me.name,
        birthdate: me.birthdate,
        sex: me.sex,
        height_cm: me.height_cm,
        weight_kg: me.weight_kg,
        timezone: me.timezone,
        context: me.context,
        email_notifications: me.email_notifications,
        notification_email: me.notification_email,
        push_notifications: me.push_notifications,
      });
    } finally {
      setSaving(false);
    }
  }

  // Telegram pairing
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [inviteCopied, setInviteCopied] = useState(false);

  async function generatePairCode() {
    setPairBusy(true);
    try {
      const r = await api.telegram.pairCode();
      setPairCode(r.code);
    } catch (e: any) {
      alert("Ошибка: " + e.message);
    } finally {
      setPairBusy(false);
    }
  }

  async function generateInvite() {
    setPairBusy(true);
    setInviteCopied(false);
    try {
      const r = await api.telegram.invite();
      setInviteUrl(r.url);
      try {
        await navigator.clipboard.writeText(r.url);
        setInviteCopied(true);
      } catch {}
    } catch (e: any) {
      alert("Ошибка: " + e.message);
    } finally {
      setPairBusy(false);
    }
  }

  async function unpairTelegram() {
    if (!confirm("Отвязать Telegram?")) return;
    await api.telegram.unpair();
    setTgStatus({ paired: false, chat_id: null, bot_configured: tgStatus?.bot_configured ?? false });
    setPairCode(null);
  }

  // Push subscription
  async function subscribePush() {
    setPushBusy(true);
    setPushError("");
    try {
      if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
        setPushError("Этот браузер не поддерживает Web Push.");
        return;
      }
      const reg = await navigator.serviceWorker.register("/sw.js");
      const vapid = await api.push.vapidKey();
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapid.public_key),
      });
      const json = sub.toJSON();
      await api.push.subscribe({
        endpoint: json.endpoint!,
        p256dh: json.keys!.p256dh!,
        auth: json.keys!.auth!,
      });
      setPushStatus({ enabled: true, subscriptions: (pushStatus?.subscriptions ?? 0) + 1 });
    } catch (e: any) {
      setPushError("Ошибка: " + e.message);
    } finally {
      setPushBusy(false);
    }
  }

  async function unsubscribePush() {
    setPushBusy(true);
    try {
      await api.push.unsubscribe();
      if ("serviceWorker" in navigator) {
        const reg = await navigator.serviceWorker.getRegistration("/sw.js");
        if (reg) {
          const sub = await reg.pushManager.getSubscription();
          if (sub) await sub.unsubscribe();
        }
      }
      setPushStatus({ enabled: false, subscriptions: 0 });
    } finally {
      setPushBusy(false);
    }
  }

  if (!me) return <div className="skeleton h-48" />;

  return (
    <div className="space-y-4">
      <Card title="Профиль" action={<Button onClick={save} disabled={saving}>{saving ? "Сохраняю…" : "Сохранить"}</Button>}>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Имя" value={me.name ?? ""} onChange={(v) => setMe({ ...me, name: v })} />
          <Input label="Часовой пояс" value={me.timezone ?? ""} onChange={(v) => setMe({ ...me, timezone: v })} />
          <Input label="Дата рождения" type="date" value={me.birthdate ?? ""} onChange={(v) => setMe({ ...me, birthdate: v })} />
          <Input label="Пол" value={me.sex ?? ""} onChange={(v) => setMe({ ...me, sex: v })} />
          <Input label="Рост, см" type="number" value={me.height_cm ?? ""} onChange={(v) => setMe({ ...me, height_cm: Number(v) })} />
          <Input label="Вес, кг" type="number" value={me.weight_kg ?? ""} onChange={(v) => setMe({ ...me, weight_kg: Number(v) })} />
        </div>
        <label className="mt-3 block">
          <span className="mb-1 block text-xs uppercase tracking-wide text-fg-faint">Контекст</span>
          <textarea
            value={me.context ?? ""}
            onChange={(e) => setMe({ ...me, context: e.target.value })}
            rows={5}
            className="w-full rounded-md border border-border bg-bg-elevated p-3 text-sm outline-none focus:border-accent"
          />
        </label>
      </Card>

      {/* Telegram Pairing */}
      <div id="telegram" className="scroll-mt-20" />
      <Card title="Telegram">
        {!tgStatus ? (
          <div className="skeleton h-12" />
        ) : !tgStatus.bot_configured ? (
          <p className="text-sm text-fg-muted">
            Бот не настроен. Задай TELEGRAM_BOT_TOKEN в .env и перезапусти стек.
          </p>
        ) : tgStatus.paired ? (
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Pill tone="ok">привязан</Pill>
              <span className="text-sm text-fg-muted">chat_id: {tgStatus.chat_id}</span>
            </div>
            <Button variant="danger" onClick={unpairTelegram}>Отвязать</Button>
          </div>
        ) : (
          <div className="space-y-4">
            <div>
              <p className="text-sm text-fg-muted">
                Одна ссылка — фаундер открывает в Telegram, жмёт «Start», чат привязан.
                Код действует 5 минут.
              </p>
              {inviteUrl ? (
                <div className="mt-2 space-y-2">
                  <div className="flex items-center gap-2">
                    <code className="flex-1 truncate rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs">
                      {inviteUrl}
                    </code>
                    <Button
                      onClick={async () => {
                        try {
                          await navigator.clipboard.writeText(inviteUrl);
                          setInviteCopied(true);
                        } catch {}
                      }}
                    >
                      {inviteCopied ? "Скопировано ✓" : "Скопировать"}
                    </Button>
                    <a
                      href={inviteUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-bg hover:bg-accent/90"
                    >
                      Открыть
                    </a>
                  </div>
                </div>
              ) : (
                <Button className="mt-2" onClick={generateInvite} disabled={pairBusy}>
                  {pairBusy ? "…" : "Сгенерировать invite-ссылку"}
                </Button>
              )}
            </div>

            <div className="border-t border-border pt-4">
              <p className="text-sm text-fg-muted">
                Или — ручной путь через код:
              </p>
              {pairCode ? (
                <div className="mt-2 flex items-center gap-4">
                  <div className="rounded-lg border border-accent/40 bg-accent/10 px-5 py-3">
                    <span className="text-2xl font-bold tracking-[0.3em] text-accent">{pairCode}</span>
                  </div>
                  <div className="text-sm text-fg-muted">
                    <p>Отправь боту:</p>
                    <code className="mt-1 block rounded bg-bg-elevated px-2 py-1 text-xs">/pair {pairCode}</code>
                    <p className="mt-1 text-xs text-fg-faint">Код действует 5 минут</p>
                  </div>
                </div>
              ) : (
                <Button className="mt-2" variant="ghost" onClick={generatePairCode} disabled={pairBusy}>
                  {pairBusy ? "…" : "Получить код привязки"}
                </Button>
              )}
            </div>
          </div>
        )}
      </Card>

      {/* Withings */}
      <div id="withings" className="scroll-mt-20" />
      <Card title="Withings (весы, BP, body composition)">
        {!withings ? (
          <div className="skeleton h-12" />
        ) : !withings.app_configured ? (
          <p className="text-sm text-fg-muted">
            Приложение Withings не настроено. Владелец инстанса: зарегистрируй Public Cloud app на{" "}
            <a href="https://developer.withings.com" target="_blank" rel="noreferrer" className="text-accent hover:underline">
              developer.withings.com
            </a>
            , добавь WITHINGS_CLIENT_ID и WITHINGS_CLIENT_SECRET в .env, перезапусти стек.
          </p>
        ) : withings.connected ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Pill tone="ok">подключено</Pill>
              {withings.last_sync_at && (
                <span className="text-xs text-fg-muted">
                  последний sync: {new Date(withings.last_sync_at).toLocaleString("ru-RU")}
                </span>
              )}
            </div>
            <p className="text-sm text-fg-muted">
              Данные синхронизируются автоматически раз в 6 часов и перед утренним брифом.
              Тянем: вес, body fat, muscle mass, АД (systolic/diastolic), pulse wave velocity,
              SpO2, сон, активность.
            </p>
            <div className="flex gap-2">
              <Button onClick={syncWithings} disabled={withingsBusy}>
                {withingsBusy ? "Синхронизирую…" : "Синхронизировать сейчас"}
              </Button>
              <Button variant="danger" onClick={disconnectWithings}>Отключить</Button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-fg-muted">
              Подключи аккаунт Withings через OAuth — откроется страница Withings для
              разрешения. Закроет ключевую дыру кардиолога (АД) и эндокринолога (body comp).
            </p>
            <Button onClick={connectWithings} disabled={withingsBusy}>
              {withingsBusy ? "…" : "Подключить Withings"}
            </Button>
          </div>
        )}
        {withingsMsg && <div className="mt-3 text-sm text-fg-muted">{withingsMsg}</div>}
      </Card>

      {/* Notifications */}
      <Card title="Уведомления">
        <div className="space-y-4">
          {/* Web Push */}
          <div className="flex items-center justify-between rounded-md border border-border bg-bg-elevated p-3">
            <div>
              <span className="font-medium text-fg">Web Push</span>
              <span className="ml-2 text-xs text-fg-muted">
                {pushStatus?.enabled
                  ? `${pushStatus.subscriptions} подписок`
                  : "Выключено"}
              </span>
              {pushError && <div className="mt-1 text-xs text-danger">{pushError}</div>}
            </div>
            {pushStatus?.enabled ? (
              <Button variant="danger" onClick={unsubscribePush} disabled={pushBusy}>Отключить</Button>
            ) : (
              <Button onClick={subscribePush} disabled={pushBusy}>
                {pushBusy ? "…" : "Включить"}
              </Button>
            )}
          </div>

          {/* Email */}
          <div className="rounded-md border border-border bg-bg-elevated p-3">
            <div className="flex items-center justify-between">
              <div>
                <span className="font-medium text-fg">Email-уведомления</span>
                <span className="ml-2 text-xs text-fg-muted">
                  {status?.capabilities?.smtp ? "SMTP настроен" : "SMTP не настроен"}
                </span>
              </div>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={me.email_notifications ?? false}
                  onChange={(e) => setMe({ ...me, email_notifications: e.target.checked })}
                  className="accent-accent"
                />
                <span className="text-xs text-fg-muted">Включить</span>
              </label>
            </div>
            {me.email_notifications && (
              <div className="mt-2">
                <Input
                  label="Email для уведомлений (если отличается от OAuth)"
                  value={me.notification_email ?? me.email ?? ""}
                  onChange={(v) => setMe({ ...me, notification_email: v })}
                />
                <p className="mt-1 text-xs text-fg-faint">
                  Утренний бриф и еженедельный MDT-отчёт будут приходить на эту почту.
                </p>
              </div>
            )}
          </div>
        </div>
      </Card>

      <Card title="Интеграции">
        <ul className="space-y-2 text-sm">
          <Integration
            label="Claude LLM"
            ok={status?.capabilities?.llm}
            hint={
              status?.llm_auth_mode === "setup_token"
                ? "Через setup token (подписка Pro/Max)"
                : status?.llm_auth_mode === "api_key"
                ? "Через ANTHROPIC_API_KEY (pay-per-use)"
                : "Задай CLAUDE_CODE_OAUTH_TOKEN или ANTHROPIC_API_KEY в .env"
            }
          />
          <Integration label="Withings" ok={status?.capabilities?.withings} hint="WITHINGS_CLIENT_ID/SECRET в .env — остальное через OAuth" />
          <Integration label="Telegram" ok={status?.capabilities?.telegram} hint={
            me.telegram_chat_id ? `Привязан chat_id ${me.telegram_chat_id}` : "Настрой TELEGRAM_BOT_TOKEN и отправь /pair <КОД>"
          } />
        </ul>
      </Card>

      <Card title="Состояние данных">
        <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
          {Object.entries(status?.counts || {}).map(([k, v]) => (
            <div key={k} className="rounded-md border border-border bg-bg-elevated p-3">
              <div className="text-xs uppercase text-fg-faint">{k}</div>
              <div className="mt-1 text-lg font-semibold">{v as number}</div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Сессия">
        <Button
          variant="danger"
          onClick={() => {
            clearSession();
            window.location.href = "/login";
          }}
        >
          Выйти
        </Button>
      </Card>
    </div>
  );
}

function Input({ label, value, onChange, type = "text" }: { label: string; value: any; onChange: (v: string) => void; type?: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs uppercase tracking-wide text-fg-faint">{label}</span>
      <input
        type={type}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm outline-none focus:border-accent"
      />
    </label>
  );
}

function Integration({ label, ok, hint }: { label: string; ok: boolean; hint: string }) {
  return (
    <li className="flex items-center justify-between rounded-md border border-border bg-bg-elevated p-3">
      <div>
        <span className="font-medium">{label}</span>
        <span className="ml-2 text-xs text-fg-muted">{hint}</span>
      </div>
      <Pill tone={ok ? "ok" : "muted"}>{ok ? "активно" : "выключено"}</Pill>
    </li>
  );
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i++) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}
