"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AddDeviceInput, DeviceSnapshot, DeviceStatus, StatusResponse } from "@/lib/types";
import { formatLatency, formatTime, timeAgo } from "@/lib/format";
import { StatusBadge, ChecksStrip, STATUS_META } from "@/components/StatusBadge";
import { DeviceDetail } from "@/components/DeviceDetail";
import { AddDeviceModal } from "@/components/AddDeviceModal";
import {
  IconActivity,
  IconAlert,
  IconCheck,
  IconClock,
  IconPause,
  IconPlay,
  IconPlus,
  IconPower,
  IconRefresh,
  IconSearch,
  IconServer,
  IconTrash,
} from "@/components/Icons";

type Filter = "all" | DeviceStatus;

const INTERVALS = [
  { value: 3, label: "3 с" },
  { value: 5, label: "5 с" },
  { value: 10, label: "10 с" },
  { value: 30, label: "30 с" },
];

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { ...init, headers: { "Content-Type": "application/json" } });
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { error?: string } | null;
    throw new Error(body?.error ?? `Ошибка ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export default function DashboardPage() {
  const [data, setData] = useState<StatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [paused, setPaused] = useState(false);
  const [intervalSec, setIntervalSec] = useState(5);
  const [polling, setPolling] = useState(false);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [group, setGroup] = useState("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [busyIds, setBusyIds] = useState<Set<string>>(new Set());
  const [lastPollAt, setLastPollAt] = useState<Date | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api<StatusResponse>("/api/status");
      setData(res);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось загрузить данные");
    }
  }, []);

  const poll = useCallback(async () => {
    setPolling(true);
    try {
      const res = await api<StatusResponse>("/api/poll", { method: "POST" });
      setData(res);
      setLastPollAt(new Date());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка опроса");
    } finally {
      setPolling(false);
    }
  }, []);

  // Первичная загрузка + автоопрос по таймеру
  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (paused) return;
    timerRef.current = setInterval(() => void poll(), intervalSec * 1000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [paused, intervalSec, poll]);

  /* ---------------- действия над устройствами ---------------- */

  const withBusy = useCallback(async (id: string, fn: () => Promise<unknown>) => {
    setBusyIds((s) => new Set(s).add(id));
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setBusyIds((s) => {
        const next = new Set(s);
        next.delete(id);
        return next;
      });
    }
  }, []);

  const checkOne = useCallback(
    (id: string) =>
      withBusy(id, async () => {
        await api(`/api/devices/${id}/check`, { method: "POST" });
        await load();
      }),
    [withBusy, load],
  );

  const toggle = useCallback(
    (d: DeviceSnapshot) =>
      withBusy(d.id, async () => {
        await api(`/api/devices/${d.id}`, {
          method: "PATCH",
          body: JSON.stringify({ enabled: !d.enabled }),
        });
        await load();
      }),
    [withBusy, load],
  );

  const remove = useCallback(
    (d: DeviceSnapshot) => {
      if (!window.confirm(`Удалить «${d.name}» из списка мониторинга?`)) return;
      void withBusy(d.id, async () => {
        await api(`/api/devices/${d.id}`, { method: "DELETE" });
        if (selectedId === d.id) setSelectedId(null);
        await load();
      });
    },
    [withBusy, load, selectedId],
  );

  const addDevice = useCallback(
    async (input: AddDeviceInput) => {
      await api("/api/devices", { method: "POST", body: JSON.stringify(input) });
      await load();
    },
    [load],
  );

  /* ---------------- производные данные ---------------- */

  const devices = data?.devices ?? [];
  const summary = useMemo(() => {
    const by = (s: DeviceStatus) => devices.filter((d) => d.status === s).length;
    const lat = devices
      .filter((d) => d.status === "online" && d.latencyMs !== null)
      .map((d) => d.latencyMs as number);
    return {
      total: devices.length,
      online: by("online"),
      offline: by("offline"),
      degraded: by("degraded"),
      disabled: by("disabled"),
      avgLatency: lat.length ? Math.round(lat.reduce((a, b) => a + b, 0) / lat.length) : null,
    };
  }, [devices]);

  const groups = useMemo(() => Array.from(new Set(devices.map((d) => d.group))), [devices]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return devices.filter((d) => {
      if (filter !== "all" && d.status !== filter) return false;
      if (group !== "all" && d.group !== group) return false;
      if (q && !`${d.name} ${d.host} ${d.type}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [devices, filter, group, search]);

  const selected = selectedId ? devices.find((d) => d.id === selectedId) ?? null : null;

  const filterTabs: { id: Filter; label: string; count: number }[] = [
    { id: "all", label: "Все", count: summary.total },
    { id: "online", label: "Онлайн", count: summary.online },
    { id: "offline", label: "Офлайн", count: summary.offline },
    { id: "degraded", label: "Деградация", count: summary.degraded },
    { id: "disabled", label: "Отключены", count: summary.disabled },
  ];

  /* ---------------- рендер ---------------- */

  return (
    <div className="page">
      <header className="topbar">
        <div className="brand">
          <span className="brand-icon">
            <IconActivity size={20} />
          </span>
          <div>
            <h1>Панель мониторинга доступности</h1>
            <p className="muted">D4NMS · опрос сетевых узлов · демо-режим на моках</p>
          </div>
        </div>
        <div className="topbar-actions">
          <span className="mock-chip" title="Данные генерируются мок-движком, реальный пинг не выполняется">
            МОК · без реального пинга
          </span>
          <button className="btn btn-secondary" onClick={() => void poll()} disabled={polling}>
            <IconRefresh size={15} className={polling ? "spin" : undefined} />
            {polling ? "Опрашиваем…" : "Проверить все"}
          </button>
          <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
            <IconPlus size={15} /> Устройство
          </button>
        </div>
      </header>

      {error && (
        <div className="error-banner" role="alert">
          <IconAlert size={16} /> {error}
          <button className="btn btn-secondary btn-sm" onClick={() => void load()}>
            Повторить
          </button>
        </div>
      )}

      {/* Сводные карточки */}
      <section className="kpi-grid">
        <div className="kpi">
          <span className="kpi-label">Всего узлов</span>
          <span className="kpi-value">{summary.total}</span>
          <span className="kpi-sub">в списке мониторинга</span>
        </div>
        <div className="kpi kpi-online">
          <span className="kpi-label">Онлайн</span>
          <span className="kpi-value">{summary.online}</span>
          <span className="kpi-sub">{summary.total ? Math.round((summary.online / summary.total) * 100) : 0}% от всех</span>
        </div>
        <div className="kpi kpi-offline">
          <span className="kpi-label">Офлайн</span>
          <span className="kpi-value">{summary.offline}</span>
          <span className="kpi-sub">требуют внимания</span>
        </div>
        <div className="kpi kpi-degraded">
          <span className="kpi-label">Деградация</span>
          <span className="kpi-value">{summary.degraded}</span>
          <span className="kpi-sub">высокая задержка</span>
        </div>
        <div className="kpi">
          <span className="kpi-label">Средняя задержка</span>
          <span className="kpi-value">{formatLatency(summary.avgLatency)}</span>
          <span className="kpi-sub">по онлайн-узлам</span>
        </div>
      </section>

      {/* Панель управления опросом и фильтрами */}
      <section className="toolbar panel">
        <div className="toolbar-group">
          <button
            className={`btn ${paused ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setPaused((p) => !p)}
          >
            {paused ? <IconPlay size={15} /> : <IconPause size={15} />}
            {paused ? "Возобновить" : "Пауза"}
          </button>
          <label className="interval-label">
            <IconClock size={14} />
            <select
              value={intervalSec}
              onChange={(e) => setIntervalSec(Number(e.target.value))}
              aria-label="Интервал опроса"
            >
              {INTERVALS.map((i) => (
                <option key={i.value} value={i.value}>
                  {i.label}
                </option>
              ))}
            </select>
          </label>
          <span className="muted small">
            {paused
              ? "Автоопрос приостановлен"
              : `Автоопрос каждые ${intervalSec} с`}
            {lastPollAt && ` · последний опрос ${formatTime(lastPollAt.toISOString())}`}
          </span>
        </div>

        <div className="toolbar-group">
          <label className="search-box">
            <IconSearch size={15} />
            <input
              placeholder="Поиск по имени, IP, типу…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <select value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Группа">
            <option value="all">Все группы</option>
            {groups.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        </div>
      </section>

      <div className="tabs" role="tablist">
        {filterTabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={filter === t.id}
            className={`tab ${filter === t.id ? "tab-active" : ""}`}
            onClick={() => setFilter(t.id)}
          >
            {t.label} <span className="tab-count">{t.count}</span>
          </button>
        ))}
      </div>

      <div className="main-grid">
        {/* Таблица устройств */}
        <section className="panel table-panel">
          {!data ? (
            <p className="muted empty">Загрузка данных…</p>
          ) : filtered.length === 0 ? (
            <p className="muted empty">Устройства не найдены. Измените фильтры или добавьте узел.</p>
          ) : (
            <div className="table-wrap">
              <table className="devices-table">
                <thead>
                  <tr>
                    <th>Устройство</th>
                    <th>Статус</th>
                    <th>Задержка</th>
                    <th>Uptime 24 ч</th>
                    <th>Последние проверки</th>
                    <th>Проверено</th>
                    <th className="actions-col">Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((d) => (
                    <tr key={d.id} className={`row-${d.status}`}>
                      <td>
                        <button className="device-name" onClick={() => setSelectedId(d.id)}>
                          <IconServer size={15} />
                          <span>
                            <strong>{d.name}</strong>
                            <small>
                              {d.host}:{d.port} · {d.type} · {d.group}
                            </small>
                          </span>
                        </button>
                      </td>
                      <td>
                        <StatusBadge status={d.status} />
                        {d.status === "offline" && d.lastReason && (
                          <small className="row-reason">{d.lastReason}</small>
                        )}
                      </td>
                      <td className="mono">{formatLatency(d.latencyMs)}</td>
                      <td className="mono">{d.uptime24h}%</td>
                      <td>
                        <ChecksStrip checks={d.checks} />
                      </td>
                      <td className="muted small">{timeAgo(d.lastCheckedAt)}</td>
                      <td>
                        <div className="row-actions">
                          <button
                            className="icon-btn"
                            title="Проверить сейчас"
                            disabled={!d.enabled || busyIds.has(d.id)}
                            onClick={() => void checkOne(d.id)}
                          >
                            <IconRefresh size={15} className={busyIds.has(d.id) ? "spin" : undefined} />
                          </button>
                          <button
                            className="icon-btn"
                            title={d.enabled ? "Отключить мониторинг" : "Включить мониторинг"}
                            disabled={busyIds.has(d.id)}
                            onClick={() => void toggle(d)}
                          >
                            <IconPower size={15} />
                          </button>
                          <button
                            className="icon-btn icon-btn-danger"
                            title="Удалить"
                            disabled={busyIds.has(d.id)}
                            onClick={() => remove(d)}
                          >
                            <IconTrash size={15} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Лента событий */}
        <aside className="panel events-panel">
          <h2>
            <IconAlert size={16} /> Последние события
          </h2>
          {!data || data.events.length === 0 ? (
            <p className="muted">Событий пока нет</p>
          ) : (
            <ul className="events-list">
              {data.events.slice(0, 12).map((e) => (
                <li key={e.id} className={`event event-${e.kind}`}>
                  <span className="event-icon">
                    {e.kind === "up" ? <IconCheck size={14} /> : <IconAlert size={14} />}
                  </span>
                  <div>
                    <p>{e.message}</p>
                    <small className="muted">{formatTime(e.at)}</small>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>

      <footer className="footer muted">
        Демо-режим: статусы генерируются мок-движком (<code>src/lib/mock-engine.ts</code>).
        При переходе на реальный мониторинг этот файл заменяется на TCP/ICMP-чекер и БД —
        интерфейс и API не изменятся. Серверное время:{" "}
        {data ? formatTime(data.serverTime) : "—"} · статусы:{" "}
        {Object.values(STATUS_META).map((m) => m.label).join(" / ")}
      </footer>

      {selected && (
        <DeviceDetail
          device={selected}
          onClose={() => setSelectedId(null)}
          onCheck={(id) => void checkOne(id)}
          checking={busyIds.has(selected.id)}
        />
      )}
      {showAdd && <AddDeviceModal onClose={() => setShowAdd(false)} onAdd={addDevice} />}
    </div>
  );
}
