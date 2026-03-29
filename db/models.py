"""
db/models.py — Modele bazy danych (SQLAlchemy 2.0 style)
SQLite na prototyp, PostgreSQL na produkcję — zero zmian w kodzie.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Integer, DateTime, Text, Boolean, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Game(Base):
    """
    Dane o grze pobrane z SteamSpy + Steam Store API.
    Odświeżane co 6h przez scraper.
    """
    __tablename__ = "games"

    id: Mapped[int]             = mapped_column(Integer, primary_key=True)
    app_id: Mapped[int]         = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str]           = mapped_column(String(255), index=True)
    developer: Mapped[str]      = mapped_column(String(255), default="")
    publisher: Mapped[str]      = mapped_column(String(255), default="")

    # Dane sprzedażowe (SteamSpy — szacunki)
    owners_min: Mapped[int]     = mapped_column(Integer, default=0)
    owners_max: Mapped[int]     = mapped_column(Integer, default=0)
    players_forever: Mapped[int]= mapped_column(Integer, default=0)
    average_playtime: Mapped[int]= mapped_column(Integer, default=0)  # minuty
    median_playtime: Mapped[int] = mapped_column(Integer, default=0)

    # Cena
    price_usd: Mapped[float]    = mapped_column(Float, default=0.0)
    discount_pct: Mapped[int]   = mapped_column(Integer, default=0)

    # Recenzje
    positive: Mapped[int]       = mapped_column(Integer, default=0)
    negative: Mapped[int]       = mapped_column(Integer, default=0)

    # Gatunki i tagi (JSON list)
    genres: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    tags: Mapped[Optional[dict]]   = mapped_column(JSON, default=dict)  # tag: votes

    # Daty
    release_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime]             = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime]             = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def owners_mid(self) -> int:
        return (self.owners_min + self.owners_max) // 2

    @property
    def estimated_revenue(self) -> float:
        """Szybki szacunek przychodu: owners_mid × price × 0.3 (Steam cut)."""
        return self.owners_mid * self.price_usd * 0.7

    @property
    def review_score(self) -> float:
        total = self.positive + self.negative
        return (self.positive / total * 100) if total > 0 else 0.0

    def __repr__(self) -> str:
        return f"<Game {self.app_id}: {self.name}>"


class GenreTrend(Base):
    """
    Agregat trendów per gatunek, zapisywany co 24h.
    Na tym budujemy wykresy i prognozy.
    """
    __tablename__ = "genre_trends"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True)
    genre: Mapped[str]           = mapped_column(String(100), index=True)
    recorded_at: Mapped[datetime]= mapped_column(DateTime, default=datetime.utcnow, index=True)

    # Metryki
    game_count: Mapped[int]      = mapped_column(Integer, default=0)
    avg_owners: Mapped[int]      = mapped_column(Integer, default=0)
    avg_revenue: Mapped[float]   = mapped_column(Float, default=0.0)
    avg_review_score: Mapped[float] = mapped_column(Float, default=0.0)
    avg_playtime_h: Mapped[float]= mapped_column(Float, default=0.0)
    avg_price: Mapped[float]     = mapped_column(Float, default=0.0)
    total_owners: Mapped[int]    = mapped_column(Integer, default=0)

    # Twitch (jeśli klucze dostępne)
    twitch_viewers: Mapped[int]  = mapped_column(Integer, default=0)

    def __repr__(self) -> str:
        return f"<GenreTrend {self.genre} @ {self.recorded_at.date()}>"


class AIReport(Base):
    """
    Cache wygenerowanych raportów AI — nie płacimy za ten sam prompt 2x.
    """
    __tablename__ = "ai_reports"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True)
    report_type: Mapped[str]     = mapped_column(String(50), index=True)  # weekly, genre, trend
    prompt_hash: Mapped[str]     = mapped_column(String(64), unique=True)  # sha256 promptu
    content: Mapped[str]         = mapped_column(Text)
    model_used: Mapped[str]      = mapped_column(String(100))
    tokens_used: Mapped[int]     = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class ScrapeLog(Base):
    """
    Logi scrapeów — wiemy co zostało pobrane i kiedy.
    """
    __tablename__ = "scrape_logs"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True)
    source: Mapped[str]          = mapped_column(String(50))   # steamspy, igdb, twitch
    status: Mapped[str]          = mapped_column(String(20))   # success, error, partial
    records_fetched: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_s: Mapped[float]    = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
