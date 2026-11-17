"use client";

import Link from "next/link";

import { Badge, ErrorState, Loading, formatDateTime } from "@/components/ui";
import type { Schemas } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

export default function OverviewPage() {
  const { me, can } = useSession();
  const clients = useApi<Schemas["Page_ClientOut_"]>(can("client.read") ? "/clients?limit=200" : null);
  const members = useApi<Schemas["MemberOut"][]>(can("member.read") ? "/members" : null);
  const invites = useApi<Schemas["InvitationOut"][]>(can("member.read") ? "/invitations" : null);
  const log = useApi<Schemas["Page_AuditLogOut_"]>(can("audit_log.read") ? "/audit-log?limit=8" : null);

  const byStatus = (s: string) => clients.data?.items.filter((c) => c.status === s).length ?? 0;
  const clientCount = clients.data?.items.length ?? 0;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Overview</h1>
          <p className="muted">{me.active_tenant?.name}</p>
        </div>
      </div>

      {can("client.read") ? (
        clients.loading ? (
          <Loading />
        ) : clients.error ? (
          <ErrorState error={clients.error} onRetry={clients.reload} />
        ) : (
          <section aria-labelledby="clients-h" className="grid">
            <h2 id="clients-h" className="sr-only">
              Client counts
            </h2>
            <div className="card">
              <div className="muted small">Active clients</div>
              <div className="stat">{byStatus("active")}</div>
            </div>
            <div className="card">
              <div className="muted small">Onboarding</div>
              <div className="stat">{byStatus("onboarding")}</div>
            </div>
            <div className="card">
              <div className="muted small">Paused</div>
              <div className="stat">{byStatus("paused")}</div>
            </div>
            {can("member.read") ? (
              <div className="card">
                <div className="muted small">Team members · pending invitations</div>
                <div className="stat">
                  {members.data ? members.data.length : "—"} · {invites.data ? invites.data.length : "—"}
                </div>
              </div>
            ) : null}
          </section>
        )
      ) : null}

      <div className="grid">
        <section className="card" aria-labelledby="start-h">
          <h2 id="start-h">Getting started</h2>
          <ul className="list-plain">
            <li>
              {clientCount > 0 ? <Badge tone="ok">Done</Badge> : <Badge>To do</Badge>}{" "}
              {can("client.create") ? <Link href="/clients">Add your first client</Link> : "Add your first client"}
            </li>
            <li>
              {(members.data?.length ?? 0) > 1 ? <Badge tone="ok">Done</Badge> : <Badge>To do</Badge>}{" "}
              {can("member.invite") ? <Link href="/settings/members">Invite your team</Link> : "Invite your team"}
            </li>
            <li>
              {me.mfa_enabled ? <Badge tone="ok">Done</Badge> : <Badge tone="warn">Recommended</Badge>}{" "}
              <Link href="/settings/security">Turn on two-factor authentication</Link>
            </li>
            <li>
              <Badge>Next</Badge> <Link href="/domains">Verify a domain and run a technical audit</Link>
            </li>
          </ul>
        </section>

        {can("audit_log.read") ? (
          <section className="card" aria-labelledby="activity-h">
            <h2 id="activity-h">Recent activity</h2>
            {log.loading ? (
              <Loading />
            ) : log.error ? (
              <ErrorState error={log.error} onRetry={log.reload} />
            ) : log.data && log.data.items.length ? (
              <ul className="list-plain">
                {log.data.items.map((e) => (
                  <li key={e.id}>
                    <strong>{e.action}</strong> <span className="muted">by {e.actor_name ?? "system"}</span>
                    <div className="muted small">{formatDateTime(e.created_at)}</div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">No activity yet.</p>
            )}
            <Link href="/settings/audit-log">View full audit log</Link>
          </section>
        ) : null}
      </div>
    </>
  );
}
