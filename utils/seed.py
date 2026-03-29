"""
utils/seed.py — Wypełnia bazę realistycznymi danymi demonstracyjnymi.

Używaj gdy:
  - Chcesz pokazać demo bez czekania na scrape
  - Piszesz testy
  - Lokalny development bez internetu

Uruchomienie:
    python utils/seed.py
    python utils/seed.py --full   # więcej rekordów
"""
import random
import sys
from datetime import datetime, timedelta

from rich.console import Console
from rich.progress import track

from db.database import init_db, get_session, get_db_stats
from db.models import Game, GenreTrend

console = Console()
random.seed(42)  # powtarzalne wyniki


# ── Dane bazowe ──────────────────────────────────────────────────────────────
GENRE_PROFILES = {
    "Roguelite": {
        "tags": ["Roguelite", "Roguelike", "Dungeon Crawler", "Action", "Indie"],
        "price_range": (7.99, 19.99),
        "owners_range": (2_000, 150_000),
        "review_range": (72, 96),
        "playtime_range": (600, 2400),   # minuty
        "release_years": range(2019, 2025),
    },
    "Cozy": {
        "tags": ["Cozy", "Farming Sim", "Relaxing", "Casual", "Indie"],
        "price_range": (6.99, 14.99),
        "owners_range": (1_500, 200_000),
        "review_range": (75, 98),
        "playtime_range": (900, 4800),
        "release_years": range(2020, 2025),
    },
    "Survival": {
        "tags": ["Survival", "Crafting", "Open World", "Multiplayer", "Sandbox"],
        "price_range": (9.99, 29.99),
        "owners_range": (5_000, 500_000),
        "review_range": (60, 90),
        "playtime_range": (1200, 9600),
        "release_years": range(2018, 2025),
    },
    "Horror": {
        "tags": ["Horror", "Atmospheric", "Psychological Horror", "Indie", "Thriller"],
        "price_range": (4.99, 12.99),
        "owners_range": (500, 80_000),
        "review_range": (68, 94),
        "playtime_range": (120, 480),
        "release_years": range(2018, 2025),
    },
    "Idle": {
        "tags": ["Idler", "Incremental", "Clicker", "Strategy", "Casual"],
        "price_range": (0.0, 9.99),
        "owners_range": (1_000, 100_000),
        "review_range": (65, 88),
        "playtime_range": (2400, 14400),
        "release_years": range(2017, 2025),
    },
    "Puzzle": {
        "tags": ["Puzzle", "Logic", "Casual", "Indie", "Relaxing"],
        "price_range": (3.99, 12.99),
        "owners_range": (500, 50_000),
        "review_range": (70, 96),
        "playtime_range": (120, 600),
        "release_years": range(2016, 2025),
    },
    "Visual Novel": {
        "tags": ["Visual Novel", "Story Rich", "Anime", "Indie", "Romance"],
        "price_range": (4.99, 14.99),
        "owners_range": (300, 40_000),
        "review_range": (70, 96),
        "playtime_range": (240, 1800),
        "release_years": range(2016, 2025),
    },
    "Platformer": {
        "tags": ["Platformer", "2D", "Action", "Metroidvania", "Indie"],
        "price_range": (5.99, 19.99),
        "owners_range": (300, 60_000),
        "review_range": (65, 94),
        "playtime_range": (180, 900),
        "release_years": range(2015, 2025),
    },
}

