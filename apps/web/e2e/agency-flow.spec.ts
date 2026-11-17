import { expect, test } from "@playwright/test";

import { PASSWORD, expectNoA11yViolations, lastEmailTo, signup, uniq } from "./helpers";

test("agency owner onboards a client, invites a scoped viewer, and the audit log records it", async ({ browser }) => {
  const id = uniq("acme");
  const ownerEmail = `${id}@owner.example`;
  const viewerEmail = `${id}@viewer.example`;

  const ownerCtx = await browser.newContext();
  const page = await ownerCtx.newPage();
  const cspErrors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" && /Content Security Policy/i.test(m.text())) cspErrors.push(m.text());
  });

  await signup(page, `Agency ${id}`, ownerEmail);
  await expectNoA11yViolations(page);

  // Disabled future modules are visible with their phase, not dead links.
  const nav = page.getByRole("navigation", { name: "Main" });
  await expect(nav.getByText("Technical audit")).toBeVisible();
  await expect(nav.getByText("Technical audit")).toHaveAttribute("aria-disabled", "true");
  await expect(nav.getByRole("link", { name: "Technical audit" })).toHaveCount(0);

  // Create two clients.
  await page.getByRole("link", { name: "Clients" }).click();
  await expect(page.getByText("No clients yet")).toBeVisible();
  for (const name of [`Visible ${id}`, `Hidden ${id}`]) {
    await page.getByRole("button", { name: "New client" }).click();
    await page.getByRole("dialog").getByLabel("Client name").fill(name);
    await page.getByRole("dialog").getByRole("button", { name: "Create client" }).click();
    await expect(page.getByRole("heading", { name })).toBeVisible();
    await page.getByRole("link", { name: "← Clients" }).click();
  }
  await page.getByRole("link", { name: `Visible ${id}` }).click();
  await expectNoA11yViolations(page);

  // Domain: invalid input shows a field error; valid input is normalized and listed as unverified.
  await page.getByRole("tab", { name: "Domains" }).click();
  await page.getByRole("button", { name: "Add" }).click();
  await page.getByLabel("Hostname").fill("https://bad.example/path");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(/bare hostname/i)).toBeVisible();
  await page.getByLabel("Hostname").fill(`WWW.${id}.example`);
  await page.getByLabel("Primary domain").check();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(`www.${id}.example`)).toBeVisible();
  await expect(page.getByText("unverified", { exact: true })).toBeVisible();

  // Brand with aliases.
  await page.getByRole("tab", { name: "Brands" }).click();
  await page.getByRole("button", { name: "Add" }).click();
  await page.getByLabel("Brand name").fill("Acme");
  await page.getByLabel("Aliases").fill("Acme Inc, ACME");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Aliases: Acme Inc, ACME")).toBeVisible();

  // Internal note with markup is shown as text, never executed.
  await page.getByRole("tab", { name: "Notes" }).click();
  await page.getByLabel("Add a note").fill('<img src=x onerror="window.__xss=1">');
  await page.getByRole("button", { name: "Add note" }).click();
  await expect(page.getByText('<img src=x onerror="window.__xss=1">')).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();

  // Invite a client viewer scoped to one client.
  await page.getByRole("link", { name: "Members" }).click();
  await page.getByRole("button", { name: "Invite member" }).click();
  const dlg = page.getByRole("dialog");
  await dlg.getByLabel("Email").fill(viewerEmail);
  await dlg.getByLabel("Role").selectOption("client_viewer");
  await dlg.getByLabel(`Visible ${id}`).check();
  await dlg.getByRole("button", { name: "Send invitation" }).click();
  await expect(page.getByRole("cell", { name: viewerEmail })).toBeVisible();
  await expectNoA11yViolations(page);

  // Viewer accepts in a separate browser context.
  const link = lastEmailTo(viewerEmail).body.match(/http:\/\/\S+\/invite#token=\S+/)?.[0];
  expect(link).toBeTruthy();
  const viewerCtx = await browser.newContext();
  const vp = await viewerCtx.newPage();
  await vp.goto(link!);
  await expect(vp.getByRole("heading", { name: `Join Agency ${id}` })).toBeVisible();
  expect(vp.url()).not.toContain("token="); // fragment removed from the address bar
  await vp.getByLabel("Your name").fill("Vic Viewer");
  await vp.getByLabel("Password").fill(PASSWORD);
  await vp.getByRole("button", { name: "Create account and join" }).click();
  await expect(vp.getByRole("heading", { name: "Overview" })).toBeVisible();

  await vp.getByRole("link", { name: "Clients" }).click();
  await expect(vp.getByRole("link", { name: `Visible ${id}` })).toBeVisible();
  await expect(vp.getByRole("link", { name: `Hidden ${id}` })).toHaveCount(0);
  await expect(vp.getByRole("button", { name: "New client" })).toBeDisabled();
  await vp.getByRole("link", { name: `Visible ${id}` }).click();
  await expect(vp.getByRole("tab", { name: "Notes" })).toHaveCount(0);
  await expect(vp.getByRole("link", { name: "Audit log" })).toHaveCount(0);

  // Owner sees the trail.
  await page.getByRole("link", { name: "Audit log" }).click();
  for (const action of ["member.joined", "member.invited", "note.created", "brand.created", "domain.created", "client.created"]) {
    await expect(page.getByRole("cell", { name: action }).first()).toBeVisible();
  }
  expect(cspErrors).toEqual([]);
  await ownerCtx.close();
  await viewerCtx.close();
});

test("login requires correct password, supports sign out, and protects app routes", async ({ page }) => {
  const email = `${uniq("login")}@owner.example`;
  await signup(page, "Login Agency", email);
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();

  await page.goto("/clients");
  await expect(page).toHaveURL(/\/login\?next=%2Fclients/);
  await expectNoA11yViolations(page);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("wrong password value");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.locator(".alert-error")).toContainText("Email or password is incorrect");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Clients" })).toBeVisible();
});

test("open redirect via next= is ignored", async ({ page }) => {
  const email = `${uniq("redir")}@owner.example`;
  await signup(page, "Redirect Agency", email);
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.goto("/login?next=//evil.example");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  expect(new URL(page.url()).host).toBe("localhost:3100");
});

test("pages send a nonce-based CSP and work at phone width without horizontal scroll", async ({ page }) => {
  const res = await page.goto("/login");
  const csp = res?.headers()["content-security-policy"] ?? "";
  expect(csp).toMatch(/script-src 'self' 'nonce-[^']+' 'strict-dynamic'/);
  expect(csp).toContain("frame-ancestors 'none'");
  expect(res?.headers()["x-frame-options"]).toBe("DENY");

  await page.setViewportSize({ width: 375, height: 800 });
  await signup(page, "Mobile Agency", `${uniq("mobile")}@owner.example`);
  for (const path of ["/", "/clients", "/settings/members", "/settings/audit-log", "/settings/security"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    expect(overflow, path).toBe(false);
  }
  await page.getByRole("button", { name: "Menu" }).click();
  await expect(page.getByRole("link", { name: "Clients" })).toBeVisible();
});
