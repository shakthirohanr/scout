import { NextResponse } from "next/server";

import { importCTF } from "@/lib/backend";
import type { ImportCTFInput } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as Partial<ImportCTFInput>;

    const name = body.name?.trim();
    const ctfdUrl = body.ctfdUrl?.trim();
    const authMode = body.authMode;

    if (!name || !ctfdUrl || !authMode) {
      return NextResponse.json(
        { error: "name, ctfdUrl, and authMode are required." },
        { status: 400 },
      );
    }

    const payload = await importCTF({
      name,
      ctfdUrl,
      authMode,
      token: body.token,
      username: body.username,
      password: body.password,
      challengesRoot: body.challengesRoot,
    });

    return NextResponse.json(payload);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Failed to import CTF.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