# Przykładowe nazwy gier per gatunek
GAME_NAME_PATTERNS = {
    "Roguelite": [
        "Shattered Abyss", "Cursed Dungeon", "Rift Runner", "Shadow Loop",
        "Neon Depths", "Infernal Cascade", "Voidborn Run", "Crystal Descent",
        "Ember Rogue", "Fractured Path", "Arcane Dive", "Gloom Crawler",
    ],
    "Cozy": [
        "Meadow Life", "Sunflower Farm", "Cozy Cottage", "Harvest Dreams",
        "Little Garden", "Petal Fields", "Valley of Rest", "Warm Hearth",
        "Morning Dew", "Gentle Acres", "Blossom Bay", "Quiet Creek",
    ],
    "Survival": [
        "Iron Wilds", "Frozen Frontier", "Dead Lands", "Rust World",
        "Storm Shelter", "Primal Ground", "Bare Earth", "Lost Domain",
        "Last Haven", "Wasteland Craft", "Forest Edge", "Deep Wild",
    ],
    "Horror": [
        "Whispering Dark", "Manor of Fear", "Pale Visitor", "Crimson Dread",
        "Hollow Screams", "The Presence", "Beneath the Skin", "Fog Walker",
        "Unseen Horror", "Last Breath", "Shadow Watcher", "Void Stare",
    ],
    "Idle": [
        "Idle Kingdom", "Clicker Empire", "Incremental World", "Resource Loop",
        "Auto Factory", "Number Grower", "Prestige Loop", "Infinite Mine",
    ],
    "Puzzle": [
        "Logic Box", "Color Shift", "Block Mind", "Pipe Dream",
        "Grid Solver", "Path Finder", "Neural Maze", "Sequence",
    ],
    "Visual Novel": [
        "Hearts & Stars", "Last Summer", "Crimson Petal", "Digital Love",
        "Another Life", "Fading Light", "Promise", "Second Chance",
    ],
    "Platformer": [
        "Pixel Knight", "Sky Jumper", "Cave Explorer", "Neon Runner",
        "Crystal Walker", "Shadow Leap", "Iron Boot", "Cloud Dancer",
    ],
}

DEVELOPERS = [
    "Pixel Forge", "Dream Studio", "Lone Wolf Games", "Two Pixels",
    "Indie Core", "Starfall Dev", "Micro Games", "Solo Craft",
    "Binary Dreams", "Tiny Studio", "Quiet Games", "Dark Corner Dev",
    "Morning Light", "Silent Code", "Ember Works", "Pixel Thread",
]


# ── Seed Functions ────────────────────────────────────────────────────────────
def seed_games(games_per_genre: int = 30) -> int:
    """Generuje i zapisuje gry demonstracyjne."""
    init_db()
    saved = 0
    app_id_counter = 100_000  # zaczynamy od 100k żeby nie kolidować z prawdziwymi

    with get_session() as db:
        # Wyczyść stare dane seed
        existing_count = db.query(Game).count()
        if existing_count > 0:
            console.print(f"[yellow]⚠ W bazie jest już {existing_count} gier.[/yellow]")
            if not _confirm("Nadpisać dane?"):
                return 0
            db.query(Game).filter(Game.app_id >= 100_000).delete()
            console.print("[dim]Stare dane seed usunięte[/dim]")

        for genre, profile in track(GENRE_PROFILES.items(), description="Generowanie gier..."):
            names = GAME_NAME_PATTERNS.get(genre, [f"{genre} Game {i}" for i in range(games_per_genre)])

            for i in range(games_per_genre):
                # Losowe właściwości w zakresach profilu
                price = round(random.uniform(*profile["price_range"]), 2)
                owners_min_raw = random.randint(*profile["owners_range"])
                # Zaokrąglij do typowych progów SteamSpy
                owners_min = _round_to_steamspy_bucket(owners_min_raw * 0.8)
                owners_max = _round_to_steamspy_bucket(owners_min_raw * 1.2)

                positive_ratio = random.uniform(*[r / 100 for r in profile["review_range"]])
                total_reviews = random.randint(10, 5000)
                positive = int(total_reviews * positive_ratio)
                negative = total_reviews - positive

                playtime = random.randint(*profile["playtime_range"])
                release_year = random.choice(list(profile["release_years"]))
                release_date = datetime(
                    release_year,
                    random.randint(1, 12),
                    random.randint(1, 28),
                )

                # Tagi: główny gatunek + losowe dodatkowe
                primary_tag = profile["tags"][0]
                extra_tags = random.sample(profile["tags"][1:], k=min(3, len(profile["tags"]) - 1))
                tags = {primary_tag: random.randint(200, 2000)}
                for tag in extra_tags:
                    tags[tag] = random.randint(50, 500)

                game = Game(
                    app_id=app_id_counter + saved,
                    name=names[i % len(names)] + (f" {i // len(names) + 1}" if i >= len(names) else ""),
                    developer=random.choice(DEVELOPERS),
                    publisher=random.choice(DEVELOPERS),
                    owners_min=owners_min,
                    owners_max=owners_max,
                    players_forever=int(owners_min * random.uniform(1.1, 2.0)),
                    average_playtime=playtime,
                    median_playtime=int(playtime * 0.6),
                    price_usd=price,
                    positive=positive,
                    negative=negative,
                    tags=tags,
                    release_date=release_date,
                )
                db.add(game)
                saved += 1

    return saved


