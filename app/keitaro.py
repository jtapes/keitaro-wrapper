"""Тонкий клиент Keitaro Admin API."""
from __future__ import annotations

from typing import Any

import httpx

from .config import settings


class KeitaroError(Exception):
    def __init__(self, status: int, detail: Any):
        super().__init__(f"Keitaro {status}: {detail}")
        self.status = status
        self.detail = detail


class KeitaroClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(
            base_url=(base_url or settings.keitaro_url) + "/admin_api/v1",
            headers={"Api-Key": api_key or settings.keitaro_api_key},
            timeout=30,
            transport=transport,
        )

    def _request(self, method: str, path: str, **kwargs) -> Any:
        try:
            resp = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:  # сеть, таймаут
            raise KeitaroError(502, f"Keitaro недоступен: {exc}") from exc
        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except ValueError:
                detail = resp.text[:200]
            raise KeitaroError(resp.status_code, detail)
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            raise KeitaroError(502, "Keitaro вернул не JSON")

    # справочники
    def domains(self) -> list[dict]:
        return self._request("GET", "/domains")

    def groups(self) -> list[dict]:
        return self._request("GET", "/groups", params={"type": "campaigns"})

    def traffic_sources(self) -> list[dict]:
        return self._request("GET", "/traffic_sources")

    def offers(self) -> list[dict]:
        return self._request("GET", "/offers")

    def offer(self, offer_id: int) -> dict:
        return self._request("GET", f"/offers/{offer_id}")

    # кампании
    def campaigns(self) -> list[dict]:
        return self._request("GET", "/campaigns")

    def campaign(self, campaign_id: int) -> dict:
        return self._request("GET", f"/campaigns/{campaign_id}")

    def create_campaign(self, payload: dict) -> dict:
        return self._request("POST", "/campaigns", json=payload)

    def delete_campaign(self, campaign_id: int) -> None:
        self._request("DELETE", f"/campaigns/{campaign_id}")

    # потоки
    def streams(self, campaign_id: int) -> list[dict]:
        return self._request("GET", f"/campaigns/{campaign_id}/streams")

    def create_stream(self, payload: dict) -> dict:
        return self._request("POST", "/streams", json=payload)

    def update_stream(self, stream_id: int, payload: dict) -> dict:
        return self._request("PUT", f"/streams/{stream_id}", json=payload)

    # статистика
    def report(self, campaign_id: int, grouping: list[str]) -> list[dict]:
        body = {
            "range": {"interval": "all_time", "timezone": "Europe/Moscow"},
            "metrics": ["clicks", "campaign_unique_clicks", "conversions", "revenue", "cost", "profit"],
            "grouping": grouping,
            "filters": [{"name": "campaign_id", "operator": "EQUALS", "expression": campaign_id}],
        }
        return self._request("POST", "/report/build", json=body).get("rows", [])
