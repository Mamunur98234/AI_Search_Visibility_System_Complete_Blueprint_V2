"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import {
  Badge,
  Button,
  DisabledHint,
  EmptyState,
  ErrorState,
  Field,
  FormError,
  Loading,
  SelectField,
  formatDateTime,
  toast,
} from "@/components/ui";
import { api, ApiError, type Schemas } from "@/lib/api";
import { CRAWL_TONE, VERIFICATION_TONE } from "@/lib/labels";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

const METHODS: Record<string, string> = {
  dns_txt: "DNS TXT record (recommended)",
  meta_tag: "HTML meta tag on the homepage (HTTPS)",
  well_known: "File at /.well-known/ (HTTPS)",
};

export default function DomainPage() {
  const { id } = useParams<{ id: string }>();
  const domain = useApi<Schemas["DomainOut"]>(`/domains/${id}`);
  const ver = useApi<Schemas["VerificationOut"]>(`/domains/${id}/verification`);
  const crawls = useApi<Schemas["CrawlOut"][]>(domain.data ? `/clients/${domain.data.client_id}/crawls` : null);

  if ((domain.loading && !domain.data) || (ver.loading && !ver.data)) return <Loading />;
  if (domain.error) return <ErrorState error={domain.error} onRetry={domain.reload} />;
  if (ver.error) return <ErrorState error={ver.error} onRetry={ver.reload} />;
  const d = domain.data!;
  const v = ver.data!;
  const history = (crawls.data ?? []).filter((c) => c.domain_id === d.id);

  return (
    <>
      <p className="small">
        <Link href="/domains">← Domains &amp; audits</Link> · <Link href={`/clients/${d.client_id}`}>Client</Link>
      </p>
      <div className="page-head">
        <div>
          <h1>{d.hostname}</h1>
          <p className="muted">
            Ownership: <Badge tone={VERIFICATION_TONE[v.status]}>{v.status}</Badge>
            {v.verified_at ? ` since ${formatDateTime(v.verified_at)}` : ""}
          </p>
        </div>
      </div>
      <div className="stack">
        {v.status === "verified" ? (
          <StartCrawl domainId={d.id} hasActive={history.some((c) => ["queued", "running", "paused"].includes(c.status))} />
        ) : (
          <Verification v={v} onChange={(nv) => ver.setData(nv)} />
        )}
        <section className="card" aria-labelledby="hist-h">
          <h2 id="hist-h">Crawl history</h2>
          {crawls.loading && !crawls.data ? (
            <Loading />
          ) : crawls.error ? (
            <ErrorState error={crawls.error} onRetry={crawls.reload} />
          ) : history.length === 0 ? (
            <EmptyState title="No crawls yet" />
          ) : (
            <div className="table-wrap">
              <table>
                <caption className="sr-only">Crawl history</caption>
                <thead>
                  <tr>
                    <th scope="col">Started</th>
                    <th scope="col">Status</th>
                    <th scope="col">Fetched</th>
                    <th scope="col">Skipped</th>
                    <th scope="col">Errors</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((c) => (
                    <tr key={c.id}>
                      <td>
                        <Link href={`/crawls/${c.id}`}>{formatDateTime(c.started_at ?? c.created_at)}</Link>
                      </td>
                      <td>
                        <Badge tone={CRAWL_TONE[c.status]}>{c.status}</Badge>
                      </td>
                      <td>{c.pages_fetched}</td>
                      <td>{c.pages_skipped}</td>
                      <td>{c.pages_errored}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </>
  );
}

function Verification({ v, onChange }: { v: Schemas["VerificationOut"]; onChange: (v: Schemas["VerificationOut"]) => void }) {
  const { can } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [method, setMethod] = useState(v.method ?? "dns_txt");

  async function start() {
    setBusy(true);
    setError(undefined);
    try {
      onChange(await api<Schemas["VerificationOut"]>("POST", `/domains/${v.domain_id}/verification`, { method }));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function check() {
    setBusy(true);
    setError(undefined);
    try {
      const r = await api<Schemas["VerificationOut"]>("POST", `/domains/${v.domain_id}/verification/check`);
      onChange(r);
      toast(r.status === "verified" ? "Domain verified" : "Not verified yet");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  if (!can("domain.verify")) {
    return (
      <section className="card">
        <h2>Verify ownership</h2>
        <p className="muted">This domain is not verified yet. Ask an account manager or analyst to verify it.</p>
      </section>
    );
  }
  const instr = v.instructions;
  return (
    <section className="card" aria-labelledby="ver-h">
      <h2 id="ver-h">Verify ownership</h2>
      <p className="muted">
        We only crawl domains whose owner has published a proof token. The token is specific to this workspace.
      </p>
      <FormError error={error} />
      <div className="row">
        <SelectField label="Method" value={method} onChange={(e) => setMethod(e.target.value)}>
          {Object.entries(METHODS).map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </SelectField>
        <div className="field">
          <Button onClick={() => void start()} busy={busy}>
            {v.method ? "Switch method" : "Get instructions"}
          </Button>
        </div>
      </div>
      {instr && v.method ? (
        <div className="alert alert-info">
          <p>
            <strong>{METHODS[v.method]}</strong> — {instr.summary}
          </p>
          <dl className="kv">
            {Object.entries(instr)
              .filter(([k]) => k !== "summary")
              .map(([k, val]) => (
                <div key={k} className="contents">
                  <dt>{k.replace(/_/g, " ")}</dt>
                  <dd>
                    <code className="secret">{val}</code>
                  </dd>
                </div>
              ))}
          </dl>
        </div>
      ) : null}
      {v.error ? (
        <div className="alert alert-warn" role="status">
          Last check {formatDateTime(v.checked_at)}: {v.error}
        </div>
      ) : null}
      {v.method ? (
        <Button variant="primary" onClick={() => void check()} busy={busy}>
          Check now
        </Button>
      ) : null}
    </section>
  );
}

function StartCrawl({ domainId, hasActive }: { domainId: string; hasActive: boolean }) {
  const { can } = useSession();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const fe = error instanceof ApiError ? error.fieldErrors : {};

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(undefined);
    try {
      const c = await api<Schemas["CrawlOut"]>("POST", `/domains/${domainId}/crawls`, {
        max_pages: Number(f.get("max_pages")),
        max_depth: Number(f.get("max_depth")),
        delay_ms: Number(f.get("delay_ms")),
      });
      router.push(`/crawls/${c.id}`);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-labelledby="crawl-h">
      <h2 id="crawl-h">Run a technical audit crawl</h2>
      <p className="muted small">
        The crawler identifies itself as AISVBot, obeys robots.txt and Crawl-delay, fetches one page at a time, does not
        execute JavaScript and stays on this exact host.
      </p>
      {!can("crawl.run") ? (
        <DisabledHint label="Start crawl" reason="Your role cannot start crawls." />
      ) : hasActive ? (
        <DisabledHint label="Start crawl" reason="A crawl of this domain is already queued, running or paused." />
      ) : (
        <form onSubmit={submit}>
          <FormError error={error} />
          <div className="row">
            <Field label="Max pages" name="max_pages" type="number" min={1} max={5000} defaultValue={200} required
              error={fe.max_pages} />
            <Field label="Max link depth" name="max_depth" type="number" min={0} max={20} defaultValue={5} required
              error={fe.max_depth} />
            <Field label="Delay between requests (ms)" name="delay_ms" type="number" min={0} max={10000}
              defaultValue={1000} required error={fe.delay_ms} />
          </div>
          <Button variant="primary" type="submit" busy={busy}>
            Start crawl
          </Button>
        </form>
      )}
    </section>
  );
}