def seed_genre_trends(days: int = 30) -> int:
    """Generuje historię trendów dla wykresów i forecasting."""
    init_db()
    now = datetime.utcnow()

    # Bazowe wartości per gatunek + trend
    baselines = {
        "Roguelite":    {"owners": 45_000, "growth": 1.008, "review": 84, "viewers": 25_000},
        "Cozy":         {"owners": 38_000, "growth": 1.010, "review": 87, "viewers": 18_000},
        "Survival":     {"owners": 62_000, "growth": 1.015, "review": 76, "viewers": 45_000},
        "Horror":       {"owners": 22_000, "growth": 1.012, "review": 79, "viewers": 12_000},
        "Idle":         {"owners": 18_000, "growth": 1.005, "review": 72, "viewers": 8_000},
        "Puzzle":       {"owners": 15_000, "growth": 1.003, "review": 81, "viewers": 5_000},
        "Visual Novel": {"owners": 12_000, "growth": 1.006, "review": 78, "viewers": 4_000},
        "Platformer":   {"owners": 11_000, "growth": 1.002, "review": 74, "viewers": 6_000},
    }

    saved = 0
    with get_session() as db:
        # Wyczyść stare trendy
        db.query(GenreTrend).delete()

        for day_offset in range(days, 0, -1):
            record_date = now - timedelta(days=day_offset)

            for genre, base in baselines.items():
                # Wzrost + szum losowy
                growth_factor = base["growth"] ** (days - day_offset)
                noise = random.uniform(0.95, 1.05)

                avg_owners = int(base["owners"] * growth_factor * noise)
                avg_revenue = avg_owners * random.uniform(8.0, 16.0)  # uproszczony model

                # Sezonowość: Q4 (Paź-Gru) +15%
                if record_date.month in (10, 11, 12):
                    avg_owners = int(avg_owners * 1.15)
                    avg_revenue *= 1.15

                db.add(GenreTrend(
                    genre=genre,
                    recorded_at=record_date,
                    game_count=100 + (days - day_offset) * 2,
                    avg_owners=avg_owners,
                    total_owners=avg_owners * (100 + day_offset),
                    avg_revenue=round(avg_revenue, 2),
                    avg_review_score=base["review"] + random.uniform(-2, 2),
                    avg_playtime_h=random.uniform(8, 50),
                    avg_price=random.uniform(7.99, 19.99),
                    twitch_viewers=int(base["viewers"] * growth_factor * noise),
                ))
                saved += 1

    return saved


def _round_to_steamspy_bucket(n: float) -> int:
    """SteamSpy zaokrągla właścicieli do konkretnych progów."""
    buckets = [0, 20_000, 50_000, 100_000, 200_000, 500_000, 1_000_000, 2_000_000]
    rounded = int(n)
    for bucket in buckets:
        if rounded < bucket:
            return bucket
    return 2_000_000


def _confirm(msg: str) -> bool:
    try:
        return input(f"{msg} [t/N] ").strip().lower() in ("t", "tak", "y", "yes")
    except EOFError:
        return True  # non-interactive (testy)


# ── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    full_mode = "--full" in sys.argv
    games_per_genre = 50 if full_mode else 20
    trend_days = 60 if full_mode else 30

    console.rule("[bold]GDIntel — Seed danych demonstracyjnych[/bold]")

    console.print(f"\nTryb: {'[yellow]FULL[/yellow]' if full_mode else 'standard'}")
    console.print(f"Gier per gatunek: {games_per_genre}")
    console.print(f"Dni historii trendów: {trend_days}\n")

    n_games = seed_games(games_per_genre)
    console.print(f"[green]✓[/green] Gry: {n_games} rekordów")

    n_trends = seed_genre_trends(trend_days)
    console.print(f"[green]✓[/green] Trendy: {n_trends} rekordów")

    stats = get_db_stats()
    console.rule("[green]Gotowe![/green]")
    console.print(f"  Gry w DB:    {stats['games']:,}")
    console.print(f"  Trendy w DB: {stats['genre_trends']:,}")
    console.print(f"\nUruchom: [bold]streamlit run app.py[/bold]")
