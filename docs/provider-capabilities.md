# Provider & Integration Capability Registry (initial)

Status: **Draft — UNVERIFIED.** Entries reflect general knowledge at design time. Before any
provider is enabled, an admin must re-check current documentation, terms of use, quotas and
pricing, record the review date, and update this registry. Nothing here is a claim that an
integration is implemented.

| Provider | Access method | Permitted use (to confirm) | Useful fields | Key limitations | Planned phase |
|---|---|---|---|---|---|
| Google Search Console | Official API (OAuth, `webmasters.readonly`) | Read data for properties the user has access to | Search Analytics (page, query, country, device, date; clicks, impressions, CTR, position); URL Inspection; sitemaps | Aggregated/anonymized queries omitted; row limits per request; ~16 months history; URL Inspection has daily per-property quota; OAuth app verification required for production | 3 |
| Google Analytics 4 | Official Data API (OAuth, `analytics.readonly`) | Read reports for authorized properties | Sessions, users, landing page, source/medium/channel, key events/conversions | Thresholding and sampling may apply; quota tokens per property; attribution settings are property-level | 3 |
| CSV import (GSC/GA4/other exports) | Customer upload | Customer-owned data | As exported | Unverified (`customer_import`); schema detection and validation required | 3 |
| OpenAI API | Official API key | Programmatic prompting under OpenAI terms | Answer text; web-search tool citations where used; model id; token usage | Not equivalent to ChatGPT consumer app output; results vary run to run | 4 |
| Anthropic API | Official API key | Programmatic prompting under Anthropic terms | Answer text; web search tool citations where used; model id; token usage | Not equivalent to Claude consumer app output | 4 |
| Google Gemini API | Official API key | Programmatic prompting under Google terms | Answer text; grounding metadata/citations when Search grounding enabled | Not equivalent to Google AI Overviews / AI Mode | 4 |
| Perplexity API | Official API key | Programmatic prompting under Perplexity terms | Answer text; citation URLs | Not equivalent to consumer app output | 4 |
| Google AI Overviews / AI Mode | **No official public API known** | — | — | Do **not** scrape. Only via a licensed third-party provider with documented methodology, or customer-supplied observations | 4 (import only) |
| Microsoft Copilot / ChatGPT consumer UI | **No permitted programmatic access assumed** | — | — | Do not automate consumer UIs. Import-only | 4 (import only) |
| Licensed AI-visibility data vendors | Vendor API/export under contract | Per contract | Vendor-defined | Labelled `third_party_estimate`; methodology disclosure required | 4+ (if contracted) |
| WordPress / CMS | Application passwords / REST API, staging first | Opt-in, least privilege | Posts/pages | Production writes disabled in MVP | Post-MVP |
| Email (notifications) | SMTP / transactional email API | Notifications to members only | — | No client-facing sends without approval | 1–5 |

## Registry fields (stored per provider in DB)

`key, name, access_method, docs_url, terms_url, terms_reviewed_at, reviewed_by, allowed_use,
supported_fields[], quotas(json), cost_model(json), regions[], data_retention_notes,
limitations[], enabled`
