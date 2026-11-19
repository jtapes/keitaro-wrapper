import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    keitaro_url: str = os.getenv("KEITARO_URL", "https://tlgk.host").rstrip("/")
    keitaro_api_key: str = os.getenv("KEITARO_API_KEY", "")
    default_domain_id: int = int(os.getenv("DEFAULT_DOMAIN_ID", "0") or 0)
    default_group_id: int = int(os.getenv("DEFAULT_GROUP_ID", "0") or 0)
    default_traffic_source_id: int = int(os.getenv("DEFAULT_TRAFFIC_SOURCE_ID", "0") or 0)
    campaign_prefix: str = os.getenv("CAMPAIGN_PREFIX", "test_gorbachev_")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./wrapper.db")


settings = Settings()
