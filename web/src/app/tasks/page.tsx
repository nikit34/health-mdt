"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, Button, Empty, Pill } from "@/components/Card";

export default function TasksPage() {
  const [filter, setFilter] = useState<"open" | "done" | "all">("open");
  const [tasks, setTasks] = useState<any[]>([]);
  const [newTask, setNewTask] = useState({ title: "", detail: "", priority: "normal", due: "" });
  const [showNew, setShowNew] = useState(false);

  async function load() {
    const status = filter === "all" ? null : filter;
    setTasks(await api.tasks.list(status));
  }

  useEffect(() => {
    load();
  }, [filter]);

  async function create() {
    if (!newTask.title.trim()) return;
    await api.tasks.create({
      title: newTask.title,
      detail: newTask.detail || undefined,
      priority: newTask.priority,
      due: newTask.due || undefined,
    });
    setNewTask({ title: "", detail: "", priority: "normal", due: "" });
    setShowNew(false);
    load();
  }

  async function closeTask(id: number, status: string) {
    await api.tasks.update(id, { status });
    load();
  }

  return (
    <div className="space-y-4">
      <Card
        title="Задачи"
        action={
          <div className="flex gap-2">
            <div className="flex rounded-md border border-border bg-bg-elevated text-xs">
              {(["open", "done", "all"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`px-3 py-1.5 transition ${
                    filter === f ? "bg-bg-card text-fg" : "text-fg-muted hover:text-fg"
                  }`}
                >
                  {f === "open" ? "Открытые" : f === "done" ? "Закрытые" : "Все"}
                </button>
              ))}
            </div>
            <Button onClick={() => setShowNew((v) => !v)}>+ Добавить</Button>
          </div>
        }
      >
        {showNew && (
          <div className="mb-4 space-y-2 rounded-lg border border-border bg-bg-elevated p-4">
            <input
              value={newTask.title}
              onChange={(e) => setNewTask({ ...newTask, title: e.target.value })}
              placeholder="Что сделать"
              className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
            />
            <textarea
              value={newTask.detail}
              onChange={(e) => setNewTask({ ...newTask, detail: e.target.value })}
              placeholder="Детали (опц)"
              rows={2}
              className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
            />
            <div className="flex gap-2">
              <select
                value={newTask.priority}
                onChange={(e) => setNewTask({ ...newTask, priority: e.target.value })}
                className="rounded-md border border-border bg-bg px-2 py-2 text-sm"
              >
                <option value="urgent">🔴 urgent</option>
                <option value="normal">🟡 normal</option>
                <option value="low">⚪ low</option>
              </select>
              <input
                type="date"
                value={newTask.due}
                onChange={(e) => setNewTask({ ...newTask, due: e.target.value })}
                className="rounded-md border border-border bg-bg px-3 py-2 text-sm"
              />
              <Button onClick={create}>Создать</Button>
              <Button variant="ghost" onClick={() => setShowNew(false)}>Отмена</Button>
            </div>
          </div>
        )}

        {tasks.length === 0 ? (
          <Empty title="Пусто" hint={filter === "open" ? "Открытых задач нет — GP или ты их создашь." : "Здесь будут закрытые задачи."} />
        ) : (
          <ul className="space-y-2">
            {tasks.map((t) => (
              <li key={t.id} className="flex items-start gap-3 rounded-lg border border-border bg-bg-elevated p-3">
                <PriorityDot priority={t.priority} />
                <div className="flex-1 min-w-0">
                  <div className={`text-sm font-medium ${t.status !== "open" ? "text-fg-muted line-through" : "text-fg"}`}>
                    {t.title}
                  </div>
                  {t.detail && <div className="mt-0.5 text-xs text-fg-muted">{t.detail}</div>}
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-fg-faint">
                    <span>от {t.created_by}</span>
                    <span>·</span>
                    <span>{t.age_days}д</span>
                    {t.due && <><span>·</span><span>до {t.due}</span></>}
                    {t.source_report_id && (
                      <Pill tone="muted">из MDT #{t.source_report_id}</Pill>
                    )}
                  </div>
                </div>
                {t.status === "open" && (
                  <div className="flex gap-1">
                    {t.reminders_url && (
                      <a
                        href={t.reminders_url}
                        className="rounded-md bg-bg px-2 py-1 text-xs text-fg-muted hover:bg-border/60"
                        title="Добавить в Apple Reminders (iOS)"
                      >
                        ⏰
                      </a>
                    )}
                    <Button variant="ghost" onClick={() => closeTask(t.id, "done")}>✓</Button>
                    <Button variant="ghost" onClick={() => closeTask(t.id, "dismissed")}>✕</Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Apple Reminders">
        <p className="text-sm text-fg-muted">
          У каждой задачи есть ссылка-шорткат ⏰, которая создаёт напоминание в iOS Reminders.
          Для этого один раз установи на iPhone шорткат{" "}
          <span className="font-medium text-fg">«Consilium Add»</span> — инструкция в
          репозитории (<code className="text-fg-muted">docs/apple-reminders.md</code>).
        </p>
      </Card>
    </div>
  );
}

function PriorityDot({ priority }: { priority: string }) {
  const color = { urgent: "bg-danger", normal: "bg-warn", low: "bg-fg-faint" }[priority] || "bg-warn";
  return <span className={`mt-1.5 h-2 w-2 flex-shrink-0 rounded-full ${color}`} />;
}
