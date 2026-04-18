"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Card, Button, Pill } from "@/components/Card";

type Msg = {
  role: "user" | "gp";
  text: string;
  streaming?: boolean;
  confidence?: number;
  safety_flags?: string[];
  follow_ups?: string[];
  partial?: boolean;
};

type ConvMeta = { id: number; title: string; updated_at: string };

const ACTIVE_KEY = "consilium_active_conversation";

export default function ChatPage() {
  const [history, setHistory] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [conversations, setConversations] = useState<ConvMeta[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<(() => void) | null>(null);

  // Rehydrate active conversation on mount
  useEffect(() => {
    refreshConversations();
    const saved = typeof window !== "undefined" ? window.localStorage.getItem(ACTIVE_KEY) : null;
    if (saved) {
      const id = parseInt(saved, 10);
      if (!Number.isNaN(id)) loadConversation(id);
    }
    return () => cancelRef.current?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refreshConversations() {
    try {
      const list = await api.chat.conversations.list();
      setConversations(list);
    } catch {
      /* ignore */
    }
  }

  async function loadConversation(id: number) {
    try {
      const conv = await api.chat.conversations.get(id);
      setConversationId(id);
      window.localStorage.setItem(ACTIVE_KEY, String(id));
      setHistory(
        conv.messages.map((m) => ({
          role: m.role === "assistant" ? "gp" : "user",
          text: m.content,
          safety_flags: m.meta?.safety_flags,
          follow_ups: m.meta?.follow_ups,
          confidence: m.meta?.confidence,
          partial: m.meta?.partial,
        })),
      );
      setSidebarOpen(false);
    } catch {
      // Conversation missing — start fresh
      startNewConversation();
    }
  }

  function startNewConversation() {
    setConversationId(null);
    setHistory([]);
    window.localStorage.removeItem(ACTIVE_KEY);
    setSidebarOpen(false);
  }

  async function archiveConversation(id: number) {
    try {
      await api.chat.conversations.archive(id);
      if (conversationId === id) startNewConversation();
      await refreshConversations();
    } catch {
      /* ignore */
    }
  }

  function stop() {
    cancelRef.current?.();
    cancelRef.current = null;
    setBusy(false);
    setHistory((h) => h.map((m, i) => (i === h.length - 1 && m.streaming ? { ...m, streaming: false, partial: true } : m)));
  }

  function scroll() {
    requestAnimationFrame(() => {
      listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
    });
  }

  async function send() {
    const q = input.trim();
    if (!q) return;
    setInput("");
    setHistory((h) => [...h, { role: "user", text: q }, { role: "gp", text: "", streaming: true }]);
    setBusy(true);
    scroll();

    cancelRef.current = api.chat.streamAsk(
      q,
      (cid) => {
        if (cid !== conversationId) {
          setConversationId(cid);
          window.localStorage.setItem(ACTIVE_KEY, String(cid));
        }
      },
      (chunk) => {
        setHistory((h) => {
          const last = h[h.length - 1];
          if (!last || last.role !== "gp") return h;
          return [...h.slice(0, -1), { ...last, text: last.text + chunk }];
        });
        scroll();
      },
      () => {
        setHistory((h) => {
          const last = h[h.length - 1];
          if (!last) return h;
          const warns = Array.from(last.text.matchAll(/⚠\s*([^\n]+)/g)).map((m) => m[1].trim());
          return [...h.slice(0, -1), { ...last, streaming: false, safety_flags: warns }];
        });
        setBusy(false);
        cancelRef.current = null;
        refreshConversations();
      },
      (err) => {
        setHistory((h) => {
          const last = h[h.length - 1];
          if (!last) return h;
          return [...h.slice(0, -1), { ...last, text: last.text + `\n\n[ошибка: ${err}]`, streaming: false }];
        });
        setBusy(false);
        cancelRef.current = null;
      },
      { conversation_id: conversationId ?? undefined },
    );
  }

  return (
    <div className="relative flex h-[calc(100vh-8rem)] gap-3">
      {sidebarOpen && (
        <>
          {/* Mobile backdrop — dim + tap-to-close */}
          <button
            onClick={() => setSidebarOpen(false)}
            className="fixed inset-0 z-20 bg-black/40 md:hidden"
            aria-label="Закрыть историю"
          />
          <aside className="fixed inset-y-16 left-4 right-4 z-30 max-w-sm overflow-y-auto rounded-lg border border-border bg-bg-elevated p-3 shadow-2xl md:static md:inset-auto md:w-64 md:shrink-0 md:shadow-none">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs uppercase tracking-wide text-fg-muted">История</span>
              <button onClick={startNewConversation} className="text-xs text-accent hover:underline">
                + новый
              </button>
            </div>
            <ul className="space-y-1">
              {conversations.map((c) => (
                <li key={c.id}>
                  <div
                    className={`group flex items-center justify-between rounded px-2 py-1.5 text-sm ${
                      c.id === conversationId ? "bg-accent/20 text-fg" : "hover:bg-bg text-fg-muted"
                    }`}
                  >
                    <button onClick={() => loadConversation(c.id)} className="flex-1 truncate text-left">
                      {c.title || "Без названия"}
                    </button>
                    <button
                      onClick={() => archiveConversation(c.id)}
                      className="ml-2 text-xs text-fg-faint hover:text-fg md:hidden md:group-hover:inline"
                      title="Архивировать"
                    >
                      ×
                    </button>
                  </div>
                </li>
              ))}
              {conversations.length === 0 && (
                <li className="px-2 py-1.5 text-xs text-fg-faint">Пока пусто</li>
              )}
            </ul>
          </aside>
        </>
      )}
      <Card title="Спросить GP" className="flex flex-1 flex-col">
        <div className="mb-2 flex items-center justify-between">
          <button
            onClick={() => setSidebarOpen((v) => !v)}
            className="text-xs text-fg-muted hover:text-fg"
          >
            {sidebarOpen ? "← скрыть историю" : "история →"}
          </button>
          {history.length > 0 && (
            <button onClick={startNewConversation} className="text-xs text-accent hover:underline">
              новый диалог
            </button>
          )}
        </div>
        <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto pr-1">
          {history.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
              <p className="text-sm text-fg-muted">
                Спроси про свои данные — GP ответит, опираясь на метрики и анализы.
                Следующие вопросы учитывают историю диалога.
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                {[
                  "Почему у меня упала HRV на этой неделе?",
                  "Есть ли тренды в моём сне за 2 недели?",
                  "Пора ли сдать кровь?",
                  "Что с моими анализами липидов?",
                ].map((s) => (
                  <button
                    key={s}
                    onClick={() => setInput(s)}
                    className="rounded-full border border-border bg-bg-elevated px-3 py-1 text-xs text-fg-muted hover:text-fg"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            history.map((m, i) => <Bubble key={i} msg={m} />)
          )}
        </div>
        <form
          className="mt-3 flex gap-2 border-t border-border pt-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (busy) {
              stop();
            } else {
              send();
            }
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Напиши вопрос…"
            className="flex-1 rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm outline-none focus:border-accent"
            disabled={busy}
          />
          {busy ? (
            <Button type="submit" variant="ghost">Стоп</Button>
          ) : (
            <Button type="submit">Отправить</Button>
          )}
        </form>
      </Card>
    </div>
  );
}

function Bubble({ msg }: { msg: Msg }) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-accent/20 px-4 py-2 text-sm text-fg">
          {msg.text}
        </div>
      </div>
    );
  }
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] space-y-2">
        <div className="rounded-2xl rounded-tl-sm border border-border bg-bg-elevated px-4 py-3 text-sm leading-relaxed text-fg">
          <p className="whitespace-pre-wrap">
            {msg.text}
            {msg.streaming && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-accent align-middle" />}
          </p>
          {msg.partial && !msg.streaming && (
            <p className="mt-2 text-[11px] italic text-fg-faint">ответ прерван</p>
          )}
        </div>
        {msg.safety_flags && msg.safety_flags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {msg.safety_flags.map((f, i) => (
              <Pill key={i} tone="warn">
                ⚠ {f}
              </Pill>
            ))}
          </div>
        )}
        {msg.follow_ups && msg.follow_ups.length > 0 && (
          <ul className="space-y-0.5 text-xs text-fg-muted">
            {msg.follow_ups.map((f, i) => (
              <li key={i}>→ {f}</li>
            ))}
          </ul>
        )}
        {msg.confidence != null && (
          <div className="text-[11px] text-fg-faint">
            уверенность: {Math.round(msg.confidence * 100)}%
          </div>
        )}
      </div>
    </div>
  );
}
