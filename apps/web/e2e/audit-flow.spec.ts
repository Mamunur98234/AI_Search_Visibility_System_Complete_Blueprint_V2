import { expect, test } from "@playwright/test";

import { expectNoA11yViolations, signup, uniq } from "./helpers";

const SITE_CONTROL = "http://127.0.0.1:8199/__publish-verification";

test("verify a domain, crawl it, review evidence-backed findings and triage one", async ({ page, request }) => {
  test.setTimeout(90_000);
  const id = uniq("audit");
  await signup(page, `Audit Agency ${id}`, `${id}@owner.example`);

  await page.getByRole("link", { name: "Clients" }).click();
  await page.getByRole("button", { name: "New client" }).click();
  await page.getByRole("dialog").getByLabel("Client name").fill(`Shop ${id}`);
  await page.getByRole("dialog").getByRole("button", { name: "Create client" }).click();
  await page.getByRole("tab", { name: "Domains" }).click();
  await page.getByRole("button", { name: "Add" }).click();
  await page.getByLabel("Hostname").fill("site.example");
  await page.getByRole("button", { name: "Save" }).click();
  await page.getByRole("link", { name: "site.example" }).click();

  // Verification: request instructions, fail first, publish the proof, then succeed.
  await expect(page.getByRole("heading", { name: "Verify ownership" })).toBeVisible();
  await page.getByLabel("Method").selectOption("well_known");
  await page.getByRole("button", { name: "Get instructions" }).click();
  const token = (await page.locator("dd code").filter({ hasText: /^aisv-/ }).first().textContent())!.trim();
  expect(token).toMatch(/^aisv-[0-9a-f]{32}$/);
  await page.getByRole("button", { name: "Check now" }).click();
  await expect(page.getByText(/does not contain the expected token/)).toBeVisible();
  await expectNoA11yViolations(page);
  const pub = await request.post(SITE_CONTROL, { data: token });
  expect(pub.status()).toBe(204);
  await page.getByRole("button", { name: "Check now" }).click();
  await expect(page.getByText("verified", { exact: true })).toBeVisible();

  // Crawl.
  // 300 ms between requests keeps the crawl running while the page polls, exercising the live
  // running -> completed transition (regression: findings panel crashed on that transition).
  await page.getByLabel("Delay between requests (ms)").fill("300");
  await page.getByRole("button", { name: "Start crawl" }).click();
  await expect(page.getByRole("heading", { name: "Crawl of site.example" })).toBeVisible();
  await expect(page.getByText("Findings appear when the crawl completes")).toBeVisible();
  await expect(page.getByText("completed", { exact: true }).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("robots.txt found and applied")).toBeVisible();

  // Findings with denominators, provenance and "No data" never shown as 0%.
  await expect(page.getByLabel("Data provenance")).toContainText("first party verified");
  const brokenRow = page.getByRole("row", { name: /Pages linking to broken internal URLs/ });
  await expect(brokenRow.getByRole("cell").nth(2)).toHaveText("2");
  await expect(brokenRow.getByRole("cell").nth(3)).toHaveText("4");
  await expect(brokenRow.getByRole("cell").nth(4)).toHaveText("50.0%");
  await expectNoA11yViolations(page);
  await brokenRow.getByRole("button", { name: /View 2 affected URLs/ }).click();
  const issues = page.getByRole("region", { name: "Pages linking to broken internal URLs" });
  await expect(issues.getByText("http://site.example/broken").first()).toBeVisible();

  // Triage.
  await issues.getByRole("button", { name: "Triage" }).first().click();
  await issues.getByLabel("Status").selectOption("wont_fix");
  await issues.getByLabel("Note").fill("Legacy URL, will redirect later");
  await issues.getByRole("button", { name: "Save" }).click();
  await expect(issues.getByText("Legacy URL, will redirect later")).toBeVisible();

  // Page log shows skip reasons; robots.txt is shown verbatim as text.
  await page.getByRole("tab", { name: "Pages" }).click();
  await page.getByLabel("State").selectOption("skipped");
  await expect(page.getByText("Disallowed by robots.txt")).toBeVisible();
  await page.getByLabel("State").selectOption("error");
  await expect(page.getByText("Response larger than 5 MB")).toBeVisible();
  await page.getByRole("tab", { name: "robots.txt" }).click();
  await expect(page.getByText("Disallow: /private")).toBeVisible();

  // Domains list reflects state; audit log has the trail.
  await page.getByRole("link", { name: "Domains & audits" }).click();
  await expect(page.getByRole("row", { name: /site\.example/ }).getByText("completed")).toBeVisible();
  await page.getByRole("link", { name: "Audit log" }).click();
  for (const action of ["issue.updated", "crawl.started", "domain.verified", "domain.verification_failed"]) {
    await expect(page.getByRole("cell", { name: action }).first()).toBeVisible();
  }
});

test("public bot page explains the crawler", async ({ page }) => {
  await page.goto("/bot");
  await expect(page.getByRole("heading", { name: "About AISVBot" })).toBeVisible();
  await expect(page.getByText("Obeys robots.txt")).toBeVisible();
});
