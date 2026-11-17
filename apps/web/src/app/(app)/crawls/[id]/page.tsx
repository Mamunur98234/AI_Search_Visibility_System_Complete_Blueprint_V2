"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { SafeLink } from "@/components/SafeLink";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Loading,
  SelectField,
  TextAreaField,
  formatDateTime,
  toast,
} from "@/components/ui";
import { api, ApiError, type Schemas } from "@/lib/api";
import { CRAWL_TONE, ROBOTS_LABELS, SEVERITY_TONE, SKIP_REASON_LABELS, pct } from "@/lib/labels";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

type Crawl = Schemas["CrawlDetailOut"];
const TABS = ["Findings", "Pages", "robots.txt"] as const;

export default function CrawlPage() {
  const { id } = useParams<{ id: string }>();
  const crawl = useApi<Crawl>(`/crawls/${id}`);
  const [tab, setTab] = useState<(typeof TABS)[number]>("Findings");
  const live = crawl.data && ["queued", "running"].includes(crawl.data.status);
  const { reload } = crawl;

  useEffect(() => {
    if (!live) return;
    const t = setInterval(() => void reload(), 3000);
    return () => clearInterval(t);
  }, [live, reload]);

  if (crawl.loading && !crawl.data) return <Loading />;
  if (crawl.error && !crawl.data) return <ErrorState error={crawl.error} onRetry={crawl.reload} />;
  const c = crawl.data!;

  return (
    <>
      <p className="small">
        <Link href={`/domains/${c.domain_id}`}>← {c.hostname}</Link>
      </p>
      <div className="page-head">
        <div>
          <h1>Crawl of {c.hostname}</h1>
          <p className="muted" aria-live="polite">
            <Badge tone={CRAWL_TONE[c.status]}>{c.status}</Badge>
            {c.requested_action ? ` · ${c.requested_action} requested` : ""} · started {formatDateTime(c.started_at ?? c.created_at)}
            {c.finished_at ? ` · finished ${formatDateTime(c.finished_at)}` : ""}
          </p>
        </div>
        <Controls crawl={c} onChange={() => void crawl.reload()} />
      </div>
      {c.error ? <div className="alert alert-error" role="alert">{c.error}</div> : null}
      {c.note ? <div className="alert alert-warn">{c.note}</div> : null}

      <section className="grid" aria-label="Crawl progress">
        <Stat label="Fetched" value={c.pages_fetched} />
        <Stat label="Skipped (with reason)" value={c.pages_skipped} />
        <Stat label="Errors" value={c.pages_errored} />
        <Stat label="Queued" value={c.state_counts?.queued ?? 0} />
      </section>
      <section className="card section-gap" aria-label="Crawl settings">
        <dl className="kv">
          <dt>robots.txt</dt>
          <dd>{c.robots_outcome ? ROBOTS_LABELS[c.robots_outcome] ?? c.robots_outcome : "Not fetched yet"}</dd>
          <dt>Limits</dt>
          <dd>
            {c.max_pages} pages · depth {c.max_depth} · {c.delay_ms} ms between requests
            {c.crawl_delay_s ? ` · robots Crawl-delay ${c.crawl_delay_s}s honoured` : ""}
          </dd>
          <dt>Discovered</dt>
          <dd>
            {c.urls_discovered} URLs · {c.sitemap_urls_found} sitemap entries
            {c.urls_dropped ? ` · ${c.urls_dropped} not recorded (discovery cap)` : ""}
          </dd>
          <dt>User agent</dt>
          <dd>
            <code className="small">{c.user_agent}</code>
          </dd>
        </dl>
      </section>

      <div className="tabs section-gap" role="tablist" aria-label="Crawl sections">
        {TABS.map((t) => (
          <button key={t} role="tab" id={`tab-${t}`} aria-selected={tab === t} aria-controls={`panel-${t}`}
            tabIndex={tab === t ? 0 : -1} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "Findings" && <Findings crawl={c} />}
        {tab === "Pages" && <Pages crawlId={c.id} />}
        {tab === "robots.txt" &&
          (c.robots_txt ? <pre className="card pre-wrap small">{c.robots_txt}</pre> : <EmptyState title="No robots.txt content" />)}
      </div>
    </>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="card">
      <div className="muted small">{label}</div>
      <div className="stat">{value}</div>
    </div>
  );
}

function Controls({ crawl, onChange }: { crawl: Crawl; onChange: () => void }) {
  const { can } = useSession();
  const [busy, setBusy] = useState(false);
  if (!can("crawl.run")) return null;
  async function act(action: "pause" | "resume" | "cancel") {
    if (action === "cancel" && !window.confirm("Cancel this crawl? Remaining URLs will be recorded as skipped.")) return;
    setBusy(true);
    try {
      await api("POST", `/crawls/${crawl.id}/${action}`);
      toast(`Crawl ${action} requested`);
      onChange();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }
  const s = crawl.status;
  return (
    <div className="row">
      {["queued", "running"].includes(s) ? (
        <Button onClick={() => void act("pause")} busy={busy} disabled={crawl.requested_action !== null}>
          Pause
        </Button>
      ) : null}
      {s === "paused" ? (
        <Button variant="primary" onClick={() => void act("resume")} busy={busy}>
          Resume
        </Button>
      ) : null}
      {["queued", "running", "paused"].includes(s) ? (
        <Button variant="danger" onClick={() => void act("cancel")} busy={busy} disabled={crawl.requested_action === "cancel"}>
          Cancel
        </Button>
      ) : null}
    </div>
  );
}

function Findings({ crawl }: { crawl: Crawl }) {
  const done = crawl.status === "completed";
  const summary = useApi<Schemas["AuditSummaryOut"]>(done ? `/crawls/${crawl.id}/audit` : null);
  const [rule, setRule] = useState<string | null>(null);
  if (!done) {
    return (
      <EmptyState title="Findings appear when the crawl completes">
        <span>{crawl.status === "cancelled" || crawl.status === "failed" ? "This crawl did not complete, so no audit was produced." : "Progress updates automatically."}</span>
      </EmptyState>
    );
  }
  if (summary.error) return <ErrorState error={summary.error} onRetry={summary.reload} />;
  if (!summary.data) return <Loading />;
  const s = summary.data;
  const p = s.provenance;
  const selected = s.rules.find((r) => r.key === rule);
  return (
    <div className="stack">
      <section className="alert alert-info" aria-label="Data provenance">
        <strong>Source:</strong> {p.source} · <strong>Method:</strong> {p.method} · <strong>Scope:</strong> {p.scope} ·{" "}
        <strong>n =</strong> {p.sample_size} fetched URLs · <strong>Collected:</strong> {formatDateTime(p.collected_from)} –{" "}
        {formatDateTime(p.collected_to)} · <Badge tone="info">{p.confidence_label.replace(/_/g, " ")}</Badge>
        <details>
          <summary>Limitations</summary>
          <ul>
            {p.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </details>
      </section>
      <div className="table-wrap">
        <table>
          <caption className="sr-only">Technical audit rules. Rate equals affected divided by eligible URLs.</caption>
          <thead>
            <tr>
              <th scope="col">Check</th>
              <th scope="col">Severity</th>
              <th scope="col" className="num">Affected</th>
              <th scope="col" className="num">Eligible</th>
              <th scope="col" className="num">Rate</th>
              <th scope="col"><span className="sr-only">Details</span></th>
            </tr>
          </thead>
          <tbody>
            {s.rules.map((r) => (
              <tr key={r.key}>
                <td>
                  {r.title}
                  <div className="muted small">Eligible: {r.eligible_definition}</div>
                </td>
                <td>
                  <Badge tone={SEVERITY_TONE[r.severity]}>{r.severity}</Badge>
                </td>
                <td className="num">{r.affected_count}</td>
                <td className="num">{r.eligible_count}</td>
                <td className="num">{pct(r.rate)}</td>
                <td>
                  {r.affected_count > 0 ? (
                    <Button onClick={() => setRule(r.key)} aria-label={`View ${r.affected_count} affected URLs for ${r.title}`}>
                      View
                    </Button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {selected ? <Issues crawlId={crawl.id} rule={selected} onClose={() => setRule(null)} /> : null}
    </div>
  );
}

function Evidence({ evidence }: { evidence: Record<string, unknown> }) {
  const entries = Object.entries(evidence);
  if (!entries.length) return <span className="muted">—</span>;
  return (
    <dl className="kv small">
      {entries.map(([k, v]) => (
        <div key={k} className="contents">
          <dt>{k.replace(/_/g, " ")}</dt>
          <dd>
            {Array.isArray(v) ? (
              <ul className="list-tight">
                {v.map((item, i) => (
                  <li key={i}>
                    {typeof item === "string" ? <SafeLink url={item} /> : <code>{JSON.stringify(item)}</code>}
                  </li>
                ))}
              </ul>
            ) : typeof v === "string" && /^https?:\/\//.test(v) ? (
              <SafeLink url={v} />
            ) : (
              <code>{typeof v === "string" ? v : JSON.stringify(v)}</code>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Issues({ crawlId, rule, onClose }: { crawlId: string; rule: Schemas["RuleResultOut"]; onClose: () => void }) {
  const { can } = useSession();
  const issues = useApi<Schemas["Page_IssueOut_"]>(`/crawls/${crawlId}/issues?rule=${rule.key}&limit=200`);
  return (
    <section className="card" aria-labelledby="issues-h">
      <div className="page-head">
        <div>
          <h2 id="issues-h">{rule.title}</h2>
          <p className="muted small">{rule.why}</p>
        </div>
        <Button onClick={onClose}>Close</Button>
      </div>
      {issues.loading && !issues.data ? (
        <Loading />
      ) : issues.error ? (
        <ErrorState error={issues.error} onRetry={issues.reload} />
      ) : (
        <ul className="list-plain">
          {issues.data?.items.map((i) => (
            <li key={i.id}>
              <SafeLink url={i.url} />
              <Evidence evidence={i.evidence} />
              <Triage issue={i} canManage={can("issue.manage")} />
            </li>
          ))}
          {issues.data?.next_cursor ? <li className="muted small">Showing the first 200 URLs.</li> : null}
        </ul>
      )}
    </section>
  );
}

function Triage({ issue, canManage }: { issue: Schemas["IssueOut"]; canManage: boolean }) {
  const [state, setState] = useState(issue);
  const [editing, setEditing] = useState(false);
  if (!canManage)
    return state.status !== "open" ? <Badge>{state.status.replace("_", " ")}</Badge> : null;
  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      setState(await api<Schemas["IssueOut"]>("PATCH", `/issues/${issue.id}`, { status: f.get("status"), note: f.get("note") || null }));
      setEditing(false);
      toast("Finding updated");
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Update failed");
    }
  }
  return editing ? (
    <form onSubmit={save} className="row">
      <SelectField label="Status" name="status" defaultValue={state.status}>
        <option value="open">Open</option>
        <option value="accepted">Accepted (will fix)</option>
        <option value="wont_fix">Won&apos;t fix</option>
      </SelectField>
      <TextAreaField label="Note" name="note" defaultValue={state.status_note ?? ""} maxLength={1000} rows={2} />
      <div className="field">
        <Button type="submit">Save</Button>
      </div>
    </form>
  ) : (
    <p className="small">
      <Badge tone={state.status === "open" ? "neutral" : "info"}>{state.status.replace("_", " ")}</Badge>
      {state.status_note ? <span className="muted"> — {state.status_note}</span> : null}{" "}
      <button className="btn btn-ghost small" onClick={() => setEditing(true)}>
        Triage
      </button>
    </p>
  );
}

function Pages({ crawlId }: { crawlId: string }) {
  const [state, setState] = useState("");
  const pages = useApi<Schemas["Page_CrawlPageOut_"]>(`/crawls/${crawlId}/pages?limit=200${state ? `&state=${state}` : ""}`);
  return (
    <>
      <SelectField label="State" value={state} onChange={(e) => setState(e.target.value)}>
        <option value="">All</option>
        <option value="fetched">Fetched</option>
        <option value="skipped">Skipped</option>
        <option value="error">Error</option>
        <option value="queued">Queued</option>
      </SelectField>
      {pages.loading && !pages.data ? (
        <Loading />
      ) : pages.error ? (
        <ErrorState error={pages.error} onRetry={pages.reload} />
      ) : !pages.data?.items.length ? (
        <EmptyState title="No URLs in this state" />
      ) : (
        <div className="table-wrap">
          <table>
            <caption className="sr-only">Crawled URLs</caption>
            <thead>
              <tr>
                <th scope="col">URL</th>
                <th scope="col">Result</th>
                <th scope="col">Title</th>
                <th scope="col" className="num">Fetch ms</th>
              </tr>
            </thead>
            <tbody>
              {pages.data.items.map((p) => (
                <tr key={p.id}>
                  <td>
                    <SafeLink url={p.url} />
                    <div className="muted small">
                      depth {p.depth} · via {p.source}
                      {p.final_url && p.final_url !== p.url ? <> · → <span className="break">{p.final_url}</span></> : null}
                    </div>
                  </td>
                  <td>
                    {p.state === "fetched" ? (
                      <Badge tone={(p.status_code ?? 0) >= 400 ? "bad" : (p.status_code ?? 0) >= 300 ? "warn" : "ok"}>
                        HTTP {p.status_code}
                      </Badge>
                    ) : (
                      <>
                        <Badge tone={p.state === "error" ? "bad" : "neutral"}>{p.state}</Badge>
                        <div className="small">{SKIP_REASON_LABELS[p.skip_reason ?? ""] ?? p.skip_reason}</div>
                      </>
                    )}
                  </td>
                  <td className="break">{p.title ?? "—"}</td>
                  <td className="num">{p.fetch_ms ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {pages.data?.next_cursor ? <p className="muted small">Showing the first 200 URLs.</p> : null}
    </>
  );
}
