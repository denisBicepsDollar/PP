/**
 * Мок-движок мониторинга (ДЕМО-РЕЖИМ).
 *
 * Имитирует работу реального чекера: хранит список устройств и историю
 * проверок в памяти сервера, на каждый «опрос» генерирует новые результаты
 * с задержкой, потерями и случайными падениями — как настоящий ping/TCP-check.
 *
 * ВАЖНО: это единственное место, которое нужно будет переписать при переходе
 * на реальный мониторинг. API-роуты и интерфейс при этом не изменятся:
 *   - simulateCheck()  -> реальный TCP connect / ICMP ping с таймаутом
 *   - in-memory Map    -> SQLite/PostgreSQL (таблицы devices, checks)
 *
 * Состояние хранится в модульном синглтоне: в dev-режиме Next.js один
 * процесс, поэтому данные живут между запросами. После рестарта сервера
 * данные пересоздаются из seed-набора.
 */

import type {
  AddDeviceInput,
  CheckResult,
  CheckStatus,
  Device,
  DeviceSnapshot,
  MonitorEvent,
  StatusResponse,
} from "./types";

/* ------------------------------------------------------------------ */
/* Вспомогательные функции                                             */
/* ------------------------------------------------------------------ */

let seq = 0;
function uid(prefix: string): string {
  seq += 1;
  return `${prefix}-${Date.now().toString(36)}-${seq}`;
}

