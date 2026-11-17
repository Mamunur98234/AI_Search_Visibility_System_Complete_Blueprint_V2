"""Client CRM: clients and their contacts, brands, domains, projects (markets, competitors) and notes.

Every lookup is (tenant_id, id) and additionally filtered by the caller's client access scope;
anything outside it returns 404, indistinguishable from a missing record.
"""
import uuid
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import TenantContext, require
from app.core.errors import not_found
from app.core.permissions import Perm
from app.models import (
    AccessGrant,
    Brand,
    Client,
    Competitor,
    Contact,
    Domain,
    Language,
    Market,
    Membership,
    Note,
    Project,
    ProjectMarket,
)
from app.models.base import Base
from app.schemas import (
    BrandIn,
    BrandOut,
    BrandUpdate,
    ClientIn,
    ClientOut,
    ClientUpdate,
    CompetitorIn,
    CompetitorOut,
    CompetitorUpdate,
    ContactIn,
    ContactOut,
    ContactUpdate,
    DomainIn,
    DomainOut,
    DomainUpdate,
    NoteIn,
    NoteOut,
    Page,
    ProjectIn,
    ProjectMarketIn,
    ProjectMarketOut,
    ProjectOut,
    ProjectUpdate,
)
from app.services import audit

router = APIRouter(tags=["crm"])


def _snapshot(obj: Base, fields: list[str]) -> dict[str, Any]:
    return {f: getattr(obj, f) for f in fields}


def get_client(db: Session, ctx: TenantContext, client_id: uuid.UUID) -> Client:
    c = db.scalar(select(Client).where(Client.tenant_id == ctx.tenant_id, Client.id == client_id))
    if c is None or not ctx.can_access_client(c.id):
        raise not_found("Client")
    return c


def get_project(db: Session, ctx: TenantContext, project_id: uuid.UUID) -> Project:
    p = db.scalar(select(Project).where(Project.tenant_id == ctx.tenant_id, Project.id == project_id))
    if p is None or not ctx.can_access_client(p.client_id):
        raise not_found("Project")
    return p


def _check_owner(db: Session, ctx: TenantContext, membership_id: uuid.UUID | None) -> None:
    if membership_id and not db.scalar(select(Membership.id).where(Membership.tenant_id == ctx.tenant_id,
                                                                   Membership.id == membership_id)):
        raise HTTPException(422, "Owner must be a member of this workspace")


# ---------------- clients ----------------
CLIENT_FIELDS = ["name", "industry", "website", "status", "owner_membership_id", "renewal_date", "business_goals"]


@router.get("/clients", response_model=Page[ClientOut])
def list_clients(
    db: Session = Depends(get_db), ctx: TenantContext = Depends(require(Perm.CLIENT_READ)),
    status: str | None = Query(None, pattern="^(onboarding|active|paused|archived)$"),
    q: str | None = Query(None, max_length=100),
    cursor: uuid.UUID | None = None, limit: int = Query(50, ge=1, le=200),
) -> Page[ClientOut]:
    stmt = select(Client).where(Client.tenant_id == ctx.tenant_id, ctx.client_filter(Client.id))
    stmt = stmt.where(Client.status == status) if status else stmt.where(Client.status != "archived")
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Client.name.ilike(f"%{escaped}%", escape="\\"))
    if cursor:
        stmt = stmt.where(Client.id > cursor)
    rows = list(db.scalars(stmt.order_by(Client.id).limit(limit + 1)))
    return Page[ClientOut](items=[ClientOut.model_validate(c) for c in rows[:limit]],
                           next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None)


@router.post("/clients", status_code=201, response_model=ClientOut)
def create_client(body: ClientIn, request: Request, db: Session = Depends(get_db),
                  ctx: TenantContext = Depends(require(Perm.CLIENT_CREATE))) -> Client:
    _check_owner(db, ctx, body.owner_membership_id)
    c = Client(tenant_id=ctx.tenant_id, **body.model_dump())
    db.add(c)
    db.flush()
    if ctx.scope == "granted":
        # A scoped creator (e.g. Account Manager) automatically gets access to what they create.
        db.add(AccessGrant(tenant_id=ctx.tenant_id, membership_id=ctx.membership.id, client_id=c.id))
    audit.record(db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, action="client.created",
                 object_type="client", object_id=c.id, client_id=c.id, changes=body.model_dump(), request=request)
    return c


