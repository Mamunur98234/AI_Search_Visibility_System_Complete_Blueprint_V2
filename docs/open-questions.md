# Open Questions for the Product Owner

Assumptions used until answered are marked **Default**.

1. **Production hosting.** VPS, AWS/GCP/Azure, Render/Fly, or required cPanel?
   **Default:** Docker Compose on a VPS, portable to managed containers. cPanel unsupported for the app.
2. **AI providers.** Which provider API keys will you hold? Any licensed third-party AI-visibility data source?
   **Default:** adapters built and gated; no provider enabled until a key is supplied and terms reviewed. Import path always available.
3. **Design partners.** Are there agencies/clients to validate workflows (Blueprint Phase 0 gate)?
   **Default:** proceed with prototype; flag unvalidated assumptions.
4. **Branding / product name** for UI and crawler user agent. **Default:** "AI Search Visibility System", UA `AISVBot`.
5. **Data residency** requirements (EU/US)? **Default:** single region, chosen at deploy.
6. **Email provider** for invitations/notifications. **Default:** SMTP config; console backend in dev.
7. **License.** **Default:** proprietary, all rights reserved.
