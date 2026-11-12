/** Форматирование времени проверки: «14:32:05» */
export function formatTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** Относительное время: «5 с назад», «3 мин назад» */
export function timeAgo(iso: string | null): string {
  if (!iso) return "ещё не проверялся";
  const sec = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (sec < 5) return "только что";
  if (sec < 60) return `${sec} с назад`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min} мин назад`;
  const h = Math.round(min / 60);
  return `${h} ч назад`;
}

export function formatLatency(ms: number | null): string {
  return ms === null ? "—" : `${ms} мс`;
}
