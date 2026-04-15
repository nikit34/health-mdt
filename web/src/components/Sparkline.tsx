"use client";

export function Sparkline({
  points,
  width = 120,
  height = 32,
  baseline,
}: {
  points: number[];
  width?: number;
  height?: number;
  baseline?: number;
}) {
  if (!points.length) return <div className="h-8 text-xs text-fg-faint">—</div>;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = Math.max(1e-6, max - min);
  const step = points.length > 1 ? width / (points.length - 1) : 0;
  const yOf = (v: number) => height - ((v - min) / range) * (height - 4) - 2;
  const d = points
    .map((v, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${yOf(v).toFixed(1)}`)
    .join(" ");
  const baseY = baseline != null ? yOf(baseline) : null;
  return (
    <svg className="sparkline" width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      {baseY != null && <line className="baseline" x1={0} y1={baseY} x2={width} y2={baseY} />}
      <path d={d} />
    </svg>
  );
}
