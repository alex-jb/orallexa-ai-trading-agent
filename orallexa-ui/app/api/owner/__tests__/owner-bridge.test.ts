import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GET as status, POST as signIn, DELETE as signOut } from "../session/route";
import { GET as proxyGet, POST as proxyPost } from "../proxy/[...path]/route";
import { issueSession, OWNER_COOKIE, OWNER_TTL_SECONDS, validSession } from "../owner-auth";

const token = "a".repeat(64);
const uiOrigin = "https://orallexa-ui.example";
const context = (path: string) => ({ params: Promise.resolve({ path: path.split("/") }) });

function request(path: string, method = "GET", headers: Record<string, string> = {}, body?: BodyInit): Request {
  return new Request(`${uiOrigin}${path}`, { method, headers, body });
}

function withOwner(path: string, method = "GET", extraHeaders: Record<string, string> = {}, body?: BodyInit): Request {
  return request(path, method, {
    Cookie: `${OWNER_COOKIE}=${issueSession(token)}`,
    "X-Orallexa-UI": "1",
    ...(method === "POST" ? { Origin: uiOrigin } : {}),
    ...extraHeaders,
  }, body);
}

beforeEach(() => {
  vi.stubEnv("ORALLEXA_UI_OWNER_TOKEN", token);
  vi.stubEnv("ORALLEXA_UI_ORIGIN", uiOrigin);
  vi.stubEnv("ORALLEXA_API_KEY", "server-api-key");
  vi.stubEnv("ORALLEXA_SERVER_API_URL", "https://api.example");
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("owner session", () => {
  it("refuses to configure an absent or short token", async () => {
    vi.stubEnv("ORALLEXA_UI_OWNER_TOKEN", "short");
    expect((await status(request("/api/owner/session"))).status).toBe(503);
    expect((await signIn(request("/api/owner/session", "POST", { Origin: uiOrigin, "Content-Type": "application/json" }, JSON.stringify({ token: "short" })))).status).toBe(503);
  });

  it("rejects anonymous access and cross-site sign in", async () => {
    expect((await status(request("/api/owner/session"))).status).toBe(200);
    expect((await status(request("/api/owner/session"))).headers.get("vary")).toBe("*");
    expect(await (await status(request("/api/owner/session"))).json()).toMatchObject({ paperEnabled: false });
    const crossSite = request("/api/owner/session", "POST", { Origin: "https://attacker.example", "Content-Type": "application/json" }, JSON.stringify({ token }));
    expect((await signIn(crossSite)).status).toBe(403);
  });

  it("rejects wrong token and oversized login", async () => {
    const headers = { Origin: uiOrigin, "Content-Type": "application/json" };
    expect((await signIn(request("/api/owner/session", "POST", headers, JSON.stringify({ token: "b".repeat(64) })))).status).toBe(401);
    expect((await signIn(request("/api/owner/session", "POST", headers, JSON.stringify({ token: "é".repeat(64) })))).status).toBe(401);
    expect((await signIn(request("/api/owner/session", "POST", headers, JSON.stringify({ token: "x".repeat(300) })))).status).toBe(413);
  });

  it("issues a short HttpOnly Strict cookie and rejects tampering or expiry", async () => {
    const response = await signIn(request("/api/owner/session", "POST", { Origin: uiOrigin, "Content-Type": "application/json" }, JSON.stringify({ token })));
    expect(response.status).toBe(200);
    const setCookie = response.headers.get("set-cookie")!;
    expect(setCookie).toContain("HttpOnly");
    expect(setCookie.toLowerCase()).toContain("samesite=strict");
    expect(setCookie).toContain("Path=/api/owner");
    const cookie = setCookie.split(";")[0];
    expect((await status(request("/api/owner/session", "GET", { Cookie: cookie }))).status).toBe(200);
    expect(await (await status(request("/api/owner/session", "GET", { Cookie: cookie }))).json()).toMatchObject({ authenticated: true });
    expect(validSession(cookie.split("=")[1], token, Date.now() + OWNER_TTL_SECONDS * 1000 + 1000)).toBe(false);
    const signed = cookie.split("=")[1];
    expect(validSession(signed.slice(0, -1) + (signed.endsWith("0") ? "1" : "0"), token)).toBe(false);
    expect(validSession(cookie.split("=")[1], "b".repeat(64))).toBe(false);
  });

  it("requires same origin on logout", async () => {
    expect((await signOut(request("/api/owner/session", "DELETE", { Origin: "https://attacker.example" }))).status).toBe(403);
    const response = await signOut(request("/api/owner/session", "DELETE", { Origin: uiOrigin }));
    expect(response.headers.get("set-cookie")).toContain("Max-Age=0");
  });
});

describe("allowlisted owner relay", () => {
  it("keeps paper execution off until the server explicitly enables it", async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json({ status: "submitted" }));
    vi.stubGlobal("fetch", fetchMock);
    const form = new FormData(); form.append("ticker", "NVDA");
    const first = await proxyPost(withOwner("/api/owner/proxy/alpaca/execute", "POST", {}, form), context("alpaca/execute"));
    expect(first.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
    vi.stubEnv("ORALLEXA_ENABLE_PAPER_UI", "1");
    const enabled = await proxyPost(withOwner("/api/owner/proxy/alpaca/execute", "POST", {}, form), context("alpaca/execute"));
    expect(enabled.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("never forwards anonymous or forged-cookie broker and paid requests", async () => {
    const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
    expect((await proxyPost(request("/api/owner/proxy/alpaca/execute", "POST"), context("alpaca/execute"))).status).toBe(401);
    expect((await proxyGet(request("/api/owner/proxy/daily-intel", "GET", { Cookie: `${OWNER_COOKIE}=forged`, "X-Orallexa-UI": "1" }), context("daily-intel"))).status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("requires a custom header for read requests and a matching origin on writes", async () => {
    const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
    const noHeader = request("/api/owner/proxy/daily-intel", "GET", { Cookie: `${OWNER_COOKIE}=${issueSession(token)}` });
    expect((await proxyGet(noHeader, context("daily-intel"))).status).toBe(403);
    const crossSite = withOwner("/api/owner/proxy/alpaca/execute", "POST", { Origin: "https://attacker.example", "Content-Type": "multipart/form-data; boundary=foo" }, "--foo--");
    expect((await proxyPost(crossSite, context("alpaca/execute"))).status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("blocks arbitrary URLs, methods, query strings and redirects", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 302, headers: { Location: "https://attacker.example" } }));
    vi.stubGlobal("fetch", fetchMock);
    expect((await proxyGet(withOwner("/api/owner/proxy/x/tweet"), context("x/tweet"))).status).toBe(404);
    expect((await proxyGet(withOwner("/api/owner/proxy/alpaca/account?redirect=1"), context("alpaca/account"))).status).toBe(404);
    expect((await proxyPost(withOwner("/api/owner/proxy/alpaca/account", "POST"), context("alpaca/account"))).status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
    expect((await proxyGet(withOwner("/api/owner/proxy/alpaca/account"), context("alpaca/account"))).status).toBe(502);
  });

  it("injects only server key, strips browser headers and preserves SSE streaming", async () => {
    const body = new ReadableStream({ start(controller) { controller.enqueue(new TextEncoder().encode("event: done\ndata: {}\n\n")); controller.close(); } });
    const fetchMock = vi.fn().mockResolvedValue(new Response(body, { headers: { "Content-Type": "text/event-stream", "Set-Cookie": "upstream=secret" } }));
    vi.stubGlobal("fetch", fetchMock);
    const form = new FormData(); form.append("ticker", "NVDA");
    const req = withOwner("/api/owner/proxy/deep-analysis-stream", "POST", { "X-API-Key": "attacker-key" }, form);
    const response = await proxyPost(req, context("deep-analysis-stream"));
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("text/event-stream");
    expect(response.headers.get("set-cookie")).toBeNull();
    expect(response.headers.get("cache-control")).toContain("no-store");
    expect(await response.text()).toContain("event: done");
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][0]).toBe("https://api.example/api/deep-analysis-stream");
    const forwarded = fetchMock.mock.calls[0][1];
    expect(forwarded.headers["X-API-Key"]).toBe("server-api-key");
    expect(forwarded.headers.Origin).toBeUndefined();
    expect(forwarded.headers.Cookie).toBeUndefined();
    expect(forwarded.redirect).toBe("manual");
  });

  it("rejects oversized uploads, missing keys and insecure remote upstreams", async () => {
    const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("ORALLEXA_ENABLE_PAPER_UI", "1");
    const oversized = withOwner("/api/owner/proxy/alpaca/execute", "POST", { "Content-Type": "multipart/form-data; boundary=foo" }, "x".repeat(64 * 1024 + 1));
    expect((await proxyPost(oversized, context("alpaca/execute"))).status).toBe(413);
    vi.stubEnv("ORALLEXA_API_KEY", "");
    expect((await proxyGet(withOwner("/api/owner/proxy/alpaca/account"), context("alpaca/account"))).status).toBe(503);
    vi.stubEnv("ORALLEXA_API_KEY", "server-api-key");
    vi.stubEnv("ORALLEXA_SERVER_API_URL", "http://attacker.example");
    expect((await proxyGet(withOwner("/api/owner/proxy/alpaca/account"), context("alpaca/account"))).status).toBe(503);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
