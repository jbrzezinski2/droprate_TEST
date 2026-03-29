"""
scheduler.py — Automatyczne odświeżanie danych w tle.

Uruchom równolegle z aplikacją Streamlit:
    python scheduler.py &
    streamlit run app.py

Lub użyj w jednym procesie przez Streamlit background thread.

Jobs:
  - co 6h:  scrape SteamSpy dla wszystkich gatunków
  - co 24h: oblicz i zapisz GenreTrend do bazy
  - co 24h: wyczyść stare cache AI raportów
  - co 1h:  Twitch viewership (jeśli klucze)
"""
import time
import threading
from datetime import datetime, timedelta

import schedule
from rich.console import Console
from rich.table import Table

from config import settings
from db.database import init_db, get_session
from db.models import Game, GenreTrend, ScrapeLog, AIReport
from scrapers.steam import fetch_genre_data, GENRE_TO_TAG
from scrapers.twitch import fetch_genre_viewership

console = Console()


# ── Job: Scrape Steam ──────────────────────────────────────────────────────
def job_scrape_steam() -> None:
    """Pobiera dane z SteamSpy dla wszystkich zdefiniowanych gatunków."""
    console.rule("[cyan]SCHEDULER: Steam scrape start[/cyan]")
    started = datetime.utcnow()
    total_saved = 0
    errors = []

    for genre, tag in GENRE_TO_TAG.items():
        try:
            games = fetch_genre_data(genre, pages=1)

            with get_session() as db:
                for g_data in games:
                    existing = db.query(Game).filter_by(app_id=g_data["app_id"]).first()

                    if existing:
                        # Update
                        for field, val in g_data.items():
                            if hasattr(existing, field):
                                setattr(existing, field, val)
                        existing.updated_at = datetime.utcnow()
                    else:
                        # Insert
                        db.add(Game(
                            app_id=g_data["app_id"],
                            name=g_data["name"],
                            developer=g_data.get("developer", ""),
                            publisher=g_data.get("publisher", ""),
                            owners_min=g_data.get("owners_min", 0),
                            owners_max=g_data.get("owners_max", 0),
                            players_forever=g_data.get("players_forever", 0),
                            average_playtime=g_data.get("average_playtime", 0),
                            median_playtime=g_data.get("median_playtime", 0),
                            price_usd=g_data.get("price_usd", 0.0),
                            positive=g_data.get("positive", 0),
                            negative=g_data.get("negative", 0),
                            tags=g_data.get("tags", {}),
                        ))

                    total_saved += 1

            console.print(f"  [green]✓[/green] {genre}: {len(games)} gier")

        except Exception as e:
            console.print(f"  [red]✗[/red] {genre}: {e}")
            errors.append(f"{genre}: {e}")

    duration = (datetime.utcnow() - started).total_seconds()

    # Zapisz log
    with get_session() as db:
        db.add(ScrapeLog(
            source="steamspy",
            status="success" if not errors else "partial",
            records_fetched=total_saved,
            error_message="; ".join(errors) if errors else None,
            duration_s=duration,
            started_at=started,
        ))

    console.print(
        f"[green]✓ Steam scrape zakończony:[/green] "
        f"{total_saved} rekordów w {duration:.1f}s"
    )


# ── Job: Compute Genre Trends ─────────────────────────────────────────────
def job_compute_genre_trends() -> None:
    """
    Agreguje dane gier do GenreTrend snapshot.
    Jeden rekord per gatunek per dzień.
    """
    console.rule("[cyan]SCHEDULER: Compute genre trends[/cyan]")
    now = datetime.utcnow()

    with get_session() as db:
        games = db.query(Game).filter(Game.owners_max > 0).all()

    if not games:
        console.print("[yellow]⚠ Brak gier w bazie — pomiń trend snapshot[/yellow]")
        return

    # Grupuj po gatunku (pierwszy tag)
    genre_buckets: dict[str, list[Game]] = {}
    for game in games:
        tags = game.tags or {}
        genre = list(tags.keys())[0] if tags else "Unknown"
        genre_buckets.setdefault(genre, []).append(game)

    # Oblicz i zapisz
    with get_session() as db:
        saved = 0
        for genre, genre_games in genre_buckets.items():
            if not genre_games:
                continue

            owners = [g.owners_mid for g in genre_games]
            revenues = [g.estimated_revenue for g in genre_games]
            reviews = [g.review_score for g in genre_games if g.positive + g.negative > 0]
            playtimes = [g.average_playtime / 60 for g in genre_games]

            # Twitch (opcjonalne)
            twitch_viewers = 0
            if settings.has_twitch_keys:
                try:
                    keywords = genre.lower().split()[:2]
                    twitch_viewers = fetch_genre_viewership(keywords)
                except Exception:
                    pass

            db.add(GenreTrend(
                genre=genre,
                recorded_at=now,
                game_count=len(genre_games),
                avg_owners=int(sum(owners) / len(owners)) if owners else 0,
                total_owners=sum(owners),
                avg_revenue=sum(revenues) / len(revenues) if revenues else 0.0,
                avg_review_score=sum(reviews) / len(reviews) if reviews else 0.0,
                avg_playtime_h=sum(playtimes) / len(playtimes) if playtimes else 0.0,
                avg_price=sum(g.price_usd for g in genre_games) / len(genre_games),
                twitch_viewers=twitch_viewers,
            ))
            saved += 1

    console.print(f"[green]✓ Genre trends zapisane:[/green] {saved} gatunków")


