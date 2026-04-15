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
};

export default function ChatPage() {
  const [history, setHistory] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    return () => cancelRef.current?.();
  }, []);

  function stop() {
    cancelRef.current?.();
    cancelRef.current = null;
    setBusy(false);
    setHistory((h) => h.map((m, i) => (i === h.length - 1 && m.streaming ? { ...m, streaming: false } : m)));
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

    // Extract safety flag from final chunk (pattern: "⚠ ...")
    cancelRef.current = api.chat.streamAsk(
      q,
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
          // Extract ⚠ safety lines from text
          const warns = Array.from(last.text.matchAll(/⚠\s*([^\n]+)/g)).map((m) => m[1].trim());
          return [...h.slice(0, -1), { ...last, streaming: false, safety_flags: warns }];
        });
        setBusy(false);
        cancelRef.current = null;
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
    );
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
