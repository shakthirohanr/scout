import { NextResponse } from "next/server";

import { BackendRequestError, deleteCTF } from "@/lib/backend";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{
    id: string;
  }>;
};

export async function DELETE(_request: Request, context: RouteContext) {
  try {
    const { id } = await context.params;
    const ctfId = Number.parseInt(id?.trim() ?? "", 10);

    if (!Number.isFinite(ctfId) || ctfId <= 0) {
      return NextResponse.json({ error: "valid ctf id is required." }, { status: 400 });
    }

    const payload = await deleteCTF(ctfId);
    return NextResponse.json(payload);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Failed to delete CTF.";
    const status = error instanceof BackendRequestError ? error.status : 500;
    return NextResponse.json({ error: message }, { status });
  }
}
