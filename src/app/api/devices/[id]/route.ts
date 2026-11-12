import { NextResponse } from "next/server";
import { removeDevice, setEnabled } from "@/lib/mock-engine";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ id: string }> };

/** PATCH /api/devices/:id — включить/отключить мониторинг узла */
export async function PATCH(req: Request, { params }: Ctx) {
  const { id } = await params;
  let body: { enabled?: unknown };
  try {
    body = (await req.json()) as { enabled?: unknown };
  } catch {
    return NextResponse.json({ error: "Некорректный JSON" }, { status: 400 });
  }
  if (typeof body.enabled !== "boolean") {
    return NextResponse.json({ error: "Поле enabled должно быть boolean" }, { status: 400 });
  }
  const device = setEnabled(id, body.enabled);
  if (!device) return NextResponse.json({ error: "Устройство не найдено" }, { status: 404 });
  return NextResponse.json(device);
}

/** DELETE /api/devices/:id — удалить устройство из списка */
export async function DELETE(_req: Request, { params }: Ctx) {
  const { id } = await params;
  const ok = removeDevice(id);
  if (!ok) return NextResponse.json({ error: "Устройство не найдено" }, { status: 404 });
  return NextResponse.json({ ok: true });
}
