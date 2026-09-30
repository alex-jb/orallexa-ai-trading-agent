import { cookieValue, limitedBody, ownerResponse, ownerSecret, PRIVATE_HEADERS, validOrigin, validSession } from "../../owner-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// The browser cannot select arbitrary upstream paths, origins or methods.
const GET_PATHS = new Set(["alpaca/account", "alpaca/positions", "daily-intel"]);
const POST_PATHS = new Set(["alpaca/execute", "deep-analysis-stream", "chart-analysis", "scenario", "daily-intel/refresh", "analyze"]);

function upstreamOrigin(): string | null {
  const configured = process.env.ORALLEXA_SERVER_API_URL;
  if (!configured) return null;
  try {
    const parsed = new URL(configured);
    if (parsed.origin !== configured || parsed.username || parsed.password ||
        (parsed.protocol !== "https:" && !(process.env.ORALLEXA_ALLOW_HTTP_UPSTREAM === "1" && parsed.protocol === "http:"))) return null;
    return parsed.origin;
  } catch { return null; }
}

async function proxy(request: Request, context: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const secret = ownerSecret();
  const apiKey = process.env.ORALLEXA_API_KEY?.trim();
  const upstream = upstreamOrigin();
  if (!secret || !apiKey || !upstream) return ownerResponse({ error: "Owner bridge is not configured" }, 503);
  if (!validSession(cookieValue(request), secret)) return ownerResponse({ error: "Owner session required" }, 401);
  if (request.headers.get("x-orallexa-ui") !== "1" ||
      (request.method !== "GET" && !validOrigin(request))) {
    return ownerResponse({ error: "Invalid request origin" }, 403);
  }
  const { path } = await context.params;
  const target = path.join("/");
  const allowed = request.method === "GET" ? GET_PATHS : POST_PATHS;
  if (!allowed.has(target) || new URL(request.url).search) return ownerResponse({ error: "Unsupported operation" }, 404);
  if (target === "alpaca/execute" && process.env.ORALLEXA_ENABLE_PAPER_UI !== "1") {
    return ownerResponse({ error: "Paper execution is disabled" }, 403);
  }

  const headers: Record<string, string> = { "X-API-Key": apiKey };
  let body: Uint8Array | undefined;
  if (request.method === "POST") {
    const contentType = request.headers.get("content-type") || "";
    if (!/^multipart\/form-data; boundary=[\w'()+,./:=?-]+$/i.test(contentType)) {
      return ownerResponse({ error: "Expected form data" }, 415);
    }
    const limited = await limitedBody(request, target === "chart-analysis" ? 10 * 1024 * 1024 : 64 * 1024);
    if (!limited) return ownerResponse({ error: "Request too large" }, 413);
    body = limited;
    headers["Content-Type"] = contentType;
  }
  try {
    const response = await fetch(`${upstream}/api/${target}`, {
      method: request.method, headers, body: body as BodyInit | undefined,
      redirect: "manual", cache: "no-store", signal: request.signal,
    });
    if (response.status >= 300 && response.status < 400) {
      await response.body?.cancel();
      return ownerResponse({ error: "Upstream redirect blocked" }, 502);
    }
    return new Response(response.body, {
      status: response.status,
      headers: { ...PRIVATE_HEADERS, "Content-Type": response.headers.get("content-type") || "application/json" },
    });
  } catch {
    return ownerResponse({ error: "API unavailable" }, 502);
  }
}

export async function GET(request: Request, context: { params: Promise<{ path: string[] }> }): Promise<Response> {
  return proxy(request, context);
}

export async function POST(request: Request, context: { params: Promise<{ path: string[] }> }): Promise<Response> {
  return proxy(request, context);
}
