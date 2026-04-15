"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { Card, Button, Pill } from "@/components/Card";

type Msg = {
  role: "user" | "gp";
  text: string;
  confidence?: number;
  safety_flags?: string[];
  follow_ups?: string[];
};

export default function ChatPage() {
  const [history, setHistory] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  async function send() {
    const q = input.trim();
    if (!q) return;
    setInput("");
    setHistory((h) => [...h, { role: "user", text: q }]);
    setBusy(true);
    try {
      const resp = await api.chat.ask(q);
      setHistory((h) => [
        ...h,
        {
          role: "gp",
          text: resp.answer,
          confidence: resp.confidence,
          safety_flags: resp.safety_flags,
          follow_ups: resp.follow_ups,
        },
      ]);
    } catch (e: any) {
      setHistory((h) => [...h, { role: "gp", text: `Ошибка: ${e.message}` }]);
    } finally {
      setBusy(false);
      setTimeout(() => {
        listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
      }, 50);
    }
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col">
      <Card title="Спросить GP" className="flex flex-1 flex-col">
        <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto pr-1">
          {history.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
              <p className="text-sm text-fg-muted">
                Спроси про свои данные — GP ответит, опираясь на метрики и анализы.
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
          {busy && (
            <div className="flex items-start gap-2">
              <div className="h-2 w-2 animate-pulse rounded-full bg-accent" />
              <span className="text-sm text-fg-muted">GP думает…</span>
            </div>
          )}
        </div>
        <form
          className="mt-3 flex gap-2 border-t border-border pt-3"
          onSubmit={(e) => {
            e.preventDefault();
            send();
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Напиши вопрос…"
            className="flex-1 rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm outline-none focus:border-accent"
          />
          <Button type="submit" disabled={busy}>Отправить</Button>
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
          <p className="whitespace-pre-wrap">{msg.text}</p>
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
