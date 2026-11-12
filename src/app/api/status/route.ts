import { NextResponse } from "next/server";
import { getStatus } from "@/lib/mock-engine";

// Всегда свежие данные, без кэширования
export const dynamic = "force-dynamic";

/** GET /api/status — текущий снимок всех устройств (без нового опроса) */
export async function GET() {
  return NextResponse.json(getStatus());
}
