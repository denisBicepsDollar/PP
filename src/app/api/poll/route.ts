import { NextResponse } from "next/server";
import { pollAll } from "@/lib/mock-engine";

export const dynamic = "force-dynamic";

/**
 * POST /api/poll — выполнить раунд опроса всех включённых узлов
 * и вернуть обновлённый снимок. Клиент вызывает этот роут по таймеру
 * (интервал автообновления) и по кнопке «Проверить все».
 */
export async function POST() {
  return NextResponse.json(pollAll());
}
