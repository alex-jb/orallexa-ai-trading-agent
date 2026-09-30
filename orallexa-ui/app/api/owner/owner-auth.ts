import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";

export const OWNER_COOKIE = "orallexa_owner";
export const OWNER_TTL_SECONDS = 15 * 60;
export const PRIVATE_HEADERS = {
  "Cache-Control": "private, no-store, max-age=0",
  "Pragma": "no-cache",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  // Older deployed service workers cache successful /api/ GETs. Cache API
  // rejects responses with Vary: *, including during a rolling upgrade.
  "Vary": "*",
};

export function ownerSecret(): string | null {
  const secret = process.env.ORALLEXA_UI_OWNER_TOKEN;
  // A password or placeholder would be guessable on the public dashboard.
  return secret && /^[0-9a-f]{64}$/.test(secret) ? secret : null;
}

export function validOrigin(request: Request): boolean {
  const expected = process.env.ORALLEXA_UI_ORIGIN;
  if (!expected) return false;
  try {
    const parsed = new URL(expected);
    if (parsed.origin !== expected || (parsed.protocol !== "https:" &&
      !(process.env.NODE_ENV !== "production" && parsed.hostname === "localhost" && parsed.protocol === "http:"))) return false;
  } catch { return false; }
  return request.headers.get("origin") === expected;
}

function sign(secret: string, issuedAt: number, nonce: string): string {
  return createHmac("sha256", secret).update(`owner-v1:${issuedAt}:${nonce}`).digest("hex");
}

export function issueSession(secret: string, now = Date.now()): string {
  const issuedAt = Math.floor(now / 1000);
  const nonce = randomBytes(16).toString("hex");
  return `v1.${issuedAt}.${nonce}.${sign(secret, issuedAt, nonce)}`;
}

export function validSession(cookie: string | undefined, secret: string, now = Date.now()): boolean {
  if (!cookie || cookie.length > 150) return false;
  const parts = /^v1\.(\d{10})\.([0-9a-f]{32})\.([0-9a-f]{64})$/.exec(cookie);
  if (!parts) return false;
  const issuedAt = Number(parts[1]);
  const current = Math.floor(now / 1000);
  if (issuedAt > current || current - issuedAt >= OWNER_TTL_SECONDS) return false;
  return timingSafeEqual(Buffer.from(parts[3], "hex"), Buffer.from(sign(secret, issuedAt, parts[2]), "hex"));
}

export function cookieValue(request: Request): string | undefined {
  const cookies = request.headers.get("cookie") || "";
  const item = cookies.split(";").map(part => part.trim()).find(part => part.startsWith(`${OWNER_COOKIE}=`));
  return item?.slice(OWNER_COOKIE.length + 1);
}

export function ownerResponse(body: unknown, status = 200): Response {
  return Response.json(body, { status, headers: PRIVATE_HEADERS });
}

export async function limitedBody(request: Request, maxBytes: number): Promise<Uint8Array | null> {
  const declared = Number(request.headers.get("content-length") || "0");
  if (!Number.isFinite(declared) || declared > maxBytes) return null;
  const reader = request.body?.getReader();
  if (!reader) return new Uint8Array();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.length;
    if (total > maxBytes) { await reader.cancel(); return null; }
    chunks.push(value);
  }
  const result = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { result.set(chunk, offset); offset += chunk.length; }
  return result;
}
