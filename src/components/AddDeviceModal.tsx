"use client";

import { useState } from "react";
import type { AddDeviceInput } from "@/lib/types";
import { IconX } from "./Icons";

interface Props {
  onClose: () => void;
  onAdd: (input: AddDeviceInput) => Promise<void>;
}

const TYPES = ["Коммутатор", "Маршрутизатор", "Сервер", "Шлюз", "Точка доступа", "Принтер", "Внешний узел", "Устройство"];
const GROUPS = ["Сеть", "Серверы", "Внешние", "Периферия"];

export function AddDeviceModal({ onClose, onAdd }: Props) {
  const [form, setForm] = useState<AddDeviceInput>({
    name: "",
    host: "",
    port: 80,
    type: "Устройство",
    group: "Сеть",
  });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      await onAdd(form);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось добавить устройство");
    } finally {
      setSaving(false);
    }
  }

  const set = <K extends keyof AddDeviceInput>(key: K, value: AddDeviceInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <div className="modal-head">
          <h2>Добавить устройство</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Закрыть">
            <IconX />
          </button>
        </div>

        <label className="field">
          <span>Название</span>
          <input
            required
            placeholder="Например, Коммутатор доступа, каб. 204"
            value={form.name}
            onChange={(e) => set("name", e.target.value)}
          />
        </label>

        <div className="field-row">
          <label className="field field-grow">
            <span>Адрес (IP или хост)</span>
            <input
              required
              placeholder="192.168.10.100 или srv01.local"
              value={form.host}
              onChange={(e) => set("host", e.target.value)}
            />
          </label>
          <label className="field">
            <span>Порт</span>
            <input
              required
              type="number"
              min={1}
              max={65535}
              value={form.port}
              onChange={(e) => set("port", Number(e.target.value))}
            />
          </label>
        </div>

        <div className="field-row">
          <label className="field field-grow">
            <span>Тип устройства</span>
            <select value={form.type} onChange={(e) => set("type", e.target.value)}>
              {TYPES.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </label>
          <label className="field field-grow">
            <span>Группа</span>
            <select value={form.group} onChange={(e) => set("group", e.target.value)}>
              {GROUPS.map((g) => (
                <option key={g}>{g}</option>
              ))}
            </select>
          </label>
        </div>

        {error && <p className="form-error">{error}</p>}

        <div className="modal-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Отмена
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? "Добавляем…" : "Добавить и проверить"}
          </button>
        </div>
      </form>
    </div>
  );
}
