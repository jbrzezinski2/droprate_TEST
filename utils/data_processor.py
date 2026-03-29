"""
utils/data_processor.py — Przetwarzanie surowych danych do DataFrames.

Każda funkcja zwraca pd.DataFrame gotowy do przekazania do Plotly.
To jest "warstwa transformacji" między bazą danych a wykresami.
"""
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import func, text

from db.database import get_session
from db.models import Game, GenreTrend


# ── Dane z bazy → DataFrame ───────────────────────────────────────────────────

def get_games_df() -> pd.DataFrame:
    """Wszystkie gry z bazy jako DataFrame."""
    with get_session() as db:
        games = db.query(Game).all()

    if not games:
        return pd.DataFrame()

    return pd.DataFrame([{
        "app_id": g.app_id,
        "name": g.name,
        "developer": g.developer,
        "genre": (g.tags or {}).get("primary_genre", "Unknown"),
        "owners_mid": g.owners_mid,
        "owners_min": g.owners_min,
        "owners_max": g.owners_max,
        "price_usd": g.price_usd,
        "positive": g.positive,
        "negative": g.negative,
        "review_score": g.review_score,
        "average_playtime_h": g.average_playtime / 60,
        "estimated_revenue": g.estimated_revenue,
        "release_date": g.release_date,
    } for g in games])