@router.get("/clients/{client_id}", response_model=ClientOut)
def read_client(client_id: uuid.UUID, db: Session = Depends(get_db),
                ctx: TenantContext = Depends(require(Perm.CLIENT_READ))) -> Client:
    return get_client(db, ctx, client_id)


@router.patch("/clients/{client_id}", response_model=ClientOut)
def update_client(client_id: uuid.UUID, body: ClientUpdate, request: Request, db: Session = Depends(get_db),
                  ctx: TenantContext = Depends(require(Perm.CLIENT_UPDATE))) -> Client:
    c = get_client(db, ctx, client_id)
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is None:
        raise HTTPException(422, "Name cannot be empty")
    if "status" in data and data["status"] is None:
        raise HTTPException(422, "Status cannot be empty")
    _check_owner(db, ctx, data.get("owner_membership_id"))
    before = _snapshot(c, CLIENT_FIELDS)
    for k, v in data.items():
        setattr(c, k, v)
    db.flush()
    changes = audit.diff(before, _snapshot(c, CLIENT_FIELDS))
    if changes:
        audit.record(db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, action="client.updated",
                     object_type="client", object_id=c.id, client_id=c.id, changes=changes, request=request)
    return c


@router.delete("/clients/{client_id}", status_code=204)
def archive_client(client_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                   ctx: TenantContext = Depends(require(Perm.CLIENT_DELETE))) -> Response:
    """Archives (soft-deletes). Permanent deletion is handled by retention/deletion workflows later."""
    c = get_client(db, ctx, client_id)
    if c.status != "archived":
        before = c.status
        c.status = "archived"
        audit.record(db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, action="client.archived",
                     object_type="client", object_id=c.id, client_id=c.id,
                     changes={"status": {"from": before, "to": "archived"}}, request=request)
    return Response(status_code=204)


