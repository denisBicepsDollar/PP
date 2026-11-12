import { NextResponse } from "next/server";
import { addDevice } from "@/lib/mock-engine";
import type { AddDeviceInput } from "@/lib/types";

export const dynamic = "force-dynamic";

/** POST /api/devices — добавить устройство в список мониторинга */
export async function POST(req: Request) {
  let body: Partial<AddDeviceInput>;
  try {
    body = (await req.json()) as Partial<AddDeviceInput>;
  } catch {
    return NextResponse.json({ error: "Некорректный JSON" }, { status: 400 });
  }

  const name = typeof body.name === "string" ? body.name.trim() : "";
  const host = typeof body.host === "string" ? body.host.trim() : "";
  const port = Number(body.port);

  if (!name || !host) {
    return NextResponse.json(
      { error: "Заполните имя устройства и адрес (IP или хост)" },
      { status: 400 },
    );
  }
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    return NextResponse.json(
      { error: "Порт должен быть целым числом от 1 до 65535" },
      { status: 400 },
    );
  }

  const device = addDevice({
    name,
    host,
    port,
    type: typeof body.type === "string" ? body.type : "Устройство",
    group: typeof body.group === "string" ? body.group : "Сеть",
  });
  return NextResponse.json(device, { status: 201 });
}
