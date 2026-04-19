import { NextResponse } from "next/server";

import { BackendRequestError, cancelRun } from "@/lib/backend";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{
    id: string;
  }>;
};

export async function POST(_request: Request, context: RouteContext) {
  try {
    const { id } = await context.params;
    const runId = id?.trim();
    if (!runId) {
      return NextResponse.json({ error: "run id is required." }, { status: 400 });
    }

    const result = await cancelRun(runId);
    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Failed to cancel run.";
    const status = error instanceof BackendRequestError ? error.status : 500;
    return NextResponse.json({ error: message }, { status });
  }
}
