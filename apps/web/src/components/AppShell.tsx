"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { NAV, ROLE_LABELS } from "@/lib/nav";
import { useSession } from "@/lib/session";

import { ToastRegion } from "./ui";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { me, can, logout, switchTenant } = useSession();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const active = me.active_tenant;

  const isCurrent = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href) || (href === "/domains" && pathname.startsWith("/crawls"));

  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <div className="shell">
        <nav id="sidebar" className={`sidebar ${open ? "open" : ""}`} aria-label="Main">
          <div className="brand">AI Search Visibility</div>
          {NAV.map((group) => (
            <div key={group.label}>
              <h2>{group.label}</h2>
              <ul>
                {group.items
                  .filter((i) => !i.perm || can(i.perm))
                  .map((item) =>
                    item.href ? (
                      <li key={item.label}>
                        <Link
                          href={item.href}
                          aria-current={isCurrent(item.href) ? "page" : undefined}
                          onClick={() => setOpen(false)}
                        >
                          {item.label}
                        </Link>
                      </li>
                    ) : (
                      <li key={item.label}>
                        <span className="nav-disabled" aria-disabled="true">
                          {item.label}
                          <span className="phase">
                            Phase {item.phase}
                            <span className="sr-only"> — not available yet</span>
                          </span>
                        </span>
                      </li>
                    ),
                  )}
              </ul>
            </div>
          ))}
        </nav>
        <div>
          <header className="topbar">
            <div className="row">
              <button
                className="btn menu-toggle"
                aria-expanded={open}
                aria-controls="sidebar"
                onClick={() => setOpen((o) => !o)}
              >
                Menu
              </button>
              {me.tenants.length > 1 ? (
                <label className="row">
                  <span className="sr-only">Workspace</span>
                  <select
                    value={active?.id ?? ""}
                    onChange={(e) => void switchTenant(e.target.value)}
                    aria-label="Switch workspace"
                  >
                    {me.tenants.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <strong>{active?.name ?? "No workspace"}</strong>
              )}
            </div>
            <div className="right">
              <span className="muted small">
                {me.name} · {active ? ROLE_LABELS[active.role] ?? active.role : "no role"}
              </span>
              <button className="btn" onClick={() => void logout()}>
                Sign out
              </button>
            </div>
          </header>
          <main id="main" className="content" tabIndex={-1}>
            {active ? (
              children
            ) : (
              <div className="state" role="alert">
                <strong>No active workspace</strong>
                <span>Your account is not a member of any active workspace. Ask an agency owner for an invitation.</span>
              </div>
            )}
          </main>
        </div>
      </div>
      <ToastRegion />
    </>
  );
}
