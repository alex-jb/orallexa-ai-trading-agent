import { timingSafeEqual } from "node:crypto";
import { NextResponse } from "next/server";
import { cookieValue, issueSession, limitedBody, OWNER_COOKIE, OWNER_TTL_SECONDS, ownerResponse, ownerSecret, PRIVATE_HEADERS, validOrigin, validSession } from "../owner-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  const secret = ownerSecret();
  if (!secret) return ownerResponse({ authenticated: false, configured: false }, 503);
  return ownerResponse({ authenticated: validSession(cookieValue(request), secret), configured: true,
    paperEnabled: process.env.ORALLEXA_ENABLE_PAPER_UI === "1" });
}

export async function POST(request: Request): Promise<Response> {
  const secret = ownerSecret();
  if (!secret) return ownerResponse({ error: "Owner access is not configured" }, 503);
  if (!validOrigin(request) || request.headers.get("content-type") !== "application/json") {
    return ownerResponse({ error: "Invalid origin or content type" }, 403);
  }
  const body = await limitedBody(request, 256);
  if (!body) return ownerResponse({ error: "Request too large" }, 413);
  let candidate: unknown;
  try { candidate = JSON.parse(new TextDecoder().decode(body)).token; } catch { return ownerResponse({ error: "Invalid request" }, 400); }
  const presented = typeof candidate === "string" ? Buffer.from(candidate) : Buffer.alloc(0);
  const expected = Buffer.from(secret);
  if (presented.length !== expected.length || !timingSafeEqual(presented, expected)) {
    return ownerResponse({ error: "Invalid owner token" }, 401);
  }
  const response = NextResponse.json({ authenticated: true, paperEnabled: process.env.ORALLEXA_ENABLE_PAPER_UI === "1" }, { headers: PRIVATE_HEADERS });
  response.cookies.set(OWNER_COOKIE, issueSession(secret), {
    httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "strict",
    path: "/api/owner", maxAge: OWNER_TTL_SECONDS,
  });
  return response;
}

export async function DELETE(request: Request): Promise<Response> {
  if (!validOrigin(request)) return ownerResponse({ error: "Invalid origin" }, 403);
  const response = NextResponse.json({ authenticated: false }, { headers: PRIVATE_HEADERS });
  response.cookies.set(OWNER_COOKIE, "", {
    httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "strict",
    path: "/api/owner", maxAge: 0,
  });
  return response;
}
