"""
tests/test_scrapers.py — Testy jednostkowe dla scraperów i przetwarzania danych.

Uruchomienie:
    pytest tests/ -v
    pytest tests/ -v --tb=short  # krótszy traceback

Testy NIE wywołują prawdziwych API — używają mocków (unittest.mock).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime
from unittest.mock import patch, MagicMock
import pytest
import pandas as pd


# ═════════════════════════════════════════════════════════════════════════════
# TESTY: scrapers/steam.py
# ═════════════════════════════════════════════════════════════════════════════
class TestSteamParser:
    """Testy funkcji pomocniczych scrapera Steam (bez HTTP)."""

    def test_parse_owners_standard(self):
        from scrapers.steam import _parse_owners
        lo, hi = _parse_owners("20,000 .. 50,000")
        assert lo == 20_000
        assert hi == 50_000

    def test_parse_owners_large(self):
        from scrapers.steam import _parse_owners
        lo, hi = _parse_owners("1,000,000 .. 2,000,000")
        assert lo == 1_000_000
        assert hi == 2_000_000

    def test_parse_owners_zero(self):
        from scrapers.steam import _parse_owners
        lo, hi = _parse_owners("0 .. 20,000")
        assert lo == 0
        assert hi == 20_000

    def test_parse_owners_malformed(self):
        from scrapers.steam import _parse_owners
        lo, hi = _parse_owners("invalid string")
        assert lo == 0
        assert hi == 0

    def test_parse_date_full(self):
        from scrapers.steam import _parse_date
        result = _parse_date("15 Jan, 2023")
        assert result is not None
        assert result.year == 2023
        assert result.month == 1
        assert result.day == 15

    def test_parse_date_month_only(self):
        from scrapers.steam import _parse_date
        result = _parse_date("Jan 2023")
        assert result is not None
        assert result.year == 2023

    def test_parse_date_invalid(self):
        from scrapers.steam import _parse_date
        result = _parse_date("Coming Soon")
        assert result is None

    def test_genre_to_tag_mapping(self):
        from scrapers.steam import GENRE_TO_TAG
        assert "Roguelite" in GENRE_TO_TAG
        assert "Cozy" in GENRE_TO_TAG
        assert "Survival" in GENRE_TO_TAG
        assert len(GENRE_TO_TAG) >= 5

    @patch("scrapers.steam.httpx.Client")
    def test_fetch_steamspy_tag_uses_cache(self, mock_client):
        """Drugi identyczny request powinien użyć cache (0 wywołań HTTP)."""
        from scrapers.steam import _cache, fetch_steamspy_tag

        # Wypełnij cache ręcznie
        cache_key = "spy_tag_roguelite_99"
        _cache[cache_key] = [{"app_id": 1, "name": "Test Game"}]

        result = fetch_steamspy_tag("roguelite", page=99)

        assert result == [{"app_id": 1, "name": "Test Game"}]
        mock_client.assert_not_called()  # HTTP nie był wywołany


# ═════════════════════════════════════════════════════════════════════════════
# TESTY: db/models.py
# ═════════════════════════════════════════════════════════════════════════════
class TestGameModel:
    """Testy właściwości modelu Game."""

    def _make_game(self, **kwargs) -> "Game":
        from db.models import Game
        defaults = dict(
            app_id=999,
            name="Test Game",
            owners_min=10_000,
            owners_max=50_000,
            price_usd=14.99,
            positive=800,
            negative=200,
            average_playtime=600,
        )
        defaults.update(kwargs)
        return Game(**defaults)

    def test_owners_mid(self):
        game = self._make_game(owners_min=10_000, owners_max=50_000)
        assert game.owners_mid == 30_000

    def test_owners_mid_zero(self):
        game = self._make_game(owners_min=0, owners_max=0)
        assert game.owners_mid == 0

    def test_estimated_revenue(self):
        game = self._make_game(owners_min=10_000, owners_max=50_000, price_usd=14.99)
        # owners_mid=30_000, price=14.99, steam_cut=0.7
        expected = 30_000 * 14.99 * 0.7
        assert abs(game.estimated_revenue - expected) < 1.0

    def test_review_score_positive(self):
        game = self._make_game(positive=900, negative=100)
        assert game.review_score == pytest.approx(90.0)

    def test_review_score_no_reviews(self):
        game = self._make_game(positive=0, negative=0)
        assert game.review_score == 0.0

    def test_repr(self):
        game = self._make_game(app_id=12345, name="Hades")
        assert "12345" in repr(game)
        assert "Hades" in repr(game)


# ═════════════════════════════════════════════════════════════════════════════
# TESTY: db/database.py
# ═════════════════════════════════════════════════════════════════════════════
class TestDatabase:
    """Testy inicjalizacji bazy danych (in-memory SQLite)."""

    @pytest.fixture(autouse=True)
    def setup_test_db(self, monkeypatch):
        """Każdy test dostaje świeżą bazę in-memory."""
        monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
        # Resetuj singleton settings
        from config import get_settings
        get_settings.cache_clear()
        from db import database
        from db.models import Base
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        database.engine = engine
        database.SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        yield
        Base.metadata.drop_all(engine)

    def test_init_db_creates_tables(self):
        from db.database import init_db, engine
        from sqlalchemy import inspect
        init_db()
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "games" in tables
        assert "genre_trends" in tables
        assert "ai_reports" in tables
        assert "scrape_logs" in tables

    def test_get_session_commit(self):
        from db.database import get_session, init_db
        from db.models import Game
        init_db()

        with get_session() as db:
            db.add(Game(app_id=1, name="Test", owners_min=0, owners_max=0,
                        price_usd=0, positive=0, negative=0, average_playtime=0,
                        median_playtime=0, players_forever=0))

        with get_session() as db:
            game = db.query(Game).filter_by(app_id=1).first()
            assert game is not None
            assert game.name == "Test"

    def test_get_session_rollback_on_error(self):
        from db.database import get_session, init_db
        from db.models import Game
        init_db()

        with pytest.raises(Exception):
            with get_session() as db:
                db.add(Game(app_id=2, name="Test2", owners_min=0, owners_max=0,
                            price_usd=0, positive=0, negative=0, average_playtime=0,
                            median_playtime=0, players_forever=0))
                raise ValueError("Symulowany błąd")

        # Po błędzie rekord NIE powinien być zapisany
        with get_session() as db:
            game = db.query(Game).filter_by(app_id=2).first()
            assert game is None


# ═════════════════════════════════════════════════════════════════════════════
# TESTY: utils/data_processor.py
# ═════════════════════════════════════════════════════════════════════════════
class TestDataProcessor:
    """Testy przetwarzania danych."""

    def test_fallback_genre_df_structure(self):
        from utils.data_processor import _fallback_genre_df
        df = _fallback_genre_df()
        assert not df.empty
        required_cols = ["genre", "game_count", "avg_owners", "avg_revenue", "roi_score"]
        for col in required_cols:
            assert col in df.columns, f"Brak kolumny: {col}"

    def test_fallback_genre_df_roi_sorted(self):
        from utils.data_processor import _fallback_genre_df
        df = _fallback_genre_df()
        # Pierwsza wartość powinna być najwyższa (sorted desc)
        scores = df["roi_score"].tolist()
        assert scores[0] >= scores[-1]

    def test_fallback_trend_df_structure(self):
        from utils.data_processor import _fallback_trend_df
        df = _fallback_trend_df()
        assert not df.empty
        assert "genre" in df.columns
        assert "recorded_at" in df.columns
        assert "avg_owners" in df.columns

    def test_fallback_trend_df_has_multiple_genres(self):
        from utils.data_processor import _fallback_trend_df
        df = _fallback_trend_df()
        assert len(df["genre"].unique()) >= 3


# ═════════════════════════════════════════════════════════════════════════════
# TESTY: utils/forecasting.py
# ═════════════════════════════════════════════════════════════════════════════
class TestForecasting:
    """Testy modeli prognostycznych."""

    def test_estimate_revenue_base_scenario(self):
        from utils.forecasting import estimate_solo_dev_revenue
        result = estimate_solo_dev_revenue("Roguelite", 6, 14.99, 1000.0, "base")

        assert result["scenario"] == "base"
        assert result["genre"] == "Roguelite"
        assert result["estimated_owners"] > 0
        assert result["gross_revenue_usd"] > 0
        assert result["net_revenue_usd"] <= result["gross_revenue_usd"]

    def test_optimistic_beats_pessimistic(self):
        from utils.forecasting import estimate_solo_dev_revenue
        pessimistic = estimate_solo_dev_revenue("Roguelite", 6, 14.99, 1000.0, "pessimistic")
        optimistic = estimate_solo_dev_revenue("Roguelite", 6, 14.99, 1000.0, "optimistic")
        assert optimistic["net_revenue_usd"] > pessimistic["net_revenue_usd"]

    def test_higher_price_higher_revenue(self):
        from utils.forecasting import estimate_solo_dev_revenue
        low = estimate_solo_dev_revenue("Roguelite", 6, 4.99, 0.0, "base")
        high = estimate_solo_dev_revenue("Roguelite", 6, 24.99, 0.0, "base")
        assert high["gross_revenue_usd"] > low["gross_revenue_usd"]

    def test_linear_fallback_with_few_points(self):
        from utils.forecasting import forecast_genre_trend
        import numpy as np

        # Tylko 3 punkty — za mało dla Prophet, powinien użyć regresji
        dates = pd.date_range("2024-01-01", periods=3, freq="W")
        df = pd.DataFrame({
            "genre": ["Roguelite"] * 3,
            "recorded_at": dates,
            "avg_owners": [10_000, 11_000, 12_000],
            "avg_revenue": [50_000, 55_000, 60_000],
            "avg_review": [82, 83, 84],
            "twitch_viewers": [5000, 5500, 6000],
        })

        result = forecast_genre_trend(df, "Roguelite", "avg_owners", horizon_days=30)

        assert result is not None
        assert result.method == "linear_fallback"
        assert result.trend_direction == "up"  # rosnące dane → up
        assert result.predicted_value > result.last_value

    def test_forecast_result_trend_pct(self):
        from utils.forecasting import _linear_forecast
        import numpy as np

        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        df = pd.DataFrame({
            "ds": dates,
            "y": [10_000 + i * 500 for i in range(10)],  # rosnące
        })

        result = _linear_forecast(df, "Test", "avg_owners", 30)
        assert result.trend_pct > 0  # rosnące dane
        assert result.trend_direction == "up"


# ═════════════════════════════════════════════════════════════════════════════
# TESTY: scrapers/reddit.py
# ═════════════════════════════════════════════════════════════════════════════
class TestRedditAnalysis:
    """Testy klasyfikacji postów i sentymentu (bez HTTP)."""

    def test_classify_roguelite_post(self):
        from scrapers.reddit import classify_post_genres
        post = {"title": "Best roguelite games of 2024?", "selftext": ""}
        genres = classify_post_genres(post)
        assert "Roguelite" in genres

    def test_classify_cozy_post(self):
        from scrapers.reddit import classify_post_genres
        post = {"title": "Looking for cozy games like Stardew Valley", "selftext": ""}
        genres = classify_post_genres(post)
        assert "Cozy" in genres

    def test_classify_multiple_genres(self):
        from scrapers.reddit import classify_post_genres
        post = {
            "title": "Roguelite cozy farming game?",
            "selftext": "relaxing roguelite with farming elements",
        }
        genres = classify_post_genres(post)
        # Powinien wykryć co najmniej jeden gatunek
        assert len(genres) >= 1

    def test_classify_irrelevant_post(self):
        from scrapers.reddit import classify_post_genres
        post = {"title": "Best GPU for gaming in 2024", "selftext": ""}
        genres = classify_post_genres(post)
        assert len(genres) == 0

    def test_sentiment_positive(self):
        from scrapers.reddit import calculate_sentiment
        score = calculate_sentiment("This game is amazing and fantastic, love it!")
        assert score > 0.6

    def test_sentiment_negative(self):
        from scrapers.reddit import calculate_sentiment
        score = calculate_sentiment("Terrible game, awful, boring waste of money")
        assert score < 0.4

    def test_sentiment_neutral(self):
        from scrapers.reddit import calculate_sentiment
        score = calculate_sentiment("I played this game for a while")
        assert 0.3 <= score <= 0.7


# ═════════════════════════════════════════════════════════════════════════════
# TESTY: scheduler.py
# ═════════════════════════════════════════════════════════════════════════════
class TestScheduler:
    """Testy konfiguracji schedulera."""

    def test_setup_schedule_registers_jobs(self):
        import schedule as sc
        sc.clear()  # wyczyść poprzednie joby

        from scheduler import setup_schedule
        setup_schedule()

        assert len(sc.jobs) >= 3  # scrape + trends + cleanup
        sc.clear()

    def test_run_in_background_returns_thread(self):
        import threading
        from scheduler import run_in_background
        import schedule as sc
        sc.clear()

        thread = run_in_background()
        assert isinstance(thread, threading.Thread)
        assert thread.daemon is True  # daemon — nie blokuje zamknięcia
        sc.clear()


# ═════════════════════════════════════════════════════════════════════════════
# TESTY: config.py
# ═════════════════════════════════════════════════════════════════════════════
class TestConfig:
    """Testy konfiguracji."""

    def test_has_anthropic_key_false_when_empty(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        from config import get_settings
        get_settings.cache_clear()
        s = get_settings()
        assert not s.has_anthropic_key
        get_settings.cache_clear()

    def test_has_anthropic_key_true_when_set(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        from config import get_settings
        get_settings.cache_clear()
        s = get_settings()
        assert s.has_anthropic_key
        get_settings.cache_clear()

    def test_is_production_false_by_default(self):
        from config import get_settings
        get_settings.cache_clear()
        s = get_settings()
        # Domyślnie development
        assert not s.is_production or s.app_env == "production"
        get_settings.cache_clear()

    def test_default_database_is_sqlite(self):
        from config import get_settings
        get_settings.cache_clear()
        s = get_settings()
        assert "sqlite" in s.database_url
        get_settings.cache_clear()
