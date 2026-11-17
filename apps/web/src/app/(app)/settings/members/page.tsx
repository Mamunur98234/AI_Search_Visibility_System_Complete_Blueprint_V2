"use client";

import { useState } from "react";

import {
  Badge,
  Button,
  Dialog,
  DisabledHint,
  ErrorState,
  Field,
  FormError,
  Loading,
  SelectField,
  formatDate,
  toast,
} from "@/components/ui";
import { api, ApiError, type Schemas } from "@/lib/api";
import { ROLE_LABELS, TENANT_SCOPED_ROLES } from "@/lib/nav";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

type Member = Schemas["MemberOut"];
type Client = Schemas["ClientOut"];

export default function MembersPage() {
  const { me, can } = useSession();
  const members = useApi<Member[]>("/members");
  const invites = useApi<Schemas["InvitationOut"][]>("/invitations");
  const clients = useApi<Schemas["Page_ClientOut_"]>("/clients?limit=200");
  const [inviting, setInviting] = useState(false);
  const [editing, setEditing] = useState<Member | null>(null);
  const clientName = (id: string) => clients.data?.items.find((c) => c.id === id)?.name ?? "Unknown client";
  const isOwner = me.active_tenant?.role === "agency_owner";

  async function revoke(id: string, email: string) {
    if (!window.confirm(`Revoke the invitation for ${email}?`)) return;
    try {
      await api("DELETE", `/invitations/${id}`);
      toast("Invitation revoked");
      await invites.reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed");
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Members</h1>
          <p className="muted">People with access to this workspace and what they can see.</p>
        </div>
        {can("member.invite") ? (
          <Button variant="primary" onClick={() => setInviting(true)}>
            Invite member
          </Button>
        ) : (
          <DisabledHint label="Invite member" reason="Your role cannot invite members." />
        )}
      </div>

      {members.loading && !members.data ? (
        <Loading />
      ) : members.error ? (
        <ErrorState error={members.error} onRetry={members.reload} />
      ) : (
        <div className="table-wrap">
          <table>
            <caption className="sr-only">Members</caption>
            <thead>
              <tr>
                <th scope="col">Member</th>
                <th scope="col">Role</th>
                <th scope="col">Client access</th>
                <th scope="col">2FA</th>
                <th scope="col">Status</th>
                <th scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {members.data?.map((m) => (
                <tr key={m.id}>
                  <td>
                    {m.name}
                    <div className="muted small">{m.email}</div>
                  </td>
                  <td>{ROLE_LABELS[m.role] ?? m.role}</td>
                  <td>
                    {TENANT_SCOPED_ROLES.has(m.role)
                      ? "All clients"
                      : m.client_ids.length
                        ? m.client_ids.map(clientName).join(", ")
                        : "No clients"}
                  </td>
                  <td>{m.mfa_enabled ? <Badge tone="ok">On</Badge> : <Badge>Off</Badge>}</td>
                  <td>{m.status === "active" ? <Badge tone="ok">Active</Badge> : <Badge tone="bad">Disabled</Badge>}</td>
                  <td>
                    {can("member.update") && m.user_id !== me.id && (m.role !== "agency_owner" || isOwner) ? (
                      <Button onClick={() => setEditing(m)} aria-label={`Edit ${m.name}`}>
                        Edit
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2 className="section-gap">Pending invitations</h2>
      {invites.loading && !invites.data ? (
        <Loading />
      ) : invites.error ? (
        <ErrorState error={invites.error} onRetry={invites.reload} />
      ) : invites.data?.length ? (
        <div className="table-wrap">
          <table>
            <caption className="sr-only">Pending invitations</caption>
            <thead>
              <tr>
                <th scope="col">Email</th>
                <th scope="col">Role</th>
                <th scope="col">Expires</th>
                <th scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {invites.data.map((i) => (
                <tr key={i.id}>
                  <td>{i.email}</td>
                  <td>{ROLE_LABELS[i.role] ?? i.role}</td>
                  <td>{formatDate(i.expires_at)}</td>
                  <td>
                    {can("member.invite") ? (
                      <Button variant="danger" onClick={() => void revoke(i.id, i.email)}>
                        Revoke
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">No pending invitations.</p>
      )}

      <Dialog open={inviting} title="Invite member" onClose={() => setInviting(false)}>
        <MemberForm
          mode="invite"
          clients={clients.data?.items ?? []}
          canGrantOwner={isOwner}
          onDone={async () => {
            setInviting(false);
            toast("Invitation sent");
            await invites.reload();
          }}
        />
      </Dialog>
      <Dialog open={!!editing} title={`Edit ${editing?.name ?? "member"}`} onClose={() => setEditing(null)}>
        {editing ? (
          <MemberForm
            mode="edit"
            member={editing}
            clients={clients.data?.items ?? []}
            canGrantOwner={isOwner}
            canRemove={can("member.remove")}
            onDone={async (msg) => {
              setEditing(null);
              toast(msg);
              await members.reload();
            }}
          />
        ) : null}
      </Dialog>
    </>
  );
}

function MemberForm({
  mode,
  member,
  clients,
  canGrantOwner,
  canRemove,
  onDone,
}: {
  mode: "invite" | "edit";
  member?: Member;
  clients: Client[];
  canGrantOwner: boolean;
  canRemove?: boolean;
  onDone: (message: string) => Promise<void>;
}) {
  const [role, setRole] = useState(member?.role ?? "account_manager");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const fe = error instanceof ApiError ? error.fieldErrors : {};
  const scoped = !TENANT_SCOPED_ROLES.has(role);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const client_ids = scoped ? f.getAll("client_ids").map(String) : [];
    setBusy(true);
    setError(undefined);
    try {
      if (mode === "invite") {
        await api("POST", "/members/invite", { email: f.get("email"), role, client_ids });
        await onDone("Invitation sent");
      } else {
        await api("PATCH", `/members/${member!.id}`, { role, status: f.get("status"), client_ids });
        await onDone("Member updated");
      }
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!member || !window.confirm(`Remove ${member.name} from this workspace?`)) return;
    try {
      await api("DELETE", `/members/${member.id}`);
      await onDone("Member removed");
    } catch (err) {
      setError(err);
    }
  }

  return (
    <form onSubmit={submit}>
      <FormError error={error} />
      {mode === "invite" ? <Field label="Email" name="email" type="email" required error={fe.email} autoFocus /> : null}
      <SelectField label="Role" name="role" value={role} onChange={(e) => setRole(e.target.value)}>
        {Object.entries(ROLE_LABELS)
          .filter(([k]) => k !== "agency_owner" || canGrantOwner)
          .map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
      </SelectField>
      {scoped ? (
        <fieldset>
          <legend>Client access</legend>
          <p className="hint">This role only sees the clients selected here.</p>
          {clients.length === 0 ? <p className="muted small">No clients exist yet.</p> : null}
          {clients.map((c) => (
            <label key={c.id} className="checkbox">
              <input type="checkbox" name="client_ids" value={c.id} defaultChecked={member?.client_ids.includes(c.id)} />
              {c.name}
            </label>
          ))}
        </fieldset>
      ) : (
        <p className="hint">This role can see every client in the workspace.</p>
      )}
      {mode === "edit" ? (
        <SelectField label="Status" name="status" defaultValue={member?.status}>
          <option value="active">Active</option>
          <option value="disabled">Disabled</option>
        </SelectField>
      ) : null}
      <div className="row">
        <Button variant="primary" type="submit" busy={busy}>
          {mode === "invite" ? "Send invitation" : "Save"}
        </Button>
        {mode === "edit" && canRemove ? (
          <Button type="button" variant="danger" onClick={() => void remove()}>
            Remove from workspace
          </Button>
        ) : null}
      </div>
    </form>
  );
}
