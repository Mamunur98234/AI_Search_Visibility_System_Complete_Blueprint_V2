# Data Model

Status: **Proposed (Phase 0)**. Union of Blueprint §7 and Master Prompt entity lists.

## Conventions

- PK `id` UUIDv7. Timestamps `created_at`, `updated_at` (UTC, `timestamptz`). Soft delete `deleted_at` where retention rules require.
- **T** = tenant-owned: non-null `tenant_id` FK → `tenant.id`, RLS enabled, every index leads with `tenant_id`.
- **G** = global (platform-managed reference data, no tenant data).
- Child rows repeat `tenant_id` (denormalized) so RLS and indexes never require joins; a composite
  FK `(tenant_id, parent_id) → parent(tenant_id, id)` guarantees a child cannot point at another tenant's parent.
- Enumerations are Postgres enums or check constraints, listed below.
- Every measured value either stores or references a `data_provenance` row.

## Provenance (cross-cutting)

| Entity | Own | Key fields |
|---|---|---|
| DataSource | T | kind (`crawler`,`gsc`,`ga4`,`csv_import`,`ai_provider`,`licensed_provider`,`manual`), integration_connection_id?, name |
| DataProvenance | T | data_source_id, method, scope (json: domain/market/locale/date range/sample ids), collected_at, period_start, period_end, **confidence_label**, sample_size?, notes, reviewed_by?, reviewed_at? |

`confidence_label` enum: `first_party_verified`, `customer_import`, `public_observation`,
`observed_sample`, `third_party_estimate`, `ai_extracted_unverified`, `analyst_reviewed`.

## Identity, tenancy, access

| Entity | Own | Key fields / notes |
|---|---|---|
| Tenant | G | name, slug, status, plan_id, data_region, settings(json: require_mfa, retention defaults) |
| Agency | T | 1:1 with tenant initially (branding, legal name, contact). Kept separate for future multi-agency tenants |
| User | G | email (citext unique), password_hash, mfa_secret_enc?, status, last_login_at. Users are global; access via memberships |
| Membership | T | user_id, role_id, status, invited_by. Unique (tenant_id, user_id) |
| Role | G/T | key, name, is_system. System roles global; custom roles per tenant (Phase 7) |
| Permission | G | key (`client.read` …), description |
| RolePermission | G/T | role_id, permission_id |
| AccessGrant | T | membership_id, client_id?, project_id? — narrows scope for client/project-level roles |
| Invitation | T | email, role_id, token_hash, expires_at, accepted_at, grants(json) |
| Session | G | user_id, active_tenant_id, token_hash, ip, user_agent, expires_at, revoked_at |
| AccessEvent | T | user_id, kind (login, logout, mfa_fail, export, break_glass), ip, ua |
| AuditLog | T | actor_user_id, action, object_type, object_id, before/after (json, secrets redacted), ip, request_id. Append-only (no UPDATE/DELETE grant) |

## CRM (Module A)

| Entity | Own | Key fields |
|---|---|---|
| Client | T | name, industry, status, owner_membership_id, renewal_date, plan/service_package_id |
| Contact | T | client_id, name, email, role, is_approver |
| Project | T | client_id, name, goals(json), start/end, status |
| Brand | T | client_id, name, aliases[] (for mention matching), products(json) |
| Entity | T | brand_id?, kind (person, product, organization), name, aliases[], same_as_urls[] |
| Domain | T | client_id, hostname, is_primary, verification_method, verification_token_hash, verified_at, scope_rules(json) |
| Market | G | country code, region |
| Language | G | BCP-47 code |
| ProjectMarket | T | project_id, market_id, language_id |
| Competitor | T | project_id, name, domains[], aliases[] |
| Note | T | object_type, object_id, body, author |
| SubscriptionPlan | G | key, limits(json) — Phase 7 |
| ServicePackage | T | name, deliverables(json), price? — agency's offering to clients |
| OnboardingChecklist / OnboardingItem | T | client_id, item, status, completed_by |

## Crawl & technical audit (Modules B, C, K)

