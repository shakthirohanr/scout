import { NextResponse } from "next/server";

import { BackendRequestError, getCTFImportStatus } from "@/lib/backend";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{
    id: string;
  }>;
};

export async function GET(_request: Request, context: RouteContext) {
  try {
    const { id } = await context.params;
    const ctfId = Number.parseInt(id?.trim() ?? "", 10);

    if (!Number.isFinite(ctfId) || ctfId <= 0) {
      return NextResponse.json({ error: "valid ctf id is required." }, { status: 400 });
    }

    const progress = await getCTFImportStatus(ctfId);
    return NextResponse.json(progress);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Failed to get import status.";
    const status = error instanceof BackendRequestError ? error.status : 500;
    return NextResponse.json({ error: message }, { status });
  }
}
