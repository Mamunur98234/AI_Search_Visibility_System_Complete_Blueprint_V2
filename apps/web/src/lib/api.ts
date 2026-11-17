import type { components } from "./api-types";

export type Schemas = components["schemas"];

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public requestId?: string,
    public fieldErrors: Record<string, string> = {},
  ) {
    super(message);
  }
}

const CSRF_COOKIE = /(?:^|;\s*)(?:__Host-)?aisv_csrf=([^;]+)/;

async function csrfToken(): Promise<string> {
  const m = document.cookie.match(CSRF_COOKIE);
  if (m?.[1]) return decodeURIComponent(m[1]);
  const r = await fetch("/api/v1/auth/csrf", { credentials: "same-origin" });
  if (!r.ok) throw new ApiError(r.status, "The service is unavailable. Please try again shortly.");
  const body = (await r.json()) as { csrf_token: string };
  return body.csrf_token;
}

type Method = "GET" | "POST" | "PATCH" | "DELETE";

function describeValidation(errors: { loc: (string | number)[]; msg: string }[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const e of errors) {
    const field = e.loc.filter((p) => p !== "body").join(".") || "_";
    out[field] = e.msg.replace(/^Value error, /, "");
  }
  return out;
}

export async function api<T = unknown>(
  method: Method,
  path: string,
  body?: unknown,
  extraHeaders: Record<string, string> = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...extraHeaders };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = await csrfToken();
  const res = await fetch(`/api/v1${path}`, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = undefined;
  try {
    data = text ? JSON.parse(text) : undefined;
  } catch {
    data = undefined;
  }
  if (!res.ok) {
    const p = (data ?? {}) as { detail?: unknown; title?: string; request_id?: string; errors?: never[] };
    const fieldErrors = Array.isArray(p.errors) ? describeValidation(p.errors) : {};
    const message =
      typeof p.detail === "string"
        ? p.detail
        : Object.keys(fieldErrors).length
          ? "Please correct the highlighted fields."
          : (p.title ?? `Request failed (${res.status})`);
    if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/")) {
      window.dispatchEvent(new CustomEvent("aisv:unauthenticated"));
    }
    throw new ApiError(res.status, message, p.request_id, fieldErrors);
  }
  return data as T;
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return "Something went wrong.";
}
