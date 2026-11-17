import { randomBytes } from "node:crypto";

import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against the real stack: Next.js (production build) -> FastAPI -> PostgreSQL (RLS).
 * Prerequisites: the API virtualenv at ../api/.venv, and a migrated `aisv_e2e` database.
 * Emails are written to ../api/var/e2e-outbox (file backend) so tests can follow invitation links.
 */
const API_ENV = {
  APP_ENV: "test",
  DATABASE_URL: process.env.E2E_DATABASE_URL ?? "postgresql+psycopg://aisv_app:change-me-app@localhost:5432/aisv_e2e",
  REDIS_URL: process.env.E2E_REDIS_URL ?? "",
  // Fresh throwaway Fernet key per run (32 random bytes, url-safe base64).
  ENCRYPTION_KEYS: randomBytes(32).toString("base64").replace(/\+/g, "-").replace(/\//g, "_"),
  ALLOWED_ORIGINS: "http://localhost:3100",
  PUBLIC_WEB_URL: "http://localhost:3100",
  EMAIL_BACKEND: "file",
  EMAIL_FILE_DIR: "./var/e2e-outbox",
  LOGIN_RATE_LIMIT_PER_IP: "1000",
};

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:3100", trace: "off" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "../api/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8100",
      cwd: "../api",
      url: "http://127.0.0.1:8100/api/v1/healthz",
      env: API_ENV,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      // API_ORIGIN is baked into rewrites at build time, so the e2e server builds with its own origin.
      command: "npx next build && npx next start -p 3100",
      url: "http://localhost:3100/login",
      env: { API_ORIGIN: "http://127.0.0.1:8100", NEXT_TELEMETRY_DISABLED: "1", NEXT_DIST_DIR: ".next-e2e" },
      reuseExistingServer: false,
      timeout: 240_000,
    },
  ],
});
