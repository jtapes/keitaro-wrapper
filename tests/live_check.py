"""Живая проверка редактора против реального Keitaro (нужны .env и запущенный сервер).

Запуск: python tests/live_check.py <campaign_id> <stream_id>
Работает только с переданной кампанией: добавляет и удаляет офферы, проверяет сумму долей.
"""
import json
import sys
import urllib.request

BASE = "http://localhost:8000"


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def shares(view, sid):
    s = next(s for s in view["streams"] if s["id"] == sid)
    return [(o["offer_id"], o["share"]) for o in s["offers"]], s["share_total"]


cid, sid = int(sys.argv[1]), int(sys.argv[2])
base = f"/api/campaigns/{cid}/streams/{sid}/offers"
for method, path, body in [
    ("POST", base, {"offer_id": 24}),
    ("POST", base, {"offer_id": 23232}),
    ("POST", base, {"offer_id": 24}),          # дубль -> 422
    ("DELETE", base + "/18813", None),
    ("DELETE", base + "/999", None),           # нет в потоке -> 422
]:
    code, data = call(method, path, body)
    print(method, path.split("offers")[1] or "", body or "", "->", code,
          shares(data, sid) if code == 200 else data)
