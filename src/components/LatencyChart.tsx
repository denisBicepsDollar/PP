"use client";

import { useMemo } from "react";
import type { CheckResult } from "@/lib/types";
import { formatTime } from "@/lib/format";

/**
 * График задержки по истории проверок (чистый SVG, без библиотек).
 * Точки offline (latency = null) разрывают линию.
 */
export function LatencyChart({ checks }: { checks: CheckResult[] }) {
  const { path, points, maxMs, minMs } = useMemo(() => {
    const W = 640;
    const H = 180;
    const PAD = 28;
    const lat = checks.map((c) => c.latencyMs).filter((v): v is number => v !== null);
    const maxMs = lat.length ? Math.max(...lat) : 100;
    const minMs = lat.length ? Math.min(...lat) : 0;
    const span = Math.max(1, maxMs - minMs);

    const x = (i: number) => PAD + (i / Math.max(1, checks.length - 1)) * (W - PAD * 2);
    const y = (v: number) => H - PAD - ((v - minMs) / span) * (H - PAD * 2);

    let path = "";
    let pen = false;
    const points: { cx: number; cy: number; status: string }[] = [];
    checks.forEach((c, i) => {
      if (c.latencyMs === null) {
        pen = false;
        return;
      }
      const cmd = pen ? "L" : "M";
      path += `${cmd}${x(i).toFixed(1)},${y(c.latencyMs).toFixed(1)} `;
      pen = true;
      points.push({ cx: x(i), cy: y(c.latencyMs), status: c.status });
    });
    return { path, points, maxMs, minMs };
  }, [checks]);

  if (!checks.length) return <p className="muted">Нет данных проверок</p>;

  const first = checks[0];
  const last = checks[checks.length - 1];

  return (
    <div className="chart-wrap">
      <svg viewBox="0 0 640 180" className="chart" role="img" aria-label="График задержки">
        {/* сетка */}
        {[0.25, 0.5, 0.75].map((f) => (
          <line
            key={f}
            x1={28}
            x2={612}
            y1={180 - 28 - f * 124}
            y2={180 - 28 - f * 124}
            className="chart-grid"
          />
        ))}
        <path d={path} className="chart-line" fill="none" />
        {points.map((p, i) => (
          <circle key={i} cx={p.cx} cy={p.cy} r={2.6} className={`chart-point chart-point-${p.status}`} />
        ))}
      </svg>
      <div className="chart-axis">
        <span>{formatTime(first.checkedAt)}</span>
        <span>
          мин {minMs} мс · макс {maxMs} мс
        </span>
        <span>{formatTime(last.checkedAt)}</span>
      </div>
    </div>
  );
}
