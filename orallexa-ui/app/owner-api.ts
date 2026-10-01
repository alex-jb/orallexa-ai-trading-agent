/** Browser-side request for authenticated, allowlisted owner operations only. */
export function ownerFetch(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`/api/owner/proxy/${path}`, {
    ...init,
    credentials: "same-origin",
    cache: "no-store",
    headers: { ...init.headers, "X-Orallexa-UI": "1" },
  });
}