def get_genre_stats_df() -> pd.DataFrame:
    """
    Agregat statystyk per gatunek.
    Używane do głównych wykresów porównawczych.
    """
    with get_session() as db:
        # Grupujemy gry po tagu "genre" (przechowywany w JSON tags)
        games = db.query(Game).filter(Game.owners_max > 0).all()

    if not games:
        return _fallback_genre_df()  # dane demonstracyjne gdy baza pusta

    # Buduj DF z gier
    rows = []
    for g in games:
        tags = g.tags or {}
        # Pobierz pierwszy tag jako gatunek (SteamSpy sortuje tagi wg głosów)
        genre = list(tags.keys())[0] if tags else "Other"
        rows.append({
            "genre": genre,
            "owners_mid": g.owners_mid,
            "revenue": g.estimated_revenue,
            "review_score": g.review_score,
            "playtime_h": g.average_playtime / 60,
            "price": g.price_usd,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return _fallback_genre_df()

    # Agregat
    agg = df.groupby("genre").agg(
        game_count=("owners_mid", "count"),
        avg_owners=("owners_mid", "mean"),
        avg_revenue=("revenue", "mean"),
        total_revenue=("revenue", "sum"),
        avg_review=("review_score", "mean"),
        avg_playtime_h=("playtime_h", "mean"),
        avg_price=("price", "mean"),
    ).reset_index()

    # ROI Score (composite) — znormalizowany 0–100
    agg["roi_score"] = (
        agg["avg_revenue"].rank(pct=True) * 0.4 +
        agg["avg_review"].rank(pct=True) * 0.3 +
        agg["game_count"].rank(pct=True) * 0.15 +
        (1 - agg["avg_playtime_h"].rank(pct=True)) * 0.15  # krótszy dev = lepiej
    ) * 100

    return agg.sort_values("roi_score", ascending=False)


def get_trend_history_df(genre: str | None = None, days: int = 30) -> pd.DataFrame:
    """
    Historia trendów z tabeli genre_trends.
    Jeśli genre=None → wszystkie gatunki.
    """
    with get_session() as db:
        query = db.query(GenreTrend).filter(
            GenreTrend.recorded_at >= datetime.utcnow() - timedelta(days=days)
        )
        if genre:
            query = query.filter(GenreTrend.genre == genre)
        trends = query.order_by(GenreTrend.recorded_at).all()

    if not trends:
        return _fallback_trend_df()

    return pd.DataFrame([{
        "genre": t.genre,
        "recorded_at": t.recorded_at,
        "avg_owners": t.avg_owners,
        "avg_revenue": t.avg_revenue,
        "avg_review": t.avg_review_score,
        "game_count": t.game_count,
        "twitch_viewers": t.twitch_viewers,
    } for t in trends])


def get_top_games_df(genre: str | None = None, limit: int = 20) -> pd.DataFrame:
    """Top gry wg szacowanego przychodu."""
    with get_session() as db:
        query = db.query(Game).filter(Game.owners_max > 0)
        if genre:
            # filtrowanie po JSON tag — uproszczone
            query = query.filter(
                text(f"json_extract(tags, '$.\"{genre}\"') IS NOT NULL")
            )
        games = (
            query
            .order_by((Game.owners_min + Game.owners_max).desc())
            .limit(limit)
            .all()
        )

    if not games:
        return pd.DataFrame()

    return pd.DataFrame([{
        "name": g.name,
        "app_id": g.app_id,
        "owners_mid": g.owners_mid,
        "price_usd": g.price_usd,
        "review_score": g.review_score,
        "estimated_revenue": g.estimated_revenue,
        "playtime_h": g.average_playtime / 60,
        "release_date": g.release_date,
    } for g in games])


def get_market_context() -> dict:
    """
    Agregat danych do wstrzyknięcia w kontekst Claude.
    Lekki — używamy go przy każdym zapytaniu AI.
    """
    with get_session() as db:
        total_games = db.query(func.count(Game.id)).scalar() or 0

        # Ostatnia aktualizacja
        last_game = db.query(Game).order_by(Game.updated_at.desc()).first()
        last_updated = last_game.updated_at.strftime("%d.%m.%Y %H:%M") if last_game else "brak danych"

    genre_df = get_genre_stats_df()
    top_genres = {}
    if not genre_df.empty:
        for _, row in genre_df.head(8).iterrows():
            top_genres[row["genre"]] = {
                "avg_owners": int(row["avg_owners"]),
                "avg_revenue": float(row["avg_revenue"]),
                "avg_review": float(row["avg_review"]),
                "count": int(row["game_count"]),
                "roi_score": float(row["roi_score"]),
            }

    return {
        "total_games": total_games,
        "last_updated": last_updated,
        "top_genres": top_genres,
    }


# ── Fallback Data (gdy baza pusta — demo mode) ────────────────────────────────
def _fallback_genre_df() -> pd.DataFrame:
    """Dane demonstracyjne gdy baza jest pusta (przed pierwszym scrapem)."""
    return pd.DataFrame([
        {"genre": "Roguelite",    "game_count": 420, "avg_owners": 45000, "avg_revenue": 52000, "avg_review": 84, "avg_playtime_h": 18, "avg_price": 14.99, "roi_score": 91},
        {"genre": "Cozy",         "game_count": 280, "avg_owners": 38000, "avg_revenue": 68000, "avg_review": 87, "avg_playtime_h": 22, "avg_price": 11.99, "roi_score": 88},
        {"genre": "Survival",     "game_count": 510, "avg_owners": 62000, "avg_revenue": 91000, "avg_review": 76, "avg_playtime_h": 45, "avg_price": 19.99, "roi_score": 82},
        {"genre": "Horror",       "game_count": 190, "avg_owners": 22000, "avg_revenue": 28000, "avg_review": 79, "avg_playtime_h": 6,  "avg_price": 7.99,  "roi_score": 79},
        {"genre": "Idle",         "game_count": 340, "avg_owners": 18000, "avg_revenue": 12000, "avg_review": 72, "avg_playtime_h": 60, "avg_price": 4.99,  "roi_score": 71},
        {"genre": "Puzzle",       "game_count": 620, "avg_owners": 15000, "avg_revenue": 9000,  "avg_review": 81, "avg_playtime_h": 8,  "avg_price": 6.99,  "roi_score": 68},
        {"genre": "Visual Novel", "game_count": 150, "avg_owners": 12000, "avg_revenue": 14000, "avg_review": 78, "avg_playtime_h": 10, "avg_price": 8.99,  "roi_score": 65},
        {"genre": "Platformer",   "game_count": 780, "avg_owners": 11000, "avg_revenue": 7000,  "avg_review": 74, "avg_playtime_h": 12, "avg_price": 9.99,  "roi_score": 55},
    ])


def _fallback_trend_df() -> pd.DataFrame:
    """Symulowane dane trendów historycznych (demo mode)."""
    import numpy as np
    dates = pd.date_range(end=datetime.utcnow(), periods=30, freq="D")
    genres = ["Roguelite", "Cozy", "Survival", "Horror"]
    base = {"Roguelite": 45000, "Cozy": 38000, "Survival": 62000, "Horror": 22000}
    growth = {"Roguelite": 1.008, "Cozy": 1.010, "Survival": 1.015, "Horror": 1.012}

    rows = []
    for g in genres:
        for i, d in enumerate(dates):
            rows.append({
                "genre": g,
                "recorded_at": d,
                "avg_owners": int(base[g] * (growth[g] ** i) + np.random.randint(-1000, 1000)),
                "avg_revenue": base[g] * growth[g] ** i * 1.2,
                "avg_review": 80 + np.random.uniform(-3, 3),
                "game_count": 100 + i,
                "twitch_viewers": np.random.randint(5000, 50000),
            })
    return pd.DataFrame(rows)
