"use client";

import Link from "next/link";
import { useState } from "react";

import { Badge, EmptyState, ErrorState, Loading, SelectField, formatDateTime } from "@/components/ui";
import type { Schemas } from "@/lib/api";
import { CRAWL_TONE, VERIFICATION_TONE } from "@/lib/labels";
import { useApi } from "@/lib/use-api";

export default function DomainsPage() {
  const [status, setStatus] = useState("");
  const domains = useApi<Schemas["DomainListOut"][]>(`/domains${status ? `?status=${status}` : ""}`);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Domains &amp; audits</h1>
          <p className="muted">
            Ownership must be verified before a domain can be crawled. Add domains from a client&apos;s Domains tab.
          </p>
        </div>
      </div>
      <div className="row" role="search">
        <SelectField label="Verification status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All</option>
          <option value="verified">Verified</option>
          <option value="pending">Pending</option>
          <option value="unverified">Unverified</option>
        </SelectField>
      </div>
      {domains.loading && !domains.data ? (
        <Loading />
      ) : domains.error ? (
        <ErrorState error={domains.error} onRetry={domains.reload} />
      ) : !domains.data?.length ? (
        <EmptyState title="No domains yet">
          <span>
            Open a <Link href="/clients">client</Link> and add a domain on its Domains tab.
          </span>
        </EmptyState>
      ) : (
        <div className="table-wrap">
          <table>
            <caption className="sr-only">Domains</caption>
            <thead>
              <tr>
                <th scope="col">Domain</th>
                <th scope="col">Client</th>
                <th scope="col">Ownership</th>
                <th scope="col">Latest crawl</th>
              </tr>
            </thead>
            <tbody>
              {domains.data.map((d) => (
                <tr key={d.id}>
                  <td>
                    <Link href={`/domains/${d.id}`}>{d.hostname}</Link> {d.is_primary ? <Badge tone="info">Primary</Badge> : null}
                  </td>
                  <td>
                    <Link href={`/clients/${d.client_id}`}>{d.client_name}</Link>
                  </td>
                  <td>
                    <Badge tone={VERIFICATION_TONE[d.verification_status]}>{d.verification_status}</Badge>
                  </td>
                  <td>
                    {d.last_crawl_id ? (
                      <>
                        <Link href={`/crawls/${d.last_crawl_id}`}>{formatDateTime(d.last_crawl_at)}</Link>{" "}
                        <Badge tone={CRAWL_TONE[d.last_crawl_status ?? ""]}>{d.last_crawl_status}</Badge>
                      </>
                    ) : (
                      <span className="muted">Never crawled</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
