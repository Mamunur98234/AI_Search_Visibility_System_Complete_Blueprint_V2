"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  Badge,
  Button,
  Dialog,
  DisabledHint,
  EmptyState,
  ErrorState,
  Field,
  FormError,
  Loading,
  SelectField,
  formatDate,
} from "@/components/ui";
import { api, ApiError, type Schemas } from "@/lib/api";
import { STATUS_TONE } from "@/lib/nav";
import { useSession } from "@/lib/session";

type Client = Schemas["ClientOut"];
const STATUSES = ["onboarding", "active", "paused", "archived"] as const;

export default function ClientsPage() {
  const { can } = useSession();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [items, setItems] = useState<Client[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>();
  const [creating, setCreating] = useState(false);

  async function load(reset: boolean, after?: string | null) {
    setLoading(true);
    setError(undefined);
    const params = new URLSearchParams({ limit: "50" });
    if (q.trim()) params.set("q", q.trim());
    if (status) params.set("status", status);
    if (!reset && after) params.set("cursor", after);
    try {
      const page = await api<Schemas["Page_ClientOut_"]>("GET", `/clients?${params}`);
      setItems((prev) => (reset ? page.items : [...prev, ...page.items]));
      setCursor(page.next_cursor ?? null);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const t = setTimeout(() => void load(true), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload on filter change only
  }, [q, status]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Clients</h1>
          <p className="muted">Clients you can access in this workspace.</p>
        </div>
        {can("client.create") ? (
          <Button variant="primary" onClick={() => setCreating(true)}>
            New client
          </Button>
        ) : (
          <DisabledHint label="New client" reason="Your role cannot create clients." />
        )}
      </div>

      <div className="row" role="search">
        <Field label="Search" name="q" type="search" value={q} onChange={(e) => setQ(e.target.value)} />
        <SelectField label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All except archived</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </SelectField>
      </div>

      {error ? (
        <ErrorState error={error} onRetry={() => void load(true)} />
      ) : loading && items.length === 0 ? (
        <Loading />
      ) : items.length === 0 ? (
        <EmptyState title={q || status ? "No clients match these filters" : "No clients yet"}>
          {can("client.create") && !q && !status ? <span>Create your first client to get started.</span> : null}
        </EmptyState>
      ) : (
        <>
          <div className="table-wrap">
            <table>
              <caption className="sr-only">Clients</caption>
              <thead>
                <tr>
                  <th scope="col">Client</th>
                  <th scope="col">Industry</th>
                  <th scope="col">Status</th>
                  <th scope="col">Renewal</th>
                </tr>
              </thead>
              <tbody>
                {items.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <Link href={`/clients/${c.id}`}>{c.name}</Link>
                    </td>
                    <td>{c.industry ?? "—"}</td>
                    <td>
                      <Badge tone={STATUS_TONE[c.status]}>{c.status}</Badge>
                    </td>
                    <td>{formatDate(c.renewal_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {cursor ? (
            <p>
              <Button busy={loading} onClick={() => void load(false, cursor)}>
                Load more
              </Button>
            </p>
          ) : null}
        </>
      )}

      <Dialog open={creating} title="New client" onClose={() => setCreating(false)}>
        <CreateClientForm
          onCreated={(c) => {
            setCreating(false);
            router.push(`/clients/${c.id}`);
          }}
        />
      </Dialog>
    </>
  );
}

function CreateClientForm({ onCreated }: { onCreated: (c: Client) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const fe = error instanceof ApiError ? error.fieldErrors : {};

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(undefined);
    try {
      const c = await api<Client>("POST", "/clients", {
        name: f.get("name"),
        industry: f.get("industry") || null,
        website: f.get("website") || null,
        status: f.get("status"),
        renewal_date: f.get("renewal_date") || null,
      });
      onCreated(c);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <FormError error={error} />
      <Field label="Client name" name="name" required maxLength={200} error={fe.name} autoFocus />
      <Field label="Industry" name="industry" maxLength={120} error={fe.industry} />
      <Field label="Website" name="website" maxLength={300} placeholder="https://example.com" error={fe.website} />
      <SelectField label="Status" name="status" defaultValue="onboarding">
        {STATUSES.filter((s) => s !== "archived").map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </SelectField>
      <Field label="Renewal date" name="renewal_date" type="date" error={fe.renewal_date} />
      <Button variant="primary" type="submit" busy={busy}>
        Create client
      </Button>
    </form>
  );
}
