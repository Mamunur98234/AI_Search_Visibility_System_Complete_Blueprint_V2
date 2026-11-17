export type NavItem = { label: string; href?: string; phase?: number; perm?: string };
export type NavGroup = { label: string; items: NavItem[] };

/** Modules not yet built are listed with their phase and rendered disabled — never as dead links. */
export const NAV: NavGroup[] = [
  {
    label: "Agency",
    items: [
      { label: "Overview", href: "/" },
      { label: "Clients", href: "/clients", perm: "client.read" },
      { label: "Approval center", phase: 5 },
    ],
  },
  {
    label: "Work",
    items: [
      { label: "Domain verification", phase: 2 },
      { label: "Technical audit", phase: 2 },
      { label: "Search integrations", phase: 3 },
      { label: "AI visibility explorer", phase: 4 },
      { label: "Prompt sets", phase: 4 },
      { label: "Competitor comparison", phase: 4 },
      { label: "Recommendations & tasks", phase: 5 },
      { label: "Reports", phase: 5 },
      { label: "Content & opportunities", phase: 6 },
      { label: "Verification history", phase: 6 },
    ],
  },
  {
    label: "Settings",
    items: [
      { label: "Members", href: "/settings/members", perm: "member.read" },
      { label: "Audit log", href: "/settings/audit-log", perm: "audit_log.read" },
      { label: "Workspace", href: "/settings/workspace", perm: "tenant.read" },
      { label: "Security", href: "/settings/security" },
      { label: "Providers", phase: 4 },
      { label: "Branding", phase: 7 },
    ],
  },
];

export const ROLE_LABELS: Record<string, string> = {
  agency_owner: "Agency Owner",
  agency_admin: "Agency Admin",
  account_manager: "Account Manager",
  seo_analyst: "SEO/AEO Analyst",
  content_editor: "Content Editor",
  technical_implementer: "Technical Implementer",
  client_admin: "Client Admin",
  client_viewer: "Client Viewer",
  auditor: "Auditor (read-only)",
};

export const TENANT_SCOPED_ROLES = new Set(["agency_owner", "agency_admin", "auditor"]);

export const STATUS_TONE: Record<string, "ok" | "info" | "warn" | "neutral"> = {
  active: "ok",
  onboarding: "info",
  paused: "warn",
  archived: "neutral",
  completed: "neutral",
};