# ---------------- generic child resources ----------------
def register_children(
    *, path: str, model: type[Any], parent: str, in_schema: type[BaseModel], update_schema: type[BaseModel],
    out_schema: type[BaseModel], read_perm: Perm, manage_perm: Perm, object_type: str, fields: list[str],
    order_by: str = "created_at", conflict_msg: str = "Duplicate record",
) -> None:
    """Registers list/create under /{parent}s/{id}/{path} and get/patch/delete under /{path}/{id}."""
    parent_col = f"{parent}_id"
    resolve_parent = get_client if parent == "client" else get_project

    def _client_id_of(db: Session, obj: Any) -> uuid.UUID:
        if parent == "client":
            return obj.client_id  # type: ignore[no-any-return]
        cid = db.scalar(select(Project.client_id).where(Project.tenant_id == obj.tenant_id,
                                                        Project.id == obj.project_id))
        assert cid is not None
        return cid

    def _get(db: Session, ctx: TenantContext, obj_id: uuid.UUID) -> Any:
        obj = db.scalar(select(model).where(model.tenant_id == ctx.tenant_id, model.id == obj_id))
        if obj is None or not ctx.can_access_client(_client_id_of(db, obj)):
            raise not_found(object_type.capitalize())
        return obj

    def _flush(db: Session) -> None:
        try:
            db.flush()
        except IntegrityError as exc:
            raise HTTPException(409, conflict_msg) from exc

    def list_items(parent_id: uuid.UUID, db: Session = Depends(get_db),
                   ctx: TenantContext = Depends(require(read_perm))) -> list[Any]:
        resolve_parent(db, ctx, parent_id)
        return list(db.scalars(select(model).where(model.tenant_id == ctx.tenant_id,
                                                   getattr(model, parent_col) == parent_id)
                               .order_by(getattr(model, order_by)).limit(500)))

    def create_item(parent_id: uuid.UUID, body: in_schema, request: Request,  # type: ignore[valid-type]
                    db: Session = Depends(get_db), ctx: TenantContext = Depends(require(manage_perm))) -> Any:
        par = resolve_parent(db, ctx, parent_id)
        data = body.model_dump()  # type: ignore[attr-defined]
        obj = model(tenant_id=ctx.tenant_id, **{parent_col: parent_id}, **data)
        db.add(obj)
        _flush(db)
        client_id = par.client_id if isinstance(par, Project) else par.id
        if model is Domain and data.get("is_primary"):
            _demote_other_primaries(db, ctx, obj)
        audit.record(db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, action=f"{object_type}.created",
                     object_type=object_type, object_id=obj.id, client_id=client_id, changes=data, request=request)
        return obj

    def read_item(item_id: uuid.UUID, db: Session = Depends(get_db),
                  ctx: TenantContext = Depends(require(read_perm))) -> Any:
        return _get(db, ctx, item_id)

    def update_item(item_id: uuid.UUID, body: update_schema, request: Request,  # type: ignore[valid-type]
                    db: Session = Depends(get_db), ctx: TenantContext = Depends(require(manage_perm))) -> Any:
        obj = _get(db, ctx, item_id)
        data = body.model_dump(exclude_unset=True)  # type: ignore[attr-defined]
        if "name" in data and data["name"] is None:
            raise HTTPException(422, "Name cannot be empty")
        before = _snapshot(obj, fields)
        for k, v in data.items():
            setattr(obj, k, [] if v is None and isinstance(before.get(k), list) else v)
        _flush(db)
        if model is Domain and data.get("is_primary"):
            _demote_other_primaries(db, ctx, obj)
        changes = audit.diff(before, _snapshot(obj, fields))
        if changes:
            audit.record(db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, action=f"{object_type}.updated",
                         object_type=object_type, object_id=obj.id, client_id=_client_id_of(db, obj),
                         changes=changes, request=request)
        return obj

    def delete_item(item_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                    ctx: TenantContext = Depends(require(manage_perm))) -> Response:
        obj = _get(db, ctx, item_id)
        snap = _snapshot(obj, fields)
        cid = _client_id_of(db, obj)
        db.delete(obj)
        audit.record(db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, action=f"{object_type}.deleted",
                     object_type=object_type, object_id=obj.id, client_id=cid, changes=snap, request=request)
        return Response(status_code=204)

    tag: list[str | Enum] = [object_type]
    router.add_api_route(f"/{parent}s/{{parent_id}}/{path}", list_items, methods=["GET"],
                         response_model=list[out_schema], tags=tag, name=f"list_{path}")  # type: ignore[valid-type]
    router.add_api_route(f"/{parent}s/{{parent_id}}/{path}", create_item, methods=["POST"], status_code=201,
                         response_model=out_schema, tags=tag, name=f"create_{object_type}")
    router.add_api_route(f"/{path}/{{item_id}}", read_item, methods=["GET"], response_model=out_schema, tags=tag,
                         name=f"read_{object_type}")
    if update_schema is not None:
        router.add_api_route(f"/{path}/{{item_id}}", update_item, methods=["PATCH"], response_model=out_schema,
                             tags=tag, name=f"update_{object_type}")
    router.add_api_route(f"/{path}/{{item_id}}", delete_item, methods=["DELETE"], status_code=204, tags=tag,
                         name=f"delete_{object_type}")


def _demote_other_primaries(db: Session, ctx: TenantContext, dom: Domain) -> None:
    db.execute(update(Domain).where(Domain.tenant_id == ctx.tenant_id, Domain.client_id == dom.client_id,
                                    Domain.id != dom.id).values(is_primary=False))


register_children(path="contacts", model=Contact, parent="client", in_schema=ContactIn, update_schema=ContactUpdate,
                  out_schema=ContactOut, read_perm=Perm.CLIENT_READ, manage_perm=Perm.CONTACT_MANAGE,
                  object_type="contact", fields=["name", "email", "phone", "job_title", "is_approver"],
                  order_by="name")
register_children(path="brands", model=Brand, parent="client", in_schema=BrandIn, update_schema=BrandUpdate,
                  out_schema=BrandOut, read_perm=Perm.CLIENT_READ, manage_perm=Perm.BRAND_MANAGE,
                  object_type="brand", fields=["name", "aliases", "description"], order_by="name")
register_children(path="domains", model=Domain, parent="client", in_schema=DomainIn, update_schema=DomainUpdate,
                  out_schema=DomainOut, read_perm=Perm.CLIENT_READ, manage_perm=Perm.DOMAIN_MANAGE,
                  object_type="domain", fields=["hostname", "is_primary"], order_by="hostname",
                  conflict_msg="This hostname is already registered in this workspace")
register_children(path="projects", model=Project, parent="client", in_schema=ProjectIn, update_schema=ProjectUpdate,
                  out_schema=ProjectOut, read_perm=Perm.CLIENT_READ, manage_perm=Perm.PROJECT_MANAGE,
                  object_type="project", fields=["name", "goals", "status", "start_date", "end_date"],
                  conflict_msg="Invalid project dates")
