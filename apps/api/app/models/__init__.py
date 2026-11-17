from app.models.base import Base
from app.models.crm import (
    Brand,
    Client,
    Competitor,
    Contact,
    Domain,
    Language,
    Market,
    Note,
    Project,
    ProjectMarket,
)
from app.models.identity import (
    AccessEvent,
    AccessGrant,
    AuditLog,
    AuthSession,
    Invitation,
    Membership,
    PasswordResetToken,
    Tenant,
    User,
)

__all__ = [
    "AccessEvent", "AccessGrant", "AuditLog", "AuthSession", "Base", "Brand", "Client", "Competitor", "Contact",
    "Domain", "Invitation", "Language", "Market", "Membership", "Note", "PasswordResetToken", "Project",
    "ProjectMarket", "Tenant", "User",
]

TENANT_TABLES = [
    "memberships", "access_grants", "invitations", "audit_log", "clients", "contacts", "brands", "domains",
    "projects", "project_markets", "competitors", "notes",
]