| Entity | Own | Key fields |
|---|---|---|
| CrawlJob | T | domain_id, status (`queued`,`running`,`paused`,`cancelled`,`completed`,`failed`), limits(json), robots_snapshot, started/finished, counts |
| CrawlPage | T | crawl_job_id, url, url_hash, final_url, status_code, content_type, bytes, depth, fetched_at, title, meta_description, h1[], canonical, robots_meta, x_robots_tag, lang, word_count, content_hash, text_object_key |
| CrawlSkip | T | crawl_job_id, url, reason (`robots`,`out_of_scope`,`too_large`,`content_type`,`blocked_ip`,`timeout`,`error`,`cap_reached`), detail |
| Redirect | T | crawl_page_id, hop, from_url, to_url, status_code |
| CanonicalRecord | T | crawl_page_id, declared, resolved, is_self, conflict |
| SitemapRecord | T | crawl_job_id, sitemap_url, url, lastmod |
| PageLink | T | crawl_job_id, from_page_id, to_url, anchor_text, is_internal, nofollow, target_status |
| StructuredDataRecord | T | crawl_page_id, format (json-ld), raw (sanitized), types[], parse_valid, errors[], visible_fact_mismatches(json) |
| PageMetric | T | crawl_page_id or url, metric (e.g. lcp), value, provenance_id — only when a sourced signal exists |
| AuditRun | T | crawl_job_id, ruleset_version, eligible_url_count, completed_at |
| CrawlIssue | T | audit_run_id, rule_key, severity, crawl_page_id?, url, evidence(json), status (`open`,`accepted`,`fixed`,`wont_fix`) |

Issue rate denominators come from `AuditRun.eligible_url_count` **per rule** (`audit_rule_eligibility` table: audit_run_id, rule_key, eligible_count).

## Search integrations (Module D)

| Entity | Own | Key fields |
|---|---|---|
| IntegrationConnection | T | client_id, provider (`gsc`,`ga4`), external_account, scopes[], status, last_sync_at, last_error |
| OAuthCredentialReference | T | connection_id, encrypted_refresh_token (envelope-encrypted), key_version, rotated_at. Never returned by API |
| ImportedDataset | T | client_id, kind, original_filename, object_key, sha256, row_count, schema_detected, status, provenance_id |
| SearchPerformanceDaily | T | client_id, source_id, date, page, query?, country, device, clicks, impressions, ctr, position, provenance_id |

## AI visibility (Modules E–H)

| Entity | Own | Key fields |
|---|---|---|
| Provider | G | key, name, kind (`llm_api`,`licensed_dataset`,`customer_import`), capabilities(json), terms_reviewed_at, enabled |
| TenantProviderConfig | T | provider_id, enabled, encrypted_api_key?, budget_monthly, model allow-list |
| PromptSet | T | project_id, name, version, market_id, language_id, locale, schedule(cron?), status |
| Prompt | T | prompt_set_id, text, topic_cluster_id?, intent, funnel_stage, persona, is_active, text_hash |
| PromptRun | T | prompt_id, prompt_set_version, provider_id, model, params(json), locale, run_at, status (`queued`,`completed`,`failed`,`excluded`), idempotency_key, tokens_in/out, cost, latency_ms, error, **eligible** (bool + exclusion_reason) |
| AnswerObservation | T | prompt_run_id, answer_text_object_key (if terms permit) or excerpt, answer_hash, provenance_id, parser_version, parser_confidence |
| ObservationEvidence | T | observation_id, kind (screenshot/raw json/import row), object_key, sha256 |
| Mention | T | observation_id, subject_type (brand/competitor/entity), subject_id, matched_text, offset, prominence (rank/position), mention_type (`recommended`,`neutral`,`negative`,`comparison`), sentiment, sentiment_confidence, detection_method (`exact`,`alias`,`llm`), review_status, reviewed_by |
| Citation | T | observation_id, url, normalized_url, cited_source_id, position, context_excerpt, owner_type (`owned`,`competitor`,`third_party`), qualifying (bool + reason) |
| CitedSource | T | hostname/registrable domain, classification |
| CompetitorObservation | T | observation_id, competitor_id, mentioned, cited — materialized per run for same-sample comparison |
| TopicCluster | T | project_id, name, intent, funnel_stage, source (`analyst`,`gsc_queries`,`import`) |

## Content (Modules I, J)

