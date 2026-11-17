"""Seed a clearly labelled DEMO workspace for local development and walkthroughs.

    DEMO_PASSWORD='choose-a-local-password' python -m scripts.seed_demo

All organizations are fictional and use reserved example.* domains. The script refuses to run when
APP_ENV=production. It is idempotent: if the demo owner already exists it does nothing.
"""
import os
import sys

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import session_factory, set_db_context
from app.core.ids import uuid7
from app.core.security import hash_password
from app.models import (
    AccessGrant,
    Brand,
    Client,
    Competitor,
    Contact,
    Domain,
    Membership,
    Note,
    Project,
    ProjectMarket,
    Tenant,
    User,
)
from app.models.base import utcnow
from app.services import audit

DEMO_OWNER = "owner@demo-agency.example"


def main() -> int:
    if get_settings().is_production:
        print("Refusing to seed demo data in production.")
        return 1
    password = os.environ.get("DEMO_PASSWORD", "")
    if len(password) < 12:
        print("Set DEMO_PASSWORD (12+ characters) for the demo accounts.")
        return 1
    db = session_factory()()
    try:
        if db.scalar(select(User.id).where(func.lower(User.email) == DEMO_OWNER)):
            print("Demo data already present; nothing to do.")
            return 0
        pw = hash_password(password)
        now = utcnow()
        users = {
            "owner": User(email=DEMO_OWNER, name="Avery Owner (demo)", password_hash=pw, password_changed_at=now),
            "am": User(email="am@demo-agency.example", name="Jordan Manager (demo)", password_hash=pw,
                       password_changed_at=now),
            "analyst": User(email="analyst@demo-agency.example", name="Morgan Analyst (demo)", password_hash=pw,
                            password_changed_at=now),
            "viewer": User(email="viewer@northwind.example", name="Casey Client (demo)", password_hash=pw,
                           password_changed_at=now),
        }
        db.add_all(users.values())
        db.flush()
        tenant = Tenant(id=uuid7(), name="Demo Agency (demo data)", slug="demo-agency")
        set_db_context(db, tenant_id=tenant.id, user_id=users["owner"].id)
        db.add(tenant)
        db.flush()
        mem = {
            "owner": Membership(tenant_id=tenant.id, user_id=users["owner"].id, role="agency_owner"),
            "am": Membership(tenant_id=tenant.id, user_id=users["am"].id, role="account_manager"),
            "analyst": Membership(tenant_id=tenant.id, user_id=users["analyst"].id, role="seo_analyst"),
            "viewer": Membership(tenant_id=tenant.id, user_id=users["viewer"].id, role="client_viewer"),
        }
        db.add_all(mem.values())
        db.flush()

        specs = [
            ("Northwind Analytics (demo)", "B2B SaaS", "active", "northwind.example", ["Competitor X (demo)"]),
            ("Contoso Payroll (demo)", "HR software", "onboarding", "contoso.example", ["Competitor Y (demo)"]),
            ("Fabrikam CRM (demo)", "CRM software", "active", "fabrikam.example", []),
        ]
        clients = []
        for name, industry, status, host, comps in specs:
            c = Client(tenant_id=tenant.id, name=name, industry=industry, status=status,
                       owner_membership_id=mem["am"].id, website=f"https://{host}",
                       business_goals="Demo goal: improve observed visibility for priority topics.")
            db.add(c)
            db.flush()
            clients.append(c)
            db.add(Brand(tenant_id=tenant.id, client_id=c.id, name=name.replace(" (demo)", ""),
                         aliases=[name.split()[0]]))
            db.add(Domain(tenant_id=tenant.id, client_id=c.id, hostname=host, is_primary=True))
            db.add(Contact(tenant_id=tenant.id, client_id=c.id, name="Sam Approver (demo)",
                           email=f"sam@{host}", job_title="Marketing Director", is_approver=True))
            p = Project(tenant_id=tenant.id, client_id=c.id, name="AI search visibility (demo)")
            db.add(p)
            db.flush()
            db.add(ProjectMarket(tenant_id=tenant.id, project_id=p.id, market_code="US", language_code="en"))
            for comp in comps:
                db.add(Competitor(tenant_id=tenant.id, project_id=p.id, name=comp,
                                  domains=[comp.split()[1].lower() + "-competitor.example"]))
            db.add(Note(tenant_id=tenant.id, client_id=c.id, author_user_id=users["owner"].id,
                        body="Demo note: kickoff call scheduled."))
            audit.record(db, tenant_id=tenant.id, actor_user_id=users["owner"].id, action="client.created",
                         object_type="client", object_id=c.id, client_id=c.id, changes={"name": name, "seed": True})
        for c in clients[:2]:
            db.add(AccessGrant(tenant_id=tenant.id, membership_id=mem["am"].id, client_id=c.id))
        db.add(AccessGrant(tenant_id=tenant.id, membership_id=mem["analyst"].id, client_id=clients[0].id))
        db.add(AccessGrant(tenant_id=tenant.id, membership_id=mem["viewer"].id, client_id=clients[0].id))
        db.commit()
        print("Demo workspace created. Sign in with any of:")
        for u in users.values():
            print(f"  {u.email}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
