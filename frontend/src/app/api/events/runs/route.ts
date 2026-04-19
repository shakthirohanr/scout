export const dynamic = "force-dynamic";

const BACKEND_URL = process.env.BACKEND_API_URL?.trim() || "http://127.0.0.1:8081";

export async function GET() {
  const backendUrl = `${BACKEND_URL}/api/v1/events/runs`;

  const response = await fetch(backendUrl, {
    cache: "no-store",
    headers: {
      Accept: "text/event-stream",
    },
  });

  if (!response.ok) {
    return new Response(
      JSON.stringify({ error: `Backend SSE failed: ${response.status}` }),
      { status: response.status, headers: { "Content-Type": "application/json" } },
    );
  }

  const stream = response.body;
  if (!stream) {
    return new Response(
      JSON.stringify({ error: "No stream body from backend" }),
      { status: 502, headers: { "Content-Type": "application/json" } },
    );
  }

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