| Entity | Own | Key fields |
|---|---|---|
| ContentAsset | T | client_id, url, crawl_page_id?, type, author, published_at, updated_at_observed |
| ContentVersion | T | content_asset_id or brief_id, body_object_key, author_user_id, change_note |
| PageTopicMapping | T | content_asset_id, topic_cluster_id, mapping_rule, mapped_by, confidence_label |
| ContentGap | T | topic_cluster_id, gap_type (`missing`,`stale`,`overlap`,`weak_evidence`), evidence(json) |
| InternalLinkSuggestion | T | from_asset_id, to_asset_id, anchor_suggestion, rationale, status |
| ContentBrief | T | project_id, topic_cluster_id, status (`draft`,`in_review`,`approved`), outline(json), sources(json) |

## Workflow, implementation, verification (L–O)

| Entity | Own | Key fields |
|---|---|---|
| Recommendation | T | project_id, title, impact_hypothesis, evidence_refs(json: issue/observation/gap ids), effort, risk, confidence, priority, verification_criteria, status |
| Task | T | recommendation_id?, title, assignee_membership_id, due_date, status (`todo`,`in_progress`,`awaiting_approval`,`approved`,`implemented`,`verified`,`closed`) |
| Approval | T | object_type, object_id, requested_by, approver_contact_or_user, decision (`pending`,`approved`,`rejected`,`changes_requested`), decided_at, note. Immutable after decision |
| ImplementationChange | T | task_id, environment (`staging`,`production`), description, diff/snippet, performed_by, performed_at, rollback_plan, approval_id (required) |
| VerificationRun | T | implementation_change_id, kind (`recrawl`,`retest`), before_ref, after_ref, result (`pass`,`fail`,`inconclusive`), evidence(json) |
| Comment | T | object_type, object_id, body, author, visibility (`internal`,`client`) |
| Attachment | T | object_type, object_id, object_key, sha256, mime, scanned_status |

## Analytics & attribution (P, advanced 1)

| Entity | Own | Key fields |
|---|---|---|
| AnalyticsEvent | T | client_id, source_id, date, landing_page, channel/source/medium, sessions, provenance_id |
| Conversion | T | client_id, source_id, date, name, count, value?, provenance_id |
| Lead | T | client_id, source_id, external_id_hash, created_at, qualified, landing_page — **minimized, no direct PII by default** |
| AttributionRecord | T | conversion/lead id, model (`first_touch`,`last_touch`,`assisted`), window_days, channel, provenance_id |

## Reports, notifications, governance (Q, R, §11)

| Entity | Own | Key fields |
|---|---|---|
| Report | T | client_id, period_start/end, status (`draft`,`in_review`,`issued`), snapshot(json), pdf_object_key, pdf_sha256, issued_by |
| Notification | T | user/membership, kind, payload, read_at, channel |
| AlertRule | T | project_id, kind, threshold(json), enabled |
| ConsentRecord | T | subject (client/contact), purpose, granted_at, withdrawn_at |
| RetentionPolicy | T | object_type, retain_days, action (`delete`,`anonymize`) |
| DeletionRequest | T | scope, requested_by, status, completed_at, evidence |
| ExportJob | T | requested_by, scope, format, status, object_key, expires_at |
| MethodologyDoc | G/T | key, version, body, effective_from — change history for Module S |

## Key indexes (illustrative)

- `crawl_page (tenant_id, crawl_job_id, url_hash)` unique
- `crawl_issue (tenant_id, audit_run_id, rule_key, status)`
- `prompt_run (tenant_id, prompt_id, provider_id, run_at desc)`; unique `(tenant_id, idempotency_key)`
- `mention (tenant_id, subject_type, subject_id)`; `citation (tenant_id, normalized_url)`
- `search_performance_daily (tenant_id, client_id, date, page)` (BRIN on date for large tables)
- `audit_log (tenant_id, created_at desc)`, `(tenant_id, object_type, object_id)`

## Integrity rules

- A metric query returns `null` (not `0`) when its denominator is 0 or data is missing, plus a reason.
- `PromptRun.eligible=false` rows are excluded from rate denominators and shown separately with reasons.
- Duplicate runs prevented by idempotency key `(prompt_id, provider_id, model, scheduled_slot)`.
