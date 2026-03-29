"""
config.py — Centralna konfiguracja GDIntel
Pydantic-settings automatycznie wczyta zmienne z .env
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── AI ──────────────────────────────────────────────────
    anthropic_api_key: str = ""

    # Modele Claude — haiku dla szybkich odpowiedzi, sonnet dla analiz
    claude_analyst_model: str = "claude-haiku-4-5"
    claude_report_model: str  = "claude-sonnet-4-5"
    claude_max_tokens: int    = 2048

    # ── Twitch / IGDB ───────────────────────────────────────
    twitch_client_id: str     = ""
    twitch_client_secret: str = ""

    # ── Reddit ──────────────────────────────────────────────
    reddit_client_id: str     = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str    = "GDIntel/1.0"

    # ── Baza danych ─────────────────────────────────────────
    database_url: str = "sqlite:///./gdintel.db"

    # ── Cache ────────────────────────────────────────────────
    cache_ttl_seconds: int       = 3600    # 1h
    steam_scrape_interval: int   = 21600   # 6h

    # ── Aplikacja ────────────────────────────────────────────
    app_env: str  = "development"
    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def has_anthropic_key(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def has_twitch_keys(self) -> bool:
        return bool(self.twitch_client_id and self.twitch_client_secret)


@lru_cache()
def get_settings() -> Settings:
    """Singleton — settings ładowane raz, potem z cache."""
    return Settings()


# Wygodny alias
settings = get_settings()
