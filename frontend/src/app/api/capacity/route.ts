import { NextResponse } from "next/server";

import { BackendRequestError, getCapacity } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const capacity = await getCapacity();
    return NextResponse.json(capacity);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Failed to fetch capacity.";
    const status = error instanceof BackendRequestError ? error.status : 500;
    return NextResponse.json({ error: message }, { status });
  }
}
