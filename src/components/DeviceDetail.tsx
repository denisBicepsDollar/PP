"use client";

import type { DeviceSnapshot } from "@/lib/types";
import { formatLatency, formatTime, timeAgo } from "@/lib/format";
import { StatusBadge } from "./StatusBadge";
import { LatencyChart } from "./LatencyChart";
import { IconX } from "./Icons";

interface Props {
  device: DeviceSnapshot;
  onClose: () => void;
  onCheck: (id: string) => void;
  checking: boolean;
}

export function DeviceDetail({ device, onClose, onCheck, checking }: Props) {
  const okCount = device.checks.filter((c) => c.status !== "offline").length;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <h2>{device.name}</h2>
            <p className="muted">
              {device.host}:{device.port} · {device.type} · группа «{device.group}»
            </p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Закрыть">
            <IconX />
          </button>
        </div>

        <div className="detail-status-row">
          <StatusBadge status={device.status} />
          {device.status === "offline" && device.lastReason && (
            <span className="reason">{device.lastReason}</span>
          )}
          <span className="muted">
            Последняя проверка: {formatTime(device.lastCheckedAt)} ({timeAgo(device.lastCheckedAt)})
          </span>
          <button
            className="btn btn-secondary"
            onClick={() => onCheck(device.id)}
            disabled={checking || !device.enabled}
          >
            {checking ? "Проверяем…" : "Проверить сейчас"}
          </button>
        </div>

        <div className="stat-grid">
          <div className="stat-box">
            <span className="stat-label">Uptime за 24 ч</span>
            <span className="stat-value">{device.uptime24h}%</span>
          </div>
          <div className="stat-box">
            <span className="stat-label">Средняя задержка</span>
            <span className="stat-value">{formatLatency(device.avgLatencyMs)}</span>
          </div>
          <div className="stat-box">
            <span className="stat-label">Текущая задержка</span>
            <span className="stat-value">{formatLatency(device.latencyMs)}</span>
          </div>
          <div className="stat-box">
            <span className="stat-label">Проверок за 24 ч</span>
            <span className="stat-value">
              {device.totalChecks24h} <span className="muted">({device.failedChecks24h} падений)</span>
            </span>
          </div>
        </div>

        <h3>Задержка по проверкам</h3>
        <LatencyChart checks={device.checks} />

        <h3>
          История проверок{" "}
          <span className="muted">
            (успешных {okCount} из {device.checks.length})
          </span>
        </h3>
        <div className="history-table-wrap">
          <table className="history-table">
            <thead>
              <tr>
                <th>Время</th>
                <th>Статус</th>
                <th>Задержка</th>
                <th>Причина</th>
              </tr>
            </thead>
            <tbody>
              {[...device.checks].reverse().map((c) => (
                <tr key={c.id}>
                  <td>{formatTime(c.checkedAt)}</td>
                  <td>
                    <StatusBadge status={c.status} />
                  </td>
                  <td>{formatLatency(c.latencyMs)}</td>
                  <td className="muted">{c.reason ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
