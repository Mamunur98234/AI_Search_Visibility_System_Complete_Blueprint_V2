# API Surface (outline)

Status: **Proposed (Phase 0)**. Base path `/api/v1`. JSON. Cookie session + `X-CSRF-Token` on
unsafe methods. Tenant is implied by the session's active tenant; IDs in paths are always resolved
within that tenant (foreign IDs → 404). Lists use cursor pagination (`?cursor=&limit=`).
Errors follow RFC 9457 problem+json. The OpenAPI schema is the source for the typed frontend client.

## Auth & tenancy (Phase 1)
```
POST   /auth/login                POST /auth/logout          GET  /auth/me
POST   /auth/mfa/setup|verify|disable
POST   /auth/password/forgot|reset
POST   /auth/switch-tenant
GET    /invitations/{token}       POST /invitations/{token}/accept
GET    /members                   POST /members/invite       PATCH/DELETE /members/{id}
GET    /roles                     GET  /permissions
GET    /audit-log?object_type=&object_id=&actor=&from=&to=
```

## CRM (Phase 1)
```
/clients            GET POST       /clients/{id}           GET PATCH DELETE
/clients/{id}/contacts|brands|domains|projects|notes       GET POST
/projects/{id}      GET PATCH      /projects/{id}/competitors|markets  GET POST
/brands/{id} /domains/{id} /competitors/{id} /contacts/{id}  GET PATCH DELETE
```

## Domains & crawl (Phase 2)
```
POST /domains/{id}/verification/start      → returns token + instructions
POST /domains/{id}/verification/check
POST /domains/{id}/crawls                  GET /crawls/{id}
POST /crawls/{id}/pause|resume|cancel
GET  /crawls/{id}/pages|skips
GET  /audit-runs/{id}/issues?rule=&severity=&status=
GET  /audit-runs/{id}/summary              → per-rule affected/eligible with provenance
PATCH /issues/{id}
```

## Integrations (Phase 3)
```
GET  /integrations                          POST /integrations/{provider}/connect → OAuth redirect URL
GET  /integrations/oauth/callback           DELETE /integrations/{id}
POST /integrations/{id}/sync                GET  /integrations/{id}/status
POST /imports (multipart)                   GET  /imports/{id}
GET  /clients/{id}/search-performance?from=&to=&dimension=
GET  /projects/{id}/page-topic-mappings     POST/PATCH ...
```

## AI visibility (Phase 4)
```
GET  /providers                             (capability registry, read-only for tenants)
/projects/{id}/prompt-sets  GET POST        /prompt-sets/{id} GET PATCH
/prompt-sets/{id}/prompts   GET POST        POST /prompt-sets/{id}/runs  (manual run; budget-checked)
GET  /prompt-runs?prompt_set=&provider=&from=&to=
GET  /observations/{id}                     (answer, evidence, mentions, citations)
PATCH /mentions/{id}  PATCH /citations/{id} (analyst correction → analyst_reviewed)
POST /observations/import                   (customer/licensed CSV/JSON)
GET  /projects/{id}/visibility/metrics?prompt_set=&providers=&from=&to=   → metrics with numerators/denominators/scope
GET  /projects/{id}/visibility/competitors?...                          → same eligible run set
```

## Workflow & reports (Phase 5)
```
/projects/{id}/recommendations GET POST   /recommendations/{id} GET PATCH
/tasks GET POST  /tasks/{id} GET PATCH    /tasks/{id}/comments GET POST
POST /approvals  GET /approvals?status=   POST /approvals/{id}/decide
POST /tasks/{id}/implementation-changes   POST /implementation-changes/{id}/verify  (Phase 6)
/clients/{id}/reports GET POST            /reports/{id} GET PATCH
POST /reports/{id}/render                 POST /reports/{id}/issue
GET  /reports/{id}/download               → short-lived signed URL
```

## Governance
```
GET/PUT /retention-policies   POST /exports  GET /exports/{id}  POST /deletion-requests
```

## Ops
```
GET /healthz   GET /readyz   (no tenant data)
```
