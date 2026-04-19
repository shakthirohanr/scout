import { NextResponse } from "next/server";

import { getActiveImportStatus } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const progress = await getActiveImportStatus();
    return NextResponse.json(progress);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Failed to get import status.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
