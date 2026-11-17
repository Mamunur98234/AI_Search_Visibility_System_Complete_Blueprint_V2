# Phase 0 — Repository Audit

Date: 2026-11-17

## Findings

- Git branch `claude/new-session-b1bj7y` had **no commits**; the remote had **no branches**.
- No source code, README, manifests, environment examples, migrations, tests, deployment config or UI existed.
- Only inputs: `blueprint/Complete_Blueprint_V2.pdf` (10 pages) and `blueprint/Master_Coding_Prompt_V2.txt`.
- Build environment available: Docker 29, Node 22, Python 3.13, PostgreSQL 16, Redis 7.

## (A) Existing stack
None. Preferred stack from the blueprint is adopted without conflict — see `architecture.md`.

## (B) What works
Nothing. No feature may be claimed as working.

## (C) What is missing
All modules A–T, all screens, data model, auth/tenancy, crawler, integrations, provider layer,
reports, tests, documentation and deployment.

### Spec reconciliation
The PDF data model (§7) lists entities absent from the TXT prompt: Provider, Entity,
ObservationEvidence, CompetitorObservation, OAuthCredentialReference, ImportedDataset, AccessEvent,
DeletionRequest, Redirect, CanonicalRecord, SitemapRecord, StructuredDataRecord, PageMetric,
ContentGap, InternalLinkSuggestion, Comment, Attachment, SubscriptionPlan, ServicePackage.
`data-model.md` uses the **union** of both lists.

## (D) Risks
See `threat-model.md`. Headline risks:

1. **Measurement validity** — LLM API answers are not what consumer AI interfaces show users.
   Google AI Overviews / AI Mode have no official public API. Observations must be labelled
   "API-sampled" or "customer/licensed import", never "what users see".
2. **Crawler SSRF / DNS rebinding.**
3. **Cross-tenant data leakage** across DB, API, jobs, cache, storage, exports.
4. **Prompt injection** via crawled pages and provider responses.
5. **Google OAuth** sensitive scopes require app verification (lead time of weeks).
6. **Shared hosting** cannot reliably run Redis, workers or long crawls.
7. **Cost/abuse** of provider calls and crawls — quotas required from day one.

## (E) Plan
See `roadmap.md`.

## (F) Blocking questions
See `open-questions.md`.
