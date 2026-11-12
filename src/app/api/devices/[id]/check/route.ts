import { NextResponse } from "next/server";
import { checkOne } from "@/lib/mock-engine";

export const dynamic = "force-dynamic";

/** POST /api/devices/:id/check — внеплановая проверка одного узла */
export async function POST(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const device = checkOne(id);
  if (!device) return NextResponse.json({ error: "Устройство не найдено" }, { status: 404 });
  return NextResponse.json(device);
}
