import { NextResponse } from "next/server";

import { getCTFs } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const ctfs = await getCTFs();
    return NextResponse.json({
      ctfs,
      generatedAt: new Date().toISOString(),
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Failed to load CTFs.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
