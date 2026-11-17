export const VERIFICATION_TONE: Record<string, "ok" | "info" | "warn" | "neutral" | "bad"> = {
  verified: "ok",
  pending: "warn",
  unverified: "neutral",
  failed: "bad",
};

export const CRAWL_TONE: Record<string, "ok" | "info" | "warn" | "neutral" | "bad"> = {
  queued: "info",
  running: "info",
  paused: "warn",
  completed: "ok",
  cancelled: "neutral",
  failed: "bad",
};

export const SEVERITY_TONE: Record<string, "bad" | "warn" | "neutral" | "info"> = {
  high: "bad",
  medium: "warn",
  low: "neutral",
  info: "info",
};

export const SKIP_REASON_LABELS: Record<string, string> = {
  robots_disallowed: "Disallowed by robots.txt",
  page_cap_reached: "Page limit reached",
  depth_limit: "Beyond depth limit",
  cancelled: "Crawl cancelled",
  out_of_scope: "Outside the verified host",
  redirect_out_of_scope: "Redirects outside the verified host",
  blocked_ip: "Resolves to a non-public address (blocked)",
  blocked_port: "Non-standard port (blocked)",
  blocked_scheme: "Unsupported scheme",
  invalid_url: "Invalid URL",
  too_large: "Response larger than 5 MB",
  timeout: "Timed out",
  connection_error: "Connection failed",
  tls_error: "TLS / certificate error",
  dns_error: "DNS lookup failed",
  decode_error: "Invalid content encoding",
  too_many_redirects: "Too many redirects",
};

export const ROBOTS_LABELS: Record<string, string> = {
  parsed: "robots.txt found and applied",
  not_found_allow_all: "No robots.txt (4xx): all paths allowed",
  auth_disallow_all: "robots.txt requires authentication: nothing crawled",
  unreachable_disallow_all: "robots.txt unreachable (5xx/redirect away): nothing crawled",
};

export function pct(rate: number | null | undefined): string {
  if (rate === null || rate === undefined) return "No data";
  return `${(rate * 100).toFixed(1)}%`;
}
