import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

export const PASSWORD = "e2e passphrase long enough";
const OUTBOX = join(__dirname, "..", "..", "api", "var", "e2e-outbox");

export function uniq(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
}

/** Newest email to `to` from the API's file email backend (test-only). */
export function lastEmailTo(to: string): { subject: string; body: string } {
  const files = readdirSync(OUTBOX)
    .map((f) => join(OUTBOX, f))
    .sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs);
  for (const f of files) {
    const msg = JSON.parse(readFileSync(f, "utf8")) as { to: string; subject: string; body: string };
    if (msg.to === to) return msg;
  }
  throw new Error(`No email for ${to}`);
}

export async function signup(page: Page, agency: string, email: string, name = "E2E Owner") {
  await page.goto("/signup");
  await page.getByLabel("Agency name").fill(agency);
  await page.getByLabel("Your name").fill(name);
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
}

export async function expectNoA11yViolations(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`)).toEqual([]);
}
