"""Roles and permissions. Code is the single source of truth; GET /roles exposes it read-only.

Scope:
  tenant  - role sees every client in the tenant.
  granted - role sees only clients listed in its membership's access grants.
"""
from enum import StrEnum
from typing import Literal


class Perm(StrEnum):
    TENANT_READ = "tenant.read"
    TENANT_UPDATE = "tenant.update"
    MEMBER_READ = "member.read"
    MEMBER_INVITE = "member.invite"
    MEMBER_UPDATE = "member.update"
    MEMBER_REMOVE = "member.remove"
    AUDIT_LOG_READ = "audit_log.read"
    CLIENT_READ = "client.read"
    CLIENT_CREATE = "client.create"
    CLIENT_UPDATE = "client.update"
    CLIENT_DELETE = "client.delete"
    CONTACT_MANAGE = "contact.manage"
    BRAND_MANAGE = "brand.manage"
    DOMAIN_MANAGE = "domain.manage"
    PROJECT_MANAGE = "project.manage"
    COMPETITOR_MANAGE = "competitor.manage"
    NOTE_READ = "note.read"
    NOTE_MANAGE = "note.manage"
    DOMAIN_VERIFY = "domain.verify"
    CRAWL_RUN = "crawl.run"
    ISSUE_MANAGE = "issue.manage"


PERMISSION_DESCRIPTIONS: dict[Perm, str] = {
    Perm.TENANT_READ: "View agency workspace settings",
    Perm.TENANT_UPDATE: "Change agency workspace settings",
    Perm.MEMBER_READ: "View members and roles",
    Perm.MEMBER_INVITE: "Invite members",
    Perm.MEMBER_UPDATE: "Change member roles and client access",
    Perm.MEMBER_REMOVE: "Remove members",
    Perm.AUDIT_LOG_READ: "View the audit log",
    Perm.CLIENT_READ: "View clients and their CRM records",
    Perm.CLIENT_CREATE: "Create clients",
    Perm.CLIENT_UPDATE: "Edit clients",
    Perm.CLIENT_DELETE: "Archive clients",
    Perm.CONTACT_MANAGE: "Create, edit and delete client contacts",
    Perm.BRAND_MANAGE: "Create, edit and delete brands",
    Perm.DOMAIN_MANAGE: "Create, edit and delete domains",
    Perm.PROJECT_MANAGE: "Create, edit and delete projects and markets",
    Perm.COMPETITOR_MANAGE: "Create, edit and delete competitors",
    Perm.NOTE_READ: "View internal notes",
    Perm.NOTE_MANAGE: "Create and delete internal notes",
    Perm.DOMAIN_VERIFY: "Start and check domain ownership verification",
    Perm.CRAWL_RUN: "Start, pause, resume and cancel crawls of verified domains",
    Perm.ISSUE_MANAGE: "Triage technical audit findings (accept / won't fix / reopen)",
}

Scope = Literal["tenant", "granted"]

ALL = frozenset(Perm)
_CRM_EDIT = {
    Perm.CLIENT_READ, Perm.CLIENT_UPDATE, Perm.CONTACT_MANAGE, Perm.BRAND_MANAGE,
    Perm.DOMAIN_MANAGE, Perm.PROJECT_MANAGE, Perm.COMPETITOR_MANAGE, Perm.NOTE_READ, Perm.NOTE_MANAGE,
}

ROLES: dict[str, dict[str, object]] = {
    "agency_owner": {"name": "Agency Owner", "scope": "tenant", "perms": ALL},
    "agency_admin": {"name": "Agency Admin", "scope": "tenant", "perms": ALL},
    "account_manager": {
        "name": "Account Manager", "scope": "granted",
        "perms": frozenset(_CRM_EDIT | {Perm.CLIENT_CREATE, Perm.MEMBER_READ, Perm.DOMAIN_VERIFY, Perm.CRAWL_RUN,
                                        Perm.ISSUE_MANAGE}),
    },
    "seo_analyst": {
        "name": "SEO/AEO Analyst", "scope": "granted",
        "perms": frozenset({Perm.CLIENT_READ, Perm.BRAND_MANAGE, Perm.DOMAIN_MANAGE, Perm.PROJECT_MANAGE,
                            Perm.COMPETITOR_MANAGE, Perm.NOTE_READ, Perm.NOTE_MANAGE, Perm.DOMAIN_VERIFY,
                            Perm.CRAWL_RUN, Perm.ISSUE_MANAGE}),
    },
    "content_editor": {
        "name": "Content Editor", "scope": "granted",
        "perms": frozenset({Perm.CLIENT_READ, Perm.NOTE_READ, Perm.NOTE_MANAGE}),
    },
    "technical_implementer": {
        "name": "Technical Implementer", "scope": "granted",
        "perms": frozenset({Perm.CLIENT_READ, Perm.NOTE_READ, Perm.NOTE_MANAGE, Perm.ISSUE_MANAGE}),
    },
    "client_admin": {"name": "Client Admin", "scope": "granted", "perms": frozenset({Perm.CLIENT_READ})},
    "client_viewer": {"name": "Client Viewer", "scope": "granted", "perms": frozenset({Perm.CLIENT_READ})},
    "auditor": {
        "name": "Auditor (read-only)", "scope": "tenant",
        "perms": frozenset({Perm.TENANT_READ, Perm.MEMBER_READ, Perm.AUDIT_LOG_READ, Perm.CLIENT_READ,
                            Perm.NOTE_READ}),
    },
}

ROLE_KEYS = tuple(ROLES.keys())
OWNER_ROLE = "agency_owner"


def role_perms(role: str) -> frozenset[Perm]:
    perms = ROLES[role]["perms"]
    assert isinstance(perms, frozenset)
    return perms


def role_scope(role: str) -> Scope:
    scope = ROLES[role]["scope"]
    assert scope in ("tenant", "granted")
    return scope
