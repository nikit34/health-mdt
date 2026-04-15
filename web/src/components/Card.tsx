import { ReactNode } from "react";

export function Card({
  title,
  action,
  children,
  className = "",
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-xl border border-border bg-bg-card p-5 shadow-[0_1px_0_rgba(255,255,255,0.02)] ${className}`}
    >
      {(title || action) && (
        <header className="mb-3 flex items-center justify-between">
          {title && <h2 className="text-sm font-semibold tracking-tight text-fg">{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
  trend,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  trend?: "up" | "down" | "flat";
}) {
  const color =
    trend === "up" ? "text-ok" : trend === "down" ? "text-danger" : "text-fg-muted";
  return (
    <div className="flex flex-col">
      <span className="text-xs uppercase tracking-wide text-fg-faint">{label}</span>
      <span className="mt-1 text-2xl font-semibold tabular-nums text-fg">{value}</span>
      {hint && <span className={`mt-0.5 text-xs ${color}`}>{hint}</span>}
    </div>
  );
}

export function Pill({ tone = "muted", children }: { tone?: "muted" | "warn" | "danger" | "ok" | "accent"; children: ReactNode }) {
  const tones = {
    muted: "bg-border/60 text-fg-muted",
    warn: "bg-warn/15 text-warn",
    danger: "bg-danger/15 text-danger",
    ok: "bg-ok/15 text-ok",
    accent: "bg-accent-soft text-accent",
  }[tone];
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${tones}`}>
      {children}
    </span>
  );
}

export function Empty({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-bg-elevated px-6 py-10 text-center">
      <div className="text-sm font-medium text-fg">{title}</div>
      {hint && <div className="mt-1 max-w-sm text-sm text-fg-muted">{hint}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Button({
  children,
  onClick,
  variant = "primary",
  disabled,
  type = "button",
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void | Promise<void>;
  variant?: "primary" | "ghost" | "danger";
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
}) {
  const styles = {
    primary: "bg-accent text-bg hover:bg-accent/90 disabled:bg-accent/30",
    ghost: "bg-bg-elevated text-fg hover:bg-border/60 disabled:text-fg-muted",
    danger: "bg-danger/15 text-danger hover:bg-danger/25 disabled:opacity-50",
  }[variant];
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed ${styles} ${className}`}
    >
      {children}
    </button>
  );
}
