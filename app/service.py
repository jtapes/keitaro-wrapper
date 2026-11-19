"""Бизнес-логика: создание кампании и правка офферов. Не зависит от FastAPI."""
from __future__ import annotations

import re
import secrets

from .config import settings
from .keitaro import KeitaroClient, KeitaroError

GOOGLE_URL = "https://google.com"
GEO_RE = re.compile(r"^[A-Za-z]{2}$")
STAT_KEYS = ("clicks", "campaign_unique_clicks", "conversions", "revenue", "cost", "profit")


class ValidationError(Exception):
    pass


def distribute_shares(count: int) -> list[int]:
    """Делит 100% поровну; остаток раздаётся по одному пункту с первых.

    3 оффера -> [34, 33, 33]; в сумме всегда ровно 100.
    """
    if count <= 0:
        return []
    base, rest = divmod(100, count)
    return [base + (1 if i < rest else 0) for i in range(count)]


def normalize_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValidationError("Укажите название кампании")
    prefix = settings.campaign_prefix
    if prefix and not name.startswith(prefix):
        name = prefix + name
    if len(name) > 200:
        raise ValidationError("Название слишком длинное")
    return name


def normalize_geo(geo: str) -> str:
    geo = (geo or "").strip()
    if not GEO_RE.match(geo):
        raise ValidationError("Гео - двухбуквенный код страны, например JP или AU")
    return geo.upper()


def make_alias(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "campaign"
    return f"{slug}-{secrets.token_hex(3)}"


def _offer_payload(offer_ids: list[int]) -> list[dict]:
    return [
        {"offer_id": oid, "share": share, "state": "active"}
        for oid, share in zip(offer_ids, distribute_shares(len(offer_ids)))
    ]


def create_campaign(kt: KeitaroClient, *, name: str, geo: str, offer_id: int,
                    domain_id: int, group_id: int, traffic_source_id: int) -> dict:
    name = normalize_name(name)
    geo = normalize_geo(geo)
    if offer_id <= 0:
        raise ValidationError("Укажите ID оффера")
    if not (domain_id and group_id and traffic_source_id):
        raise ValidationError("Выберите домен, группу и источник")

    campaign = kt.create_campaign({
        "name": name,
        "alias": make_alias(name),
        "type": "position",
        "state": "active",
        "domain_id": domain_id,
        "group_id": group_id,
        "traffic_source_id": traffic_source_id,
    })
    cid = campaign["id"]
    try:
        # поток 1: все из страны -> Google
        s1 = kt.create_stream({
            "campaign_id": cid, "name": f"{geo} -> Google", "type": "regular",
            "schema": "redirect", "action_type": "http", "action_payload": GOOGLE_URL,
            "position": 1, "state": "active", "collect_clicks": True,
            "filters": [{"name": "country", "mode": "accept", "payload": [geo]}],
        })
        # поток 2: выбранный оффер (100%)
        s2 = kt.create_stream({
            "campaign_id": cid, "name": "Offers", "type": "regular",
            "schema": "landings", "action_type": "http",
            "position": 2, "state": "active", "collect_clicks": True,
            "offers": _offer_payload([offer_id]),
        })
    except Exception:
        # не оставляем полусобранную кампанию
        try:
            kt.delete_campaign(cid)
        except KeitaroError:
            pass
        raise
    return {"campaign": campaign, "streams": [s1, s2]}


def _find_offers_stream(kt: KeitaroClient, campaign_id: int, stream_id: int) -> dict:
    for s in kt.streams(campaign_id):
        if s["id"] == stream_id:
            if s.get("schema") != "landings":
                raise ValidationError("В этом потоке нет офферов (это редирект)")
            return s
    raise ValidationError("Поток не найден в этой кампании")


def add_offer(kt: KeitaroClient, campaign_id: int, stream_id: int, offer_id: int) -> dict:
    stream = _find_offers_stream(kt, campaign_id, stream_id)
    ids = [o["offer_id"] for o in stream.get("offers", [])]
    if offer_id in ids:
        raise ValidationError(f"Оффер {offer_id} уже есть в потоке")
    return kt.update_stream(stream_id, {"offers": _offer_payload(ids + [offer_id])})


def remove_offer(kt: KeitaroClient, campaign_id: int, stream_id: int, offer_id: int) -> dict:
    stream = _find_offers_stream(kt, campaign_id, stream_id)
    ids = [o["offer_id"] for o in stream.get("offers", [])]
    if offer_id not in ids:
        raise ValidationError(f"Оффера {offer_id} нет в потоке")
    ids.remove(offer_id)
    return kt.update_stream(stream_id, {"offers": _offer_payload(ids)})


def _stat(row: dict | None) -> dict:
    row = row or {}
    return {k: row.get(k, 0) or 0 for k in STAT_KEYS}


def campaign_view(kt: KeitaroClient, campaign_id: int) -> dict:
    """Кампания + потоки + офферы с названиями и статистикой за всё время."""
    campaign = kt.campaign(campaign_id)
    streams = kt.streams(campaign_id)

    offer_stats = {r["offer_id"]: r for r in kt.report(campaign_id, ["offer_id"]) if "offer_id" in r}
    stream_stats = {r["stream_id"]: r for r in kt.report(campaign_id, ["stream_id"]) if "stream_id" in r}

    names: dict[int, str] = {}

    def offer_name(oid: int) -> str:
        if oid not in names:
            try:
                names[oid] = kt.offer(oid).get("name", f"Оффер {oid}")
            except KeitaroError:
                names[oid] = f"Оффер {oid} (недоступен)"
        return names[oid]

    out_streams = []
    for s in streams:
        offers = [{
            "offer_id": o["offer_id"],
            "name": offer_name(o["offer_id"]),
            "share": o.get("share", 0),
            "state": o.get("state"),
            "stats": _stat(offer_stats.get(o["offer_id"])),
        } for o in s.get("offers", [])]
        filters = [{"name": f["name"], "mode": f.get("mode"), "payload": f.get("payload")}
                   for f in s.get("filters", [])]
        out_streams.append({
            "id": s["id"], "name": s["name"], "schema": s.get("schema"),
            "action_payload": s.get("action_payload"), "filters": filters,
            "editable": s.get("schema") == "landings", "offers": offers,
            "share_total": sum(o["share"] for o in offers),
            "stats": _stat(stream_stats.get(s["id"])),
        })
    return {
        "id": campaign["id"], "name": campaign["name"], "state": campaign.get("state"),
        "domain": campaign.get("domain"), "group": campaign.get("group"),
        "alias": campaign.get("alias"), "streams": out_streams,
    }
