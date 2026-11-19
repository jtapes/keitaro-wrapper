from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import service
from .config import settings
from .db import get_db
from .keitaro import KeitaroClient, KeitaroError
from .models import CampaignLog

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Keitaro wrapper")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def get_keitaro() -> KeitaroClient:
    return KeitaroClient()


@app.exception_handler(KeitaroError)
async def keitaro_error_handler(_, exc: KeitaroError):
    code = exc.status if exc.status in (400, 401, 403, 404, 422) else 502
    return JSONResponse(status_code=code, content={"detail": f"Keitaro: {exc.detail}"})


@app.exception_handler(service.ValidationError)
async def validation_error_handler(_, exc: service.ValidationError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


class CampaignIn(BaseModel):
    name: str = Field(min_length=1)
    geo: str
    offer_id: int
    domain_id: int | None = None
    group_id: int | None = None
    traffic_source_id: int | None = None


class OfferIn(BaseModel):
    offer_id: int


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/meta")
def meta(kt: KeitaroClient = Depends(get_keitaro)):
    """Справочники для формы: домены, группы, источники, офферы и значения по умолчанию."""
    return {
        "prefix": settings.campaign_prefix,
        "defaults": {
            "domain_id": settings.default_domain_id,
            "group_id": settings.default_group_id,
            "traffic_source_id": settings.default_traffic_source_id,
        },
        "domains": [{"id": d["id"], "name": d["name"]} for d in kt.domains()],
        "groups": [{"id": g["id"], "name": g["name"]} for g in kt.groups()],
        "sources": [{"id": s["id"], "name": s["name"]} for s in kt.traffic_sources()],
        "offers": [{"id": o["id"], "name": o["name"]} for o in kt.offers()],
    }


@app.get("/api/campaigns")
def list_campaigns(q: str = "", limit: int = 50, kt: KeitaroClient = Depends(get_keitaro)):
    items = kt.campaigns()
    if q:
        needle = q.lower()
        items = [c for c in items if needle in c["name"].lower() or needle == str(c["id"])]
    items.sort(key=lambda c: c["id"], reverse=True)
    return [{"id": c["id"], "name": c["name"], "state": c.get("state")} for c in items[:limit]]


@app.post("/api/campaigns", status_code=201)
def create_campaign(body: CampaignIn, kt: KeitaroClient = Depends(get_keitaro),
                    db: Session = Depends(get_db)):
    result = service.create_campaign(
        kt,
        name=body.name,
        geo=body.geo,
        offer_id=body.offer_id,
        domain_id=body.domain_id or settings.default_domain_id,
        group_id=body.group_id or settings.default_group_id,
        traffic_source_id=body.traffic_source_id or settings.default_traffic_source_id,
    )
    c = result["campaign"]
    db.add(CampaignLog(keitaro_campaign_id=c["id"], name=c["name"], geo=service.normalize_geo(body.geo),
                       offer_id=body.offer_id, action="created"))
    db.commit()
    return {"id": c["id"], "name": c["name"], "alias": c.get("alias"),
            "streams": [{"id": s["id"], "name": s["name"]} for s in result["streams"]]}


@app.get("/api/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, kt: KeitaroClient = Depends(get_keitaro)):
    return service.campaign_view(kt, campaign_id)


@app.post("/api/campaigns/{campaign_id}/streams/{stream_id}/offers")
def add_offer(campaign_id: int, stream_id: int, body: OfferIn,
              kt: KeitaroClient = Depends(get_keitaro), db: Session = Depends(get_db)):
    service.add_offer(kt, campaign_id, stream_id, body.offer_id)
    db.add(CampaignLog(keitaro_campaign_id=campaign_id, name="", offer_id=body.offer_id, action="offer_added"))
    db.commit()
    return service.campaign_view(kt, campaign_id)


@app.delete("/api/campaigns/{campaign_id}/streams/{stream_id}/offers/{offer_id}")
def remove_offer(campaign_id: int, stream_id: int, offer_id: int,
                 kt: KeitaroClient = Depends(get_keitaro), db: Session = Depends(get_db)):
    service.remove_offer(kt, campaign_id, stream_id, offer_id)
    db.add(CampaignLog(keitaro_campaign_id=campaign_id, name="", offer_id=offer_id, action="offer_removed"))
    db.commit()
    return service.campaign_view(kt, campaign_id)


@app.get("/api/history")
def history(limit: int = 30, db: Session = Depends(get_db)):
    rows = db.execute(select(CampaignLog).order_by(CampaignLog.id.desc()).limit(limit)).scalars()
    return [{"id": r.id, "campaign_id": r.keitaro_campaign_id, "name": r.name, "geo": r.geo,
             "offer_id": r.offer_id, "action": r.action, "at": r.created_at.isoformat()} for r in rows]


@app.get("/health")
def health():
    return {"ok": True}
