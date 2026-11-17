"use client";

import { useEffect, useState } from "react";

import { Button, EmptyState, ErrorState, Field, Loading, formatDateTime } from "@/components/ui";
import { api, type Schemas } from "@/lib/api";

type Entry = Schemas["AuditLogOut"];

function Changes({ changes }: { changes: Entry["changes"] }) {
  if (!changes || Object.keys(changes).length === 0) return <span className="muted">—</span>;
  return (
    <details>
      <summary>{Object.keys(changes).length} field(s)</summary>
      {/* Rendered as text only. */}
      <pre className="pre-wrap small">{JSON.stringify(changes, null, 2)}</pre>
    </details>
  );
}

export default function AuditLogPage() {
  const [action, setAction] = useState("");
  const [objectType, setObjectType] = useState("");
  const [items, setItems] = useState<Entry[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>();

  async function load(reset: boolean, after?: string | null) {
    setLoading(true);
    setError(undefined);
    const p = new URLSearchParams({ limit: "50" });
    if (action.trim()) p.set("action", action.trim());
    if (objectType.trim()) p.set("object_type", objectType.trim());
    if (!reset && after) p.set("cursor", after);
    try {
      const page = await api<Schemas["Page_AuditLogOut_"]>("GET", `/audit-log?${p}`);
      setItems((prev) => (reset ? page.items : [...prev, ...page.items]));
      setCursor(page.next_cursor ?? null);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const t = setTimeout(() => void load(true), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload on filter change only
  }, [action, objectType]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Audit log</h1>
          <p className="muted">Append-only record of changes in this workspace. Times are UTC.</p>
        </div>
      </div>
      <div className="row" role="search">
        <Field label="Action" name="action" placeholder="e.g. client.updated" value={action}
          onChange={(e) => setAction(e.target.value)} />
        <Field label="Object type" name="object_type" placeholder="e.g. client" value={objectType}
          onChange={(e) => setObjectType(e.target.value)} />
      </div>
      {error ? (
        <ErrorState error={error} onRetry={() => void load(true)} />
      ) : loading && items.length === 0 ? (
        <Loading />
      ) : items.length === 0 ? (
        <EmptyState title="No matching events" />
      ) : (
        <>
          <div className="table-wrap">
            <table>
              <caption className="sr-only">Audit events</caption>
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Actor</th>
                  <th scope="col">Action</th>
                  <th scope="col">Object</th>
                  <th scope="col">Changes</th>
                </tr>
              </thead>
              <tbody>
                {items.map((e) => (
                  <tr key={e.id}>
                    <td>{formatDateTime(e.created_at)}</td>
                    <td>{e.actor_name ?? "—"}</td>
                    <td>
                      <code>{e.action}</code>
                    </td>
                    <td>
                      {e.object_type}
                      <div className="muted small">{e.object_id ?? ""}</div>
                    </td>
                    <td>
                      <Changes changes={e.changes} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {cursor ? (
            <p>
              <Button busy={loading} onClick={() => void load(false, cursor)}>
                Load older events
              </Button>
            </p>
          ) : null}
        </>
      )}
    </>
  );
}
