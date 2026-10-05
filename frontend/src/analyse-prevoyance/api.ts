// @ts-nocheck
import { apiBaseUrl } from "@/lib/api";

export function analyseUrl(path: string): string {
  const base = String(apiBaseUrl || "").replace(/\/$/, "");
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return `${base}/analyses-prevoyance${suffix}`;
}

export async function analyseFetch(path: string, init: RequestInit = {}) {
  const headers = { ...(init.headers || {}) };
  if (init.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  return fetch(analyseUrl(path), {
    ...init,
    credentials: "include",
    headers,
  });
}