# ── Job: Clean old AI cache ───────────────────────────────────────────────
def job_clean_ai_cache() -> None:
    """Usuwa przeterminowane raporty AI z bazy."""
    with get_session() as db:
        deleted = (
            db.query(AIReport)
            .filter(AIReport.expires_at < datetime.utcnow())
            .delete()
        )
    if deleted:
        console.print(f"[dim]Wyczyszczono {deleted} przeterminowanych raportów AI[/dim]")


# ── Scheduler Setup ───────────────────────────────────────────────────────
def setup_schedule() -> None:
    """Rejestruje wszystkie joby."""

    # Steam: co 6h (domyślnie ustawione przez settings)
    interval_h = settings.steam_scrape_interval // 3600
    schedule.every(interval_h).hours.do(job_scrape_steam)
    console.print(f"  [cyan]→[/cyan] Steam scrape: co {interval_h}h")

    # Trendy: codziennie o 3:00 (po nocnym scrape)
    schedule.every().day.at("03:00").do(job_compute_genre_trends)
    console.print(f"  [cyan]→[/cyan] Genre trends: codziennie 03:00")

    # Czyszczenie cache: raz dziennie
    schedule.every().day.at("04:00").do(job_clean_ai_cache)
    console.print(f"  [cyan]→[/cyan] AI cache cleanup: codziennie 04:00")


def print_schedule_status() -> None:
    """Wyświetla aktualny harmonogram jobów."""
    table = Table(title="Harmonogram schedulera", style="cyan")
    table.add_column("Job", style="white")
    table.add_column("Następne uruchomienie", style="yellow")
    table.add_column("Interwał", style="green")

    for job in schedule.jobs:
        table.add_row(
            str(job.job_func.__name__),
            str(job.next_run),
            str(job.interval) + " " + str(job.unit),
        )
    console.print(table)


def run_scheduler(run_immediately: bool = True) -> None:
    """
    Główna pętla schedulera — blokuje wątek.
    
    Args:
        run_immediately: uruchom wszystkie joby natychmiast (dobre przy pierwszym starcie)
    """
    init_db()
    console.rule("[bold cyan]GDIntel Scheduler[/bold cyan]")
    console.print("[green]Konfigurowanie harmonogramu...[/green]")
    setup_schedule()

    if run_immediately:
        console.print("\n[yellow]Pierwsze uruchomienie — start natychmiastowy...[/yellow]")
        job_scrape_steam()
        job_compute_genre_trends()

    print_schedule_status()
    console.print("\n[green]Scheduler uruchomiony. Ctrl+C aby zatrzymać.[/green]\n")

    while True:
        schedule.run_pending()
        time.sleep(60)  # sprawdzaj co minutę


def run_in_background() -> threading.Thread:
    """
    Uruchamia scheduler w tle (wątek daemon).
    Użyj w app.py jeśli chcesz jeden proces:
    
        from scheduler import run_in_background
        run_in_background()  # wywołaj przed st.set_page_config
    """
    thread = threading.Thread(
        target=run_scheduler,
        kwargs={"run_immediately": False},
        daemon=True,
        name="GDIntel-Scheduler",
    )
    thread.start()
    console.print("[dim]Scheduler uruchomiony w tle (daemon thread)[/dim]")
    return thread


# ── Entrypoint ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    # python scheduler.py --now  → uruchom joby natychmiast
    run_now = "--now" in sys.argv or "-n" in sys.argv

    try:
        run_scheduler(run_immediately=run_now)
    except KeyboardInterrupt:
        console.print("\n[yellow]Scheduler zatrzymany.[/yellow]")
