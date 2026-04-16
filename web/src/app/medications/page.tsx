"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, Button, Empty, Pill } from "@/components/Card";

type Med = {
  id: number;
  name: string;
  dose: string;
  frequency: string;
  started_on: string | null;
  stopped_on: string | null;
  notes: string;
  reminder_time: string | null;
  is_active: boolean;
};

const EMPTY_FORM = {
  name: "",
  dose: "",
  frequency: "",
  started_on: "",
  stopped_on: "",
  notes: "",
  reminder_time: "",
};

export default function MedicationsPage() {
  const [meds, setMeds] = useState<Med[]>([]);
  const [includeStopped, setIncludeStopped] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);

  async function load() {
    setMeds(await api.medications.list(includeStopped));
  }
  useEffect(() => {
    load();
  }, [includeStopped]);

  function startEdit(m: Med) {
    setForm({
      name: m.name,
      dose: m.dose || "",
      frequency: m.frequency || "",
      started_on: m.started_on || "",
      stopped_on: m.stopped_on || "",
      notes: m.notes || "",
      reminder_time: m.reminder_time || "",
    });
    setEditingId(m.id);
    setShowForm(true);
  }

  function cancelForm() {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setShowForm(false);
  }

  async function save() {
    if (!form.name.trim()) return;
    const body = {
      name: form.name.trim(),
      dose: form.dose || undefined,
      frequency: form.frequency || undefined,
      started_on: form.started_on || undefined,
      stopped_on: form.stopped_on || undefined,
      notes: form.notes || undefined,
      reminder_time: form.reminder_time || undefined,
    };
    if (editingId) {
      await api.medications.update(editingId, body);
    } else {
      await api.medications.create(body);
    }
    cancelForm();
    load();
  }

  async function stopMed(id: number) {
    if (!confirm("Отметить как прекращённое?")) return;
    const today = new Date().toISOString().slice(0, 10);
    await api.medications.update(id, { stopped_on: today });
    load();
  }

  async function remove(id: number) {
    if (!confirm("Удалить запись полностью?")) return;
    await api.medications.delete(id);
    load();
  }

  return (
    <div className="space-y-4">
      <Card
        title="Лекарства"
        action={
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1.5 text-xs text-fg-muted">
              <input
                type="checkbox"
                checked={includeStopped}
                onChange={(e) => setIncludeStopped(e.target.checked)}
                className="accent-accent"
              />
              показать прекращённые
            </label>
            <Button onClick={() => (showForm ? cancelForm() : setShowForm(true))}>
              {showForm ? "Отмена" : "+ Добавить"}
            </Button>
          </div>
        }
      >
        {showForm && (
          <div className="mb-4 space-y-2 rounded-lg border border-border bg-bg-elevated p-4">
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Название (напр. Metformin)"
                className="rounded-md border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
              />
              <input
                value={form.dose}
                onChange={(e) => setForm({ ...form, dose: e.target.value })}
                placeholder="Доза (напр. 500 mg)"
                className="rounded-md border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
              />
              <input
                value={form.frequency}
                onChange={(e) => setForm({ ...form, frequency: e.target.value })}
                placeholder="Частота (напр. 2 раза в день)"
                className="rounded-md border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
              />
              <input
                value={form.reminder_time}
                onChange={(e) => setForm({ ...form, reminder_time: e.target.value })}
                placeholder="Напомнить в (HH:MM, опц.)"
                className="rounded-md border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
              />
              <div>
                <label className="block text-[11px] text-fg-faint">Начало</label>
                <input
                  type="date"
                  value={form.started_on}
                  onChange={(e) => setForm({ ...form, started_on: e.target.value })}
                  className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-[11px] text-fg-faint">Окончание (если прекращено)</label>
                <input
                  type="date"
                  value={form.stopped_on}
                  onChange={(e) => setForm({ ...form, stopped_on: e.target.value })}
                  className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm"
                />
              </div>
            </div>
            <textarea
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              placeholder="Заметки (зачем принимаешь, побочки и т.п.)"
              rows={2}
              className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
            />
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={cancelForm}>Отмена</Button>
              <Button onClick={save}>{editingId ? "Сохранить" : "Добавить"}</Button>
            </div>
          </div>
        )}

        {meds.length === 0 ? (
          <Empty
            title="Лекарств не добавлено"
            hint="Добавь активные препараты — агенты будут учитывать их при интерпретации данных."
          />
        ) : (
          <ul className="space-y-2">
            {meds.map((m) => (
              <li
                key={m.id}
                className="flex items-start gap-3 rounded-lg border border-border bg-bg-elevated p-3"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={`text-sm font-medium ${m.is_active ? "text-fg" : "text-fg-muted line-through"}`}>
                      {m.name}
                    </span>
                    {m.dose && <span className="text-xs text-fg-muted">{m.dose}</span>}
                    {!m.is_active && <Pill tone="muted">прекращено</Pill>}
                    {m.reminder_time && m.is_active && <Pill tone="accent">⏰ {m.reminder_time}</Pill>}
                  </div>
                  {m.frequency && <div className="mt-0.5 text-xs text-fg-muted">{m.frequency}</div>}
                  {m.notes && <div className="mt-1 text-xs text-fg-faint">{m.notes}</div>}
                  <div className="mt-1 text-[11px] text-fg-faint">
                    {m.started_on && <>с {m.started_on}</>}
                    {m.stopped_on && <> · до {m.stopped_on}</>}
                  </div>
                </div>
                <div className="flex gap-1">
                  <Button variant="ghost" onClick={() => startEdit(m)}>✎</Button>
                  {m.is_active && (
                    <span title="Отметить как прекращённое">
                      <Button variant="ghost" onClick={() => stopMed(m.id)}>⏸</Button>
                    </span>
                  )}
                  <Button variant="ghost" onClick={() => remove(m.id)}>✕</Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
