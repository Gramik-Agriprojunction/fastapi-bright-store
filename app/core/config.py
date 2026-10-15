from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Bright Store API"
    app_env: str = "uat"
    debug: bool = False
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/bright_store"
    ai_provider: str = "none"
    ai_api_key: str | None = None
    ai_model: str | None = None
    odoo_crm_api_key: str = ""
    odoo_json2_url: str = ""
    odoo_crm_base_url: str = ""
    ses_smtp_host: str = ""
    ses_smtp_port: int = 587
    ses_smtp_user: str = ""
    ses_smtp_pass: str = ""
    ses_from_email: str = "noreply@gramik.in"
    ses_from_name: str = "WebTechAgent AI Assistant"
    reconciliation_workbook: str = (
        "/Users/sourabhyadav/Documents/Project/Gramik-Live/data_reconciliation/"
        "Lavkush_BL-D_Musturd_1666_1445_reconciliation.xlsx"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