register_children(path="competitors", model=Competitor, parent="project", in_schema=CompetitorIn,
                  update_schema=CompetitorUpdate, out_schema=CompetitorOut, read_perm=Perm.CLIENT_READ,
                  manage_perm=Perm.COMPETITOR_MANAGE, object_type="competitor",
                  fields=["name", "domains", "aliases"], order_by="name")


# ---------------- project markets ----------------
@router.get("/projects/{project_id}/markets", response_model=list[ProjectMarketOut], tags=["project"])
def list_project_markets(project_id: uuid.UUID, db: Session = Depends(get_db),
                         ctx: TenantContext = Depends(require(Perm.CLIENT_READ))) -> list[ProjectMarket]:
    get_project(db, ctx, project_id)
    return list(db.scalars(select(ProjectMarket).where(ProjectMarket.tenant_id == ctx.tenant_id,
                                                       ProjectMarket.project_id == project_id)))


@router.post("/projects/{project_id}/markets", status_code=201, response_model=ProjectMarketOut, tags=["project"])
def add_project_market(project_id: uuid.UUID, body: ProjectMarketIn, request: Request, db: Session = Depends(get_db),
                       ctx: TenantContext = Depends(require(Perm.PROJECT_MANAGE))) -> ProjectMarket:
    p = get_project(db, ctx, project_id)
    if db.get(Market, body.market_code) is None or db.get(Language, body.language_code) is None:
        raise HTTPException(422, "Unknown market or language code")
    pm = ProjectMarket(tenant_id=ctx.tenant_id, project_id=p.id, **body.model_dump())
    db.add(pm)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "This market/language is already on the project") from exc
    audit.record(db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, action="project_market.added",
                 object_type="project_market", object_id=pm.id, client_id=p.client_id, changes=body.model_dump(),
                 request=request)
    return pm


@router.delete("/project-markets/{pm_id}", status_code=204, tags=["project"])
def remove_project_market(pm_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                          ctx: TenantContext = Depends(require(Perm.PROJECT_MANAGE))) -> Response:
    pm = db.scalar(select(ProjectMarket).where(ProjectMarket.tenant_id == ctx.tenant_id, ProjectMarket.id == pm_id))
    if pm is None:
        raise not_found("Project market")
    p = get_project(db, ctx, pm.project_id)
    db.delete(pm)
    audit.record(db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, action="project_market.removed",
                 object_type="project_market", object_id=pm.id, client_id=p.client_id,
                 changes={"market_code": pm.market_code, "language_code": pm.language_code}, request=request)
    return Response(status_code=204)


# ---------------- notes (internal) ----------------
@router.get("/clients/{client_id}/notes", response_model=list[NoteOut], tags=["note"])
def list_notes(client_id: uuid.UUID, db: Session = Depends(get_db),
               ctx: TenantContext = Depends(require(Perm.NOTE_READ))) -> list[Note]:
    get_client(db, ctx, client_id)
    return list(db.scalars(select(Note).where(Note.tenant_id == ctx.tenant_id, Note.client_id == client_id)
                           .order_by(Note.created_at.desc()).limit(500)))


@router.post("/clients/{client_id}/notes", status_code=201, response_model=NoteOut, tags=["note"])
def create_note(client_id: uuid.UUID, body: NoteIn, request: Request, db: Session = Depends(get_db),
                ctx: TenantContext = Depends(require(Perm.NOTE_MANAGE))) -> Note:
    get_client(db, ctx, client_id)
    n = Note(tenant_id=ctx.tenant_id, client_id=client_id, author_user_id=ctx.user_id, body=body.body)
    db.add(n)
    db.flush()
    audit.record(db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, action="note.created", object_type="note",
                 object_id=n.id, client_id=client_id, request=request)
    return n


@router.delete("/notes/{note_id}", status_code=204, tags=["note"])
def delete_note(note_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                ctx: TenantContext = Depends(require(Perm.NOTE_MANAGE))) -> Response:
    n = db.scalar(select(Note).where(Note.tenant_id == ctx.tenant_id, Note.id == note_id))
    if n is None or not ctx.can_access_client(n.client_id):
        raise not_found("Note")
    db.delete(n)
    audit.record(db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, action="note.deleted", object_type="note",
                 object_id=n.id, client_id=n.client_id, changes={"body": n.body}, request=request)
    return Response(status_code=204)
