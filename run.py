"""
run.py — Ustawia PYTHONPATH i uruchamia seed/scheduler.
Użycie:
    python run.py seed
    python run.py scheduler
    python run.py app
"""
import sys
import os

# Dodaj główny folder projektu do ścieżki Pythona
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if len(sys.argv) < 2:
    print("Użycie: python run.py [seed|scrape|scheduler|app]")
    sys.exit(1)

command = sys.argv[1]

if command == "seed":
    from utils.seed import seed_games, seed_genre_trends
    from db.database import init_db, get_db_stats
    init_db()
    n_games = seed_games(20)
    print(f"✓ Gry: {n_games} rekordów")
    n_trends = seed_genre_trends(30)
    print(f"✓ Trendy: {n_trends} rekordów")
    stats = get_db_stats()
    print(f"\nGotowe! Gry: {stats['games']}, Trendy: {stats['genre_trends']}")
    print("Uruchom: streamlit run app.py")

elif command == "scrape":
    from db.database import init_db, get_session, get_db_stats
    from db.models import Game
    from scrapers.steam import fetch_genre_data, GENRE_TO_TAG

    init_db()
    total = 0

    for genre, tag in GENRE_TO_TAG.items():
        print(f"Pobieranie: {genre}...")
        try:
            games = fetch_genre_data(genre, pages=1)
            with get_session() as db:
                saved = 0
                for g in games:
                    existing = db.query(Game).filter_by(app_id=g["app_id"]).first()
                    if existing:
                        existing.owners_min = g.get("owners_min", 0)
                        existing.owners_max = g.get("owners_max", 0)
                        existing.positive = g.get("positive", 0)
                        existing.negative = g.get("negative", 0)
                        existing.price_usd = g.get("price_usd", 0.0)
                    else:
                        db.add(Game(
                            app_id=g["app_id"],
                            name=g["name"],
                            developer=g.get("developer", ""),
                            publisher=g.get("publisher", ""),
                            owners_min=g.get("owners_min", 0),
                            owners_max=g.get("owners_max", 0),
                            players_forever=g.get("players_forever", 0),
                            average_playtime=g.get("average_playtime", 0),
                            median_playtime=g.get("median_playtime", 0),
                            price_usd=g.get("price_usd", 0.0),
                            positive=g.get("positive", 0),
                            negative=g.get("negative", 0),
                            tags=g.get("tags", {}),
                        ))
                    saved += 1
            total += saved
            print(f"  ✓ {genre}: {saved} gier")
        except Exception as e:
            print(f"  ✗ {genre}: błąd — {e}")

    stats = get_db_stats()
    print(f"\nGotowe! Łącznie gier w bazie: {stats['games']:,}")

elif command == "scheduler":
    from scheduler import run_scheduler
    run_scheduler(run_immediately=True)

elif command == "app":
    os.system("streamlit run app.py")

else:
    print(f"Nieznana komenda: {command}")
    print("Dostępne: seed, scrape, scheduler, app")
