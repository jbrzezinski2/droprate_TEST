"""
db/database.py — Engine, sesja i inicjalizacja bazy danych.
Używaj get_session() jako context manager wszędzie.
"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from rich.console import Console

from config import settings
from db.models import Base

console = Console()

# ── Engine ──────────────────────────────────────────────────────────────────
engine = create_engine(
    settings.database_url,
    # SQLite: wyłącz check_same_thread (Streamlit używa wielu wątków)
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    echo=False,  # True = loguj każde SQL zapytanie (debug)
)

# WAL mode dla SQLite — lepsza współbieżność
if "sqlite" in settings.database_url:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# ── Session Factory ──────────────────────────────────────────────────────────
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # ważne dla Streamlit — obiekty żyją poza sesją
)


# ── Context Manager ──────────────────────────────────────────────────────────
@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Użycie:
        with get_session() as db:
            games = db.query(Game).all()
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ── Inicjalizacja ────────────────────────────────────────────────────────────
def init_db() -> None:
    """
    Tworzy wszystkie tabele jeśli nie istnieją.
    Bezpieczne do wywołania wielokrotnie.
    """
    Base.metadata.create_all(bind=engine)
    console.print("[green]✓[/green] Baza danych zainicjalizowana")


def get_db_stats() -> dict:
    """Zwraca podstawowe statystyki bazy — przydatne w UI."""
    with get_session() as db:
        return {
            "games": db.execute(text("SELECT COUNT(*) FROM games")).scalar() or 0,
            "genre_trends": db.execute(text("SELECT COUNT(*) FROM genre_trends")).scalar() or 0,
            "ai_reports": db.execute(text("SELECT COUNT(*) FROM ai_reports")).scalar() or 0,
        }
