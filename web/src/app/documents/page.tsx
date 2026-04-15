"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, Button, Empty, Pill } from "@/components/Card";

export default function DocumentsPage() {
  const [docs, setDocs] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);

  async function load() {
    setDocs(await api.documents.list());
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  async function onUpload(files: FileList | null) {
    if (!files) return;
    setBusy(true);
    try {
      for (const f of Array.from(files)) {
        await api.documents.upload(f);
      }
      await load();
    } catch (e: any) {
      alert("Ошибка: " + e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card
        title="Медицинские документы"
        action={
          <label className="cursor-pointer">
            <span className={`inline-flex items-center rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-bg transition ${busy ? "opacity-50" : "hover:bg-accent/90"}`}>
              {busy ? "Загружаю…" : "Загрузить"}
            </span>
            <input
              type="file"
              multiple
              accept=".pdf,.jpg,.jpeg,.png,.heic,.webp"
              disabled={busy}
              className="hidden"
              onChange={(e) => onUpload(e.target.files)}
            />
          </label>
        }
      >
        <p className="mb-4 text-sm text-fg-muted">
          Фото анализов, PDF-заключения, выписки. Claude vision распознаёт, извлекает лабораторные значения
          и пополняет базу. Валидность учитывается при анализе.
        </p>

        {docs.length === 0 ? (
          <Empty
            title="Документов нет"
            hint="Кинь PDF/фото анализов — система подхватит референсные интервалы и свяжет с MDT-отчётами."
          />
        ) : (
          <ul className="space-y-2">
            {docs.map((d) => (
              <li key={d.id} className="flex items-start gap-3 rounded-lg border border-border bg-bg-elevated p-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium text-fg">{d.filename}</span>
                    <StatusPill status={d.status} />
                    {d.doc_type && <Pill tone="accent">{d.doc_type}</Pill>}
                  </div>
                  {d.summary && <div className="mt-1 text-xs text-fg-muted">{d.summary}</div>}
                  <div className="mt-1 text-[11px] text-fg-faint">
                    {new Date(d.uploaded_at).toLocaleString("ru-RU")}
                    {d.date && ` · из документа от ${d.date}`}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  if (status === "processed") return <Pill tone="ok">обработан</Pill>;
  if (status === "failed") return <Pill tone="danger">ошибка</Pill>;
  return <Pill tone="warn">обработка…</Pill>;
}
