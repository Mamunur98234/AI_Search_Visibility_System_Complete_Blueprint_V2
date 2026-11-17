"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { ResourceList } from "@/components/ResourceList";
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
  TextAreaField,
  formatDate,
  formatDateTime,
  toast,
} from "@/components/ui";
import { api, ApiError, type Schemas } from "@/lib/api";
import { STATUS_TONE } from "@/lib/nav";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

type Client = Schemas["ClientOut"];
const TABS = ["Overview", "Contacts", "Brands", "Domains", "Projects", "Notes"] as const;
type Tab = (typeof TABS)[number];

export default function ClientDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useSession();
  const client = useApi<Client>(`/clients/${id}`);
  const [tab, setTab] = useState<Tab>("Overview");
  const tabs = TABS.filter((t) => t !== "Notes" || can("note.read"));

  if (client.loading && !client.data) return <Loading />;
  if (client.error) return <ErrorState error={client.error} onRetry={client.reload} />;
  const c = client.data!;

  function onKey(e: React.KeyboardEvent, i: number) {
    const next = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : null;
    if (next === null) return;
    const t = tabs[(next + tabs.length) % tabs.length]!;
    setTab(t);
    document.getElementById(`tab-${t}`)?.focus();
  }

  return (
    <>
      <p className="small">
        <Link href="/clients">← Clients</Link>
      </p>
      <div className="page-head">
        <div>
          <h1>{c.name}</h1>
          <p className="muted">
            <Badge tone={STATUS_TONE[c.status]}>{c.status}</Badge> {c.industry ? `· ${c.industry}` : ""}
          </p>
        </div>
      </div>
      <div className="tabs" role="tablist" aria-label="Client sections">
        {tabs.map((t, i) => (
          <button
            key={t}
            id={`tab-${t}`}
            role="tab"
            aria-selected={tab === t}
            aria-controls={`panel-${t}`}
            tabIndex={tab === t ? 0 : -1}
            onClick={() => setTab(t)}
            onKeyDown={(e) => onKey(e, i)}
          >
            {t}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "Overview" && <ClientOverview client={c} onSaved={client.setData} />}
        {tab === "Contacts" && (
          <ResourceList<Schemas["ContactOut"]>
            title="Contacts"
            listPath={`/clients/${id}/contacts`}
            itemPath={(x) => `/contacts/${x.id}`}
            canManage={can("contact.manage")}
            itemLabel={(x) => x.name}
            emptyText="No contacts yet"
            fields={[
              { name: "name", label: "Name", required: true },
              { name: "email", label: "Email", type: "email", maxLength: 320 },
              { name: "job_title", label: "Job title" },
              { name: "phone", label: "Phone", maxLength: 50 },
              { name: "is_approver", label: "Can approve work for this client", type: "checkbox" },
            ]}
            render={(x) => (
              <>
                <strong>{x.name}</strong> {x.is_approver ? <Badge tone="info">Approver</Badge> : null}
                <div className="muted small">{[x.job_title, x.email, x.phone].filter(Boolean).join(" · ") || "—"}</div>
              </>
            )}
          />
        )}
        {tab === "Brands" && (
          <ResourceList<Schemas["BrandOut"]>
            title="Brands"
            listPath={`/clients/${id}/brands`}
            itemPath={(x) => `/brands/${x.id}`}
            canManage={can("brand.manage")}
            itemLabel={(x) => x.name}
            emptyText="No brands yet"
            fields={[
              { name: "name", label: "Brand name", required: true },
              { name: "aliases", label: "Aliases", type: "list", hint: "Comma-separated alternative names used for mention matching." },
              { name: "description", label: "Description", maxLength: 5000 },
            ]}
            render={(x) => (
              <>
                <strong>{x.name}</strong>
                <div className="muted small">Aliases: {x.aliases.length ? x.aliases.join(", ") : "none"}</div>
              </>
            )}
          />
        )}
        {tab === "Domains" && (
          <>
            <div className="alert alert-info">
              Domain ownership verification and crawling arrive in Phase 2. Until then every domain is listed as
              unverified and nothing is crawled.
            </div>
            <ResourceList<Schemas["DomainOut"]>
              title="Domains"
              listPath={`/clients/${id}/domains`}
              itemPath={(x) => `/domains/${x.id}`}
              canManage={can("domain.manage")}
              itemLabel={(x) => x.hostname}
              emptyText="No domains yet"
              fields={[
                { name: "hostname", label: "Hostname", required: true, maxLength: 253, hint: "Bare hostname, e.g. www.example.com" },
                { name: "is_primary", label: "Primary domain", type: "checkbox" },
              ]}
              render={(x) => (
                <>
                  <strong>{x.hostname}</strong> {x.is_primary ? <Badge tone="info">Primary</Badge> : null}{" "}
                  <Badge tone={x.verification_status === "verified" ? "ok" : "neutral"}>{x.verification_status}</Badge>
                </>
              )}
            />
          </>
        )}
        {tab === "Projects" && <Projects clientId={id} />}
        {tab === "Notes" && <Notes clientId={id} />}
      </div>
    </>
  );
}

function ClientOverview({ client, onSaved }: { client: Client; onSaved: (c: Client) => void }) {
  const { can } = useSession();
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const fe = error instanceof ApiError ? error.fieldErrors : {};

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(undefined);
    try {
      const c = await api<Client>("PATCH", `/clients/${client.id}`, {
        name: f.get("name"),
        industry: f.get("industry") || null,
        website: f.get("website") || null,
        status: f.get("status"),
        renewal_date: f.get("renewal_date") || null,
        business_goals: f.get("business_goals") || null,
      });
      onSaved(c);
      setEditing(false);
      toast("Client saved");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function archive() {
    if (!window.confirm(`Archive ${client.name}? It will be hidden from the client list.`)) return;
    try {
      await api("DELETE", `/clients/${client.id}`);
      toast("Client archived");
      router.push("/clients");
    } catch (err) {
      toast(err instanceof Error ? err.message : "Archive failed");
    }
  }

  if (editing) {
    return (
      <form className="card" onSubmit={save}>
        <FormError error={error} />
        <Field label="Client name" name="name" required defaultValue={client.name} maxLength={200} error={fe.name} />
        <Field label="Industry" name="industry" defaultValue={client.industry ?? ""} maxLength={120} />
        <Field label="Website" name="website" defaultValue={client.website ?? ""} maxLength={300} />
        <SelectField label="Status" name="status" defaultValue={client.status}>
          {["onboarding", "active", "paused", "archived"].map((s) => (
            <option key={s}>{s}</option>
          ))}
        </SelectField>
        <Field label="Renewal date" name="renewal_date" type="date" defaultValue={client.renewal_date ?? ""} />
        <TextAreaField label="Business goals" name="business_goals" defaultValue={client.business_goals ?? ""} maxLength={5000} />
        <div className="row">
          <Button variant="primary" type="submit" busy={busy}>
            Save
          </Button>
          <Button type="button" onClick={() => setEditing(false)}>
            Cancel
          </Button>
        </div>
      </form>
    );
  }
  return (
    <section className="card">
      <dl className="kv">
        <dt>Industry</dt>
        <dd>{client.industry ?? "—"}</dd>
        <dt>Website</dt>
        <dd>{client.website ?? "—"}</dd>
        <dt>Renewal date</dt>
        <dd>{formatDate(client.renewal_date)}</dd>
        <dt>Business goals</dt>
        <dd className="pre-wrap">{client.business_goals ?? "—"}</dd>
        <dt>Created</dt>
        <dd>{formatDateTime(client.created_at)}</dd>
      </dl>
      <div className="row">
        {can("client.update") ? (
          <Button onClick={() => setEditing(true)}>Edit</Button>
        ) : (
          <DisabledHint label="Edit" reason="Your role cannot edit clients." />
        )}
        {can("client.delete") && client.status !== "archived" ? (
          <Button variant="danger" onClick={() => void archive()}>
            Archive
          </Button>
        ) : null}
      </div>
    </section>
  );
}

function Projects({ clientId }: { clientId: string }) {
  const { can } = useSession();
  return (
    <ResourceList<Schemas["ProjectOut"]>
      title="Projects"
      listPath={`/clients/${clientId}/projects`}
      itemPath={(x) => `/projects/${x.id}`}
      canManage={can("project.manage")}
      itemLabel={(x) => x.name}
      emptyText="No projects yet"
      fields={[
        { name: "name", label: "Project name", required: true },
        { name: "start_date", label: "Start date", type: "date" },
        { name: "end_date", label: "End date", type: "date" },
      ]}
      render={(x) => (
        <details>
          <summary>
            <strong>{x.name}</strong> <Badge tone={STATUS_TONE[x.status]}>{x.status}</Badge>{" "}
            <span className="muted small">
              {x.start_date || x.end_date
                ? `${formatDate(x.start_date)} – ${formatDate(x.end_date)}`
                : "No dates set"}
            </span>
          </summary>
          <div className="stack">
            <ProjectMarkets projectId={x.id} />
            <ResourceList<Schemas["CompetitorOut"]>
              title="Competitors"
              listPath={`/projects/${x.id}/competitors`}
              itemPath={(c) => `/competitors/${c.id}`}
              canManage={can("competitor.manage")}
              itemLabel={(c) => c.name}
              emptyText="No competitors yet"
              fields={[
                { name: "name", label: "Competitor name", required: true },
                { name: "domains", label: "Domains", type: "list", hint: "Comma-separated hostnames." },
                { name: "aliases", label: "Aliases", type: "list", hint: "Comma-separated." },
              ]}
              render={(c) => (
                <>
                  <strong>{c.name}</strong>
                  <div className="muted small">{c.domains.join(", ") || "no domains"}</div>
                </>
              )}
            />
          </div>
        </details>
      )}
    />
  );
}

function ProjectMarkets({ projectId }: { projectId: string }) {
  const { can } = useSession();
  const pms = useApi<Schemas["ProjectMarketOut"][]>(`/projects/${projectId}/markets`);
  const markets = useApi<Schemas["MarketOut"][]>("/reference/markets");
  const languages = useApi<Schemas["LanguageOut"][]>("/reference/languages");
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);

  async function add(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(undefined);
    try {
      await api("POST", `/projects/${projectId}/markets`, {
        market_code: f.get("market_code"),
        language_code: f.get("language_code"),
      });
      await pms.reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    try {
      await api("DELETE", `/project-markets/${id}`);
      await pms.reload();
    } catch (err) {
      toast(err instanceof Error ? err.message : "Remove failed");
    }
  }

  const marketName = (code: string) => markets.data?.find((m) => m.code === code)?.name ?? code;
  const langName = (code: string) => languages.data?.find((l) => l.code === code)?.name ?? code;
  return (
    <section className="card" aria-label="Markets and languages">
      <h3>Markets &amp; languages</h3>
      {pms.loading && !pms.data ? (
        <Loading />
      ) : pms.error ? (
        <ErrorState error={pms.error} onRetry={pms.reload} />
      ) : pms.data?.length ? (
        <ul className="list-plain">
          {pms.data.map((pm) => (
            <li key={pm.id} className="row between">
              <span>
                {marketName(pm.market_code)} · {langName(pm.language_code)}
              </span>
              {can("project.manage") ? (
                <Button variant="danger" onClick={() => void remove(pm.id)}
                  aria-label={`Remove ${marketName(pm.market_code)} ${langName(pm.language_code)}`}>
                  Remove
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState title="No markets yet" />
      )}
      {can("project.manage") && markets.data && languages.data ? (
        <form onSubmit={add} className="row">
          <FormError error={error} />
          <SelectField label="Market" name="market_code" required>
            {markets.data.map((m) => (
              <option key={m.code} value={m.code}>
                {m.name}
              </option>
            ))}
          </SelectField>
          <SelectField label="Language" name="language_code" required>
            {languages.data.map((l) => (
              <option key={l.code} value={l.code}>
                {l.name}
              </option>
            ))}
          </SelectField>
          <div className="field">
            <Button type="submit" busy={busy}>
              Add market
            </Button>
          </div>
        </form>
      ) : null}
    </section>
  );
}

function Notes({ clientId }: { clientId: string }) {
  const { can } = useSession();
  const notes = useApi<Schemas["NoteOut"][]>(`/clients/${clientId}/notes`);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();

  async function add(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    setBusy(true);
    setError(undefined);
    try {
      await api("POST", `/clients/${clientId}/notes`, { body: new FormData(form).get("body") });
      form.reset();
      await notes.reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    if (!window.confirm("Delete this note?")) return;
    try {
      await api("DELETE", `/notes/${id}`);
      await notes.reload();
    } catch (err) {
      toast(err instanceof Error ? err.message : "Delete failed");
    }
  }

  return (
    <section className="card" aria-label="Internal notes">
      <p className="muted small">Internal notes are visible to agency roles only, never to client users.</p>
      {can("note.manage") ? (
        <form onSubmit={add}>
          <FormError error={error} />
          <TextAreaField label="Add a note" name="body" required maxLength={10000} />
          <Button type="submit" busy={busy}>
            Add note
          </Button>
        </form>
      ) : null}
      {notes.loading && !notes.data ? (
        <Loading />
      ) : notes.error ? (
        <ErrorState error={notes.error} onRetry={notes.reload} />
      ) : notes.data?.length ? (
        <ul className="list-plain">
          {notes.data.map((n) => (
            <li key={n.id} className="row between">
              <div className="grow">
                {/* Rendered as text: React escapes it, so stored markup can never execute. */}
                <p className="pre-wrap">{n.body}</p>
                <span className="muted small">{formatDateTime(n.created_at)}</span>
              </div>
              {can("note.manage") ? (
                <Button variant="danger" onClick={() => void remove(n.id)} aria-label="Delete note">
                  Delete
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState title="No notes yet" />
      )}
    </section>
  );
}
