from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import Principal, authenticated, public
from app.models import Language, Market
from app.schemas import LanguageOut, MarketOut

router = APIRouter(tags=["reference"])


@router.get("/reference/markets", response_model=list[MarketOut])
def markets(db: Session = Depends(get_db), p: Principal = Depends(authenticated)) -> list[Market]:
    return list(db.scalars(select(Market).order_by(Market.name)))


@router.get("/reference/languages", response_model=list[LanguageOut])
def languages(db: Session = Depends(get_db), p: Principal = Depends(authenticated)) -> list[Language]:
    return list(db.scalars(select(Language).order_by(Language.name)))


health_router = APIRouter(tags=["ops"])


@health_router.get("/healthz", dependencies=[Depends(public)])
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@health_router.get("/readyz", dependencies=[Depends(public)])
def readyz(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ready"}
