from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CampaignLog(Base):
    """Журнал: что создали и менялось ли через обёртку (история действий)."""

    __tablename__ = "campaign_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keitaro_campaign_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(255))
    geo: Mapped[str] = mapped_column(String(2), default="")
    offer_id: Mapped[int] = mapped_column(Integer, default=0)
    action: Mapped[str] = mapped_column(String(32))  # created | offer_added | offer_removed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
