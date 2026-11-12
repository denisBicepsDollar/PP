import type { DeviceStatus } from "@/lib/types";

export const STATUS_META: Record<
  DeviceStatus,
  { label: string; className: string; dotClass: string }
> = {
  online: { label: "Онлайн", className: "badge badge-online", dotClass: "dot dot-online" },
  offline: { label: "Офлайн", className: "badge badge-offline", dotClass: "dot dot-offline" },
  degraded: { label: "Деградация", className: "badge badge-degraded", dotClass: "dot dot-degraded" },
  disabled: { label: "Отключён", className: "badge badge-disabled", dotClass: "dot dot-disabled" },
};

export function StatusBadge({ status }: { status: DeviceStatus }) {
  const meta = STATUS_META[status];
  return (
    <span className={meta.className}>
      <span className={meta.dotClass} />
      {meta.label}
    </span>
  );
}

/** Полоса из последних проверок: зелёный/красный/жёлтый квадратик на каждую проверку */
export function ChecksStrip({ checks }: { checks: { status: string }[] }) {
  const last = checks.slice(-20);
  return (
    <span className="checks-strip" title="Последние проверки (слева — старые)">
      {last.map((c, i) => (
        <span
          key={i}
          className={`strip-cell strip-${c.status}`}
        />
      ))}
    </span>
  );
}
