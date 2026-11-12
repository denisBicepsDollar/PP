/**
 * Типы доменной модели веб-панели мониторинга доступности.
 *
 * Эти типы — контракт между сервером (API-роуты) и клиентом (панель).
 * Когда мок-движок будет заменён на реальный пинг + БД, типы менять не нужно:
 * изменится только реализация внутри src/lib/mock-engine.ts.
 */

/** Статус узла на текущий момент */
export type DeviceStatus = "online" | "offline" | "degraded" | "disabled";

/** Результат одной проверки доступности */
export type CheckStatus = "online" | "offline" | "degraded";

export interface Device {
  id: string;
  /** Человекочитаемое имя, например «Коммутатор ядра» */
  name: string;
  /** IP-адрес или имя хоста */
  host: string;
  /** Порт проверки (TCP connect) */
  port: number;
  /** Тип устройства: коммутатор, сервер, шлюз и т.д. */
  type: string;
  /** Группа для фильтрации: Сеть / Серверы / Внешние / Периферия */
  group: string;
  /** Включён ли мониторинг узла */
  enabled: boolean;
  createdAt: string;
}

export interface CheckResult {
  id: string;
  deviceId: string;
  checkedAt: string;
  status: CheckStatus;
  /** Задержка ответа в мс, null — если ответа не было */
  latencyMs: number | null;
  /** Причина недоступности (для offline) */
  reason?: string;
}

/** Устройство + вычисленная статистика — то, что отдаёт GET /api/status */
export interface DeviceSnapshot extends Device {
  status: DeviceStatus;
  latencyMs: number | null;
  lastCheckedAt: string | null;
  lastReason?: string;
  /** Uptime за последние 24 часа, % */
  uptime24h: number;
  /** Средняя задержка за 24 часа, мс */
  avgLatencyMs: number | null;
  /** Последние проверки (для полосы истории и графика) */
  checks: CheckResult[];
  totalChecks24h: number;
  failedChecks24h: number;
}

export interface MonitorEvent {
  id: string;
  deviceId: string;
  deviceName: string;
  kind: "down" | "up" | "degraded";
  message: string;
  at: string;
}

export interface StatusResponse {
  devices: DeviceSnapshot[];
  events: MonitorEvent[];
  serverTime: string;
  /** true — данные сгенерированы моком, реальный пинг не выполняется */
  mock: boolean;
}

export interface AddDeviceInput {
  name: string;
  host: string;
  port: number;
  type: string;
  group: string;
}
