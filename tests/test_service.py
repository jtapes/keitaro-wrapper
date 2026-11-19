import json

import httpx
import pytest

from app import service
from app.keitaro import KeitaroClient


class FakeKeitaro:
    """Мини-эмуляция Keitaro Admin API на httpx.MockTransport."""

    def __init__(self, fail_second_stream: bool = False):
        self.campaigns: dict[int, dict] = {}
        self.streams: dict[int, dict] = {}
        self.offers = {10, 11, 12, 13}
        self.next_id = 100
        self.fail_second_stream = fail_second_stream
        self.deleted: list[int] = []

    def _id(self) -> int:
        self.next_id += 1
        return self.next_id

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.replace("/admin_api/v1", "")
        method = request.method
        body = json.loads(request.content) if request.content else {}

        if method == "GET" and path.startswith("/offers/"):
            oid = int(path.rsplit("/", 1)[1])
            if oid in self.offers:
                return httpx.Response(200, json={"id": oid, "name": f"Offer {oid}"})
            return httpx.Response(404, text="not found")
        if method == "POST" and path == "/campaigns":
            cid = self._id()
            self.campaigns[cid] = {**body, "id": cid}
            return httpx.Response(200, json=self.campaigns[cid])
        if method == "DELETE" and path.startswith("/campaigns/"):
            cid = int(path.rsplit("/", 1)[1])
            self.campaigns.pop(cid, None)
            self.deleted.append(cid)
            return httpx.Response(200, json={})
        if method == "POST" and path == "/streams":
            if self.fail_second_stream and body["schema"] == "landings":
                return httpx.Response(422, json={"error": "boom"})
            sid = self._id()
            self.streams[sid] = {**body, "id": sid, "offers": body.get("offers", []), "filters": body.get("filters", [])}
            return httpx.Response(200, json=self.streams[sid])
        if method == "GET" and path.endswith("/streams"):
            cid = int(path.split("/")[2])
            return httpx.Response(200, json=[s for s in self.streams.values() if s["campaign_id"] == cid])
        if method == "PUT" and path.startswith("/streams/"):
            sid = int(path.rsplit("/", 1)[1])
            self.streams[sid].update(body)
            return httpx.Response(200, json=self.streams[sid])
        return httpx.Response(500, text=f"unexpected {method} {path}")

    def client(self) -> KeitaroClient:
        return KeitaroClient("http://kt", "key", transport=httpx.MockTransport(self.handle))


def make(**kw):
    defaults = dict(name="c1", geo="jp", offer_id=10, domain_id=1, group_id=2, traffic_source_id=3)
    defaults.update(kw)
    return defaults


@pytest.mark.parametrize("n", range(1, 12))
def test_shares_sum_to_100(n):
    shares = service.distribute_shares(n)
    assert len(shares) == n and sum(shares) == 100
    assert max(shares) - min(shares) <= 1


def test_shares_empty():
    assert service.distribute_shares(0) == []


def test_create_campaign_builds_two_streams():
    fake = FakeKeitaro()
    res = service.create_campaign(fake.client(), **make())
    camp = res["campaign"]
    assert camp["name"].startswith(service.settings.campaign_prefix)
    assert (camp["domain_id"], camp["group_id"], camp["traffic_source_id"]) == (1, 2, 3)
    s1, s2 = res["streams"]
    assert s1["schema"] == "redirect" and s1["action_payload"] == "https://google.com"
    assert s1["filters"] == [{"name": "country", "mode": "accept", "payload": ["JP"]}]
    assert s2["schema"] == "landings"
    assert s2["offers"] == [{"offer_id": 10, "share": 100, "state": "active"}]


def test_create_campaign_rolls_back_on_stream_error():
    fake = FakeKeitaro(fail_second_stream=True)
    with pytest.raises(Exception):
        service.create_campaign(fake.client(), **make())
    assert fake.campaigns == {} and len(fake.deleted) == 1


@pytest.mark.parametrize("bad", [dict(geo="JPN"), dict(geo="1"), dict(name="  "), dict(offer_id=0)])
def test_create_campaign_validation(bad):
    fake = FakeKeitaro()
    with pytest.raises(service.ValidationError):
        service.create_campaign(fake.client(), **make(**bad))
    assert fake.campaigns == {}


def test_add_and_remove_offer_redistributes_shares():
    fake = FakeKeitaro()
    kt = fake.client()
    res = service.create_campaign(kt, **make())
    cid, sid = res["campaign"]["id"], res["streams"][1]["id"]

    service.add_offer(kt, cid, sid, 11)
    service.add_offer(kt, cid, sid, 12)
    shares = [o["share"] for o in fake.streams[sid]["offers"]]
    assert shares == [34, 33, 33] and sum(shares) == 100

    service.remove_offer(kt, cid, sid, 10)
    offers = fake.streams[sid]["offers"]
    assert [o["offer_id"] for o in offers] == [11, 12]
    assert [o["share"] for o in offers] == [50, 50]

    service.remove_offer(kt, cid, sid, 11)
    assert fake.streams[sid]["offers"] == [{"offer_id": 12, "share": 100, "state": "active"}]


def test_offer_edit_errors():
    fake = FakeKeitaro()
    kt = fake.client()
    res = service.create_campaign(kt, **make())
    cid = res["campaign"]["id"]
    redirect_id, offers_id = res["streams"][0]["id"], res["streams"][1]["id"]
    with pytest.raises(service.ValidationError):
        service.add_offer(kt, cid, offers_id, 10)  # дубль
    with pytest.raises(service.ValidationError):
        service.add_offer(kt, cid, redirect_id, 11)  # поток-редирект
    with pytest.raises(service.ValidationError):
        service.remove_offer(kt, cid, offers_id, 12)  # нет в потоке