/** Детерминированный генератор (mulberry32) — чтобы seed-история была стабильной */
function mulberry32(seed: number) {
  return function () {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const OFFLINE_REASONS = [
  "Превышен таймаут ожидания ответа (2000 мс)",
  "Connection refused — порт закрыт",
  "Network unreachable — маршрут недоступен",
  "DNS: имя хоста не разрешается",
  "Host unreachable — узел не отвечает на ARP",
];

/* ------------------------------------------------------------------ */
/* Профиль устройства: скрытые параметры «поведения» узла в моке       */
/* ------------------------------------------------------------------ */

interface DeviceProfile {
  baseLatencyMs: number; // типичная задержка
  jitterMs: number; // разброс задержки
  failureRate: number; // 0..1 — вероятность падения на одной проверке
  degradedRate: number; // 0..1 — вероятность «тормозов»
  downUntil?: number; // если задан — узел «лежит» до этого времени
}

interface DeviceRecord {
  device: Device;
  profile: DeviceProfile;
  history: CheckResult[]; // все проверки (seed + живые), по возрастанию времени
  lastStatus: CheckStatus | "disabled";
}

const records = new Map<string, DeviceRecord>();
const events: MonitorEvent[] = [];
let seeded = false;

/* ------------------------------------------------------------------ */
/* Seed-набор устройств                                                */
/* ------------------------------------------------------------------ */

interface SeedDevice {
  name: string;
  host: string;
  port: number;
  type: string;
  group: string;
  enabled?: boolean;
  profile: DeviceProfile;
}

const SEED_DEVICES: SeedDevice[] = [
  {
    name: "Коммутатор ядра",
    host: "10.20.0.1",
    port: 22,
    type: "Коммутатор",
    group: "Сеть",
    profile: { baseLatencyMs: 2, jitterMs: 1, failureRate: 0.005, degradedRate: 0.01 },
  },
  {
    name: "Межсетевой экран (периметр)",
    host: "10.20.0.254",
    port: 443,
    type: "Шлюз",
    group: "Сеть",
    profile: { baseLatencyMs: 4, jitterMs: 2, failureRate: 0.01, degradedRate: 0.02 },
  },
  {
    name: "Маршрутизатор филиала",
    host: "10.20.0.2",
    port: 161,
    type: "Маршрутизатор",
    group: "Сеть",
    profile: { baseLatencyMs: 6, jitterMs: 3, failureRate: 0.02, degradedRate: 0.03 },
  },
  {
    name: "Веб-сервер",
    host: "192.168.10.15",
    port: 443,
    type: "Сервер",
    group: "Серверы",
    profile: { baseLatencyMs: 12, jitterMs: 6, failureRate: 0.02, degradedRate: 0.05 },
  },
  {
    name: "Сервер БД",
    host: "192.168.10.16",
    port: 5432,
    type: "Сервер",
    group: "Серверы",
    profile: { baseLatencyMs: 3, jitterMs: 1, failureRate: 0.005, degradedRate: 0.01 },
  },
  {
    name: "Файловый сервер",
    host: "192.168.10.20",
    port: 445,
    type: "Сервер",
    group: "Серверы",
    profile: { baseLatencyMs: 8, jitterMs: 4, failureRate: 0.03, degradedRate: 0.06 },
  },
  {
    name: "Точка доступа, офис 2",
    host: "192.168.10.50",
    port: 80,
    type: "Точка доступа",
    group: "Периферия",
    // «Нестабильный» узел: часто деградирует и периодически падает
    profile: { baseLatencyMs: 25, jitterMs: 18, failureRate: 0.12, degradedRate: 0.25 },
  },
  {
    name: "Принтер бухгалтерии",
    host: "192.168.10.60",
    port: 9100,
    type: "Принтер",
    group: "Периферия",
    profile: { baseLatencyMs: 15, jitterMs: 8, failureRate: 0.04, degradedRate: 0.08 },
  },
  {
    name: "DNS Google",
    host: "8.8.8.8",
    port: 53,
    type: "Внешний узел",
    group: "Внешние",
    profile: { baseLatencyMs: 18, jitterMs: 7, failureRate: 0.01, degradedRate: 0.03 },
  },
  {
    name: "DNS Яндекс",
    host: "77.88.8.8",
    port: 53,
    type: "Внешний узел",
    group: "Внешние",
    profile: { baseLatencyMs: 22, jitterMs: 9, failureRate: 0.01, degradedRate: 0.03 },
  },
  {
    name: "Шлюз по умолчанию",
    host: "192.168.1.1",
    port: 80,
    type: "Шлюз",
    group: "Сеть",
    // «Лежит» с момента запуска — чтобы на панели сразу было видно офлайн-статус
    profile: {
      baseLatencyMs: 1,
      jitterMs: 1,
      failureRate: 0.95,
      degradedRate: 0,
      downUntil: Date.now() + 1000 * 60 * 60 * 24,
    },
  },
  {
    name: "Резервный сервер (выключен)",
    host: "192.168.10.30",
    port: 22,
    type: "Сервер",
    group: "Серверы",
    enabled: false,
    profile: { baseLatencyMs: 5, jitterMs: 2, failureRate: 0.01, degradedRate: 0.02 },
  },
];

/* ------------------------------------------------------------------ */
/* Симуляция одной проверки                                            */
/* ------------------------------------------------------------------ */

interface SimResult {
  status: CheckStatus;
  latencyMs: number | null;
  reason?: string;
}

function simulateCheck(profile: DeviceProfile, rng: () => number): SimResult {
  const now = Date.now();
  if (profile.downUntil && now < profile.downUntil) {
    return {
      status: "offline",
      latencyMs: null,
      reason: OFFLINE_REASONS[Math.floor(rng() * OFFLINE_REASONS.length)],
    };
  }
  const roll = rng();
  if (roll < profile.failureRate) {
    return {
      status: "offline",
      latencyMs: null,
      reason: OFFLINE_REASONS[Math.floor(rng() * OFFLINE_REASONS.length)],
    };
  }
  if (roll < profile.failureRate + profile.degradedRate) {
    const latency = Math.round(profile.baseLatencyMs + profile.jitterMs * 8 + rng() * 120);
    return { status: "degraded", latencyMs: latency };
  }
  const latency = Math.max(
    1,
    Math.round(profile.baseLatencyMs + (rng() - 0.5) * 2 * profile.jitterMs),
  );
  return { status: "online", latencyMs: latency };
}

function pushEvent(record: DeviceRecord, kind: MonitorEvent["kind"], message: string) {
  events.unshift({
    id: uid("evt"),
    deviceId: record.device.id,
    deviceName: record.device.name,
    kind,
    message,
    at: new Date().toISOString(),
  });
  if (events.length > 50) events.length = 50;
}

/** Выполнить одну проверку узла, записать в историю, зафиксировать смену статуса */
function runCheck(record: DeviceRecord, rng: () => number = Math.random): CheckResult {
  const result = simulateCheck(record.profile, rng);
  const check: CheckResult = {
    id: uid("chk"),
    deviceId: record.device.id,
    checkedAt: new Date().toISOString(),
    status: result.status,
    latencyMs: result.latencyMs,
    reason: result.reason,
  };
  record.history.push(check);

  const prev = record.lastStatus;
  record.lastStatus = result.status;
  if (prev !== "disabled" && prev !== result.status) {
    if (result.status === "offline") {
      pushEvent(record, "down", `${record.device.name}: узел недоступен — ${result.reason ?? "нет ответа"}`);
    } else if (result.status === "degraded") {
      pushEvent(record, "degraded", `${record.device.name}: высокая задержка (${result.latencyMs} мс)`);
    } else if (prev === "offline" || prev === "degraded") {
      pushEvent(record, "up", `${record.device.name}: узел снова доступен (${result.latencyMs} мс)`);
    }
  }
  return check;
}

/* ------------------------------------------------------------------ */
/* Инициализация: seed устройств + история за 24 часа                  */
/* ------------------------------------------------------------------ */

function seed() {
  if (seeded) return;
  seeded = true;
  const now = Date.now();
  const DAY_MS = 24 * 60 * 60 * 1000;
  const STEP_MS = 30 * 60 * 1000; // проверка каждые 30 минут в истории

  SEED_DEVICES.forEach((sd, idx) => {
    const device: Device = {
      id: `dev-${idx + 1}`,
      name: sd.name,
      host: sd.host,
      port: sd.port,
      type: sd.type,
      group: sd.group,
      enabled: sd.enabled !== false,
      createdAt: new Date(now - DAY_MS).toISOString(),
    };
    const record: DeviceRecord = {
      device,
      profile: sd.profile,
      history: [],
      lastStatus: "disabled",
    };

    // История за 24 часа — детерминированный rng на устройство
    const rng = mulberry32(1000 + idx * 77);
    for (let t = now - DAY_MS; t <= now; t += STEP_MS) {
      const r = simulateCheck(sd.profile, rng);
      record.history.push({
        id: uid("chk"),
        deviceId: device.id,
        checkedAt: new Date(t).toISOString(),
        status: r.status,
        latencyMs: r.latencyMs,
        reason: r.reason,
      });
    }
    if (device.enabled) {
      record.lastStatus = record.history[record.history.length - 1].status;
    }
    records.set(device.id, record);
  });

  // Пара стартовых событий для ленты
  events.push(
    {
      id: uid("evt"),
      deviceId: "dev-11",
      deviceName: "Шлюз по умолчанию",
      kind: "down",
      message: "Шлюз по умолчанию: узел недоступен — Host unreachable",
      at: new Date(now - 42 * 60 * 1000).toISOString(),
    },
    {
      id: uid("evt"),
      deviceId: "dev-7",
      deviceName: "Точка доступа, офис 2",
      kind: "degraded",
      message: "Точка доступа, офис 2: высокая задержка (214 мс)",
      at: new Date(now - 18 * 60 * 1000).toISOString(),
    },
  );
}

/* ------------------------------------------------------------------ */
/* Публичное API движка (вызывается из route handlers)                 */
/* ------------------------------------------------------------------ */

function toSnapshot(record: DeviceRecord): DeviceSnapshot {
  const { device, history } = record;
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;
  const day = history.filter((c) => new Date(c.checkedAt).getTime() >= cutoff);
  const ok = day.filter((c) => c.status !== "offline").length;
  const latencies = day
    .map((c) => c.latencyMs)
    .filter((v): v is number => v !== null);
  const last = history[history.length - 1];

  return {
    ...device,
    status: !device.enabled ? "disabled" : last ? last.status : "disabled",
    latencyMs: device.enabled && last ? last.latencyMs : null,
    lastCheckedAt: device.enabled && last ? last.checkedAt : null,
    lastReason: device.enabled && last ? last.reason : undefined,
    uptime24h: day.length ? Math.round((ok / day.length) * 1000) / 10 : 100,
    avgLatencyMs: latencies.length
      ? Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length)
      : null,
    checks: history.slice(-24),
    totalChecks24h: day.length,
    failedChecks24h: day.length - ok,
  };
}

export function getStatus(): StatusResponse {
  seed();
  return {
    devices: Array.from(records.values()).map(toSnapshot),
    events: [...events],
    serverTime: new Date().toISOString(),
    mock: true,
  };
}

/** Один раунд опроса всех включённых узлов */
export function pollAll(): StatusResponse {
  seed();
  for (const record of records.values()) {
    if (record.device.enabled) runCheck(record);
  }
  return getStatus();
}

export function checkOne(id: string): DeviceSnapshot | null {
  seed();
  const record = records.get(id);
  if (!record) return null;
  if (record.device.enabled) runCheck(record);
  return toSnapshot(record);
}

export function addDevice(input: AddDeviceInput): DeviceSnapshot {
  seed();
  const device: Device = {
    id: uid("dev"),
    name: input.name.trim(),
    host: input.host.trim(),
    port: input.port,
    type: input.type.trim() || "Устройство",
    group: input.group.trim() || "Сеть",
    enabled: true,
    createdAt: new Date().toISOString(),
  };
  const record: DeviceRecord = {
    device,
    profile: { baseLatencyMs: 10, jitterMs: 5, failureRate: 0.03, degradedRate: 0.05 },
    history: [],
    lastStatus: "disabled",
  };
  records.set(device.id, record);
  runCheck(record);
  return toSnapshot(record);
}

export function setEnabled(id: string, enabled: boolean): DeviceSnapshot | null {
  seed();
  const record = records.get(id);
  if (!record) return null;
  record.device.enabled = enabled;
  if (enabled) {
    runCheck(record);
    pushEvent(record, "up", `${record.device.name}: мониторинг включён`);
  } else {
    record.lastStatus = "disabled";
    pushEvent(record, "degraded", `${record.device.name}: мониторинг отключён`);
  }
  return toSnapshot(record);
}

export function removeDevice(id: string): boolean {
  seed();
  return records.delete(id);
}
