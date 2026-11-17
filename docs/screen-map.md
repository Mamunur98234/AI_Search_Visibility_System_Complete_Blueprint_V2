# Screen Map

Status: **Proposed (Phase 0)**. "Phase" = when the screen becomes functional. Before that phase the
nav item is visible but **disabled with a tooltip** ("Available in Phase N") — never a dead link.

| # | Screen | Route | Primary roles | Key content | Phase |
|---|---|---|---|---|---|
| 1 | Agency overview | `/` | Agency Owner/Admin, AM | Clients, open tasks, pending approvals, recent crawls, integration health | 1 (shell), filled progressively |
| 2 | Client list | `/clients` | Agency roles | Search/filter, status, owner, renewal | 1 |
| 3 | Client overview | `/clients/:id` | Agency roles, Client Admin | Brands, domains, projects, competitors, contacts, notes | 1 |
| 4 | Onboarding / domain verification | `/clients/:id/onboarding` | AM, Analyst | Checklist; DNS/meta/file verification instructions + check | 2 |
| 5 | Technical audit workspace | `/projects/:id/audit` | Analyst, Implementer | Crawl jobs (pause/cancel), issue table by rule with affected/eligible, page evidence drawer | 2 |
| 6 | Search integrations | `/clients/:id/integrations` | AM, Analyst | Connect GSC/GA4, sync status, CSV import with validation report | 3 |
| 7 | AI visibility explorer | `/projects/:id/visibility` | Analyst, AM, Client | Metrics with denominators + scope bar; run list; observation detail with mentions/citations | 4 |
| 8 | Prompt-set manager | `/projects/:id/prompt-sets` | Analyst | Sets, versions, prompts by topic/intent/funnel/persona, schedule, budget | 4 |
| 9 | Brand/competitor comparison | `/projects/:id/competitors` | Analyst, AM, Client | Same-sample presence, citations, cited domains, topic coverage | 4 |
| 10 | Content inventory / opportunities | `/projects/:id/content` | Analyst, Editor | Page-topic map, gaps, briefs | 6 (inventory partly 3) |
| 11 | Recommendations / task board | `/projects/:id/tasks` | All agency roles | Kanban + table; evidence links; owner/due | 5 |
| 12 | Approval center | `/approvals` | AM, Client Admin | Pending approvals, decision with note, history | 5 |
| 13 | Verification history | `/projects/:id/verification` | Analyst, Implementer | Before/after evidence per change | 6 |
| 14 | Report center / client portal | `/clients/:id/reports`, `/portal` | AM, Client roles | Draft → review → issue; PDF; methodology appendix | 5 |
| 15 | Integrations / provider capabilities | `/settings/providers` | Agency Owner/Admin | Registry, terms review, keys (write-only), budgets | 4 |
| 16 | Roles / security / retention / branding | `/settings/*` | Agency Owner/Admin, Auditor (read) | Members, invitations, roles, MFA policy, audit log, retention, branding | 1 (members/audit log), 7 (branding) |

## Required states per screen
Empty (with next-step CTA), loading (skeleton, `aria-busy`), error (message + retry + request id),
success (toast with `role="status"`), permission-denied (explains which role is needed).

## Metric display contract
Every number renders inside a `MetricCard`/`MetricCell` with a "scope bar":
`n = 120 eligible runs · 3 providers · 2026-10-01→10-31 · US/en · Prompt set "SaaS buyers" v3 · observed sample`.
Clicking opens the provenance drawer (source, method, timestamps, exclusions).
