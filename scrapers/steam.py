"""
scrapers/steam.py — Pobieranie danych z SteamSpy i Steam Store API.

SteamSpy: szacowane przychody, liczba właścicieli, czas gry
Steam Store: ceny, tagi, recenzje, daty premier

Bez klucza API — oba są publicznie dostępne.
"""
import asyncio
import time
from datetime import datetime
from typing import Any

import httpx
from cachetools import TTLCache
from rich.console import Console

from config import settings

console = Console()

# In-memory cache — przeżywa restart Streamlita (ale nie serwera)
_cache: TTLCache = TTLCache(maxsize=1000, ttl=settings.cache_ttl_seconds)

# ── Stałe ────────────────────────────────────────────────────────────────────
STEAMSPY_BASE = "https://steamspy.com/api.php"
STEAM_STORE_BASE = "https://store.steampowered.com/api"

# Gatunki które nas interesują — pobierzemy top gry z każdego
TARGET_GENRES = [
    "Roguelite", "Roguelike", "Survival", "Crafting",
    "Cozy", "Farming Sim", "Horror", "Puzzle",
    "Visual Novel", "Idle", "Platformer", "RPG",
    "Strategy", "Simulation", "Action",
]

# SteamSpy używa tagów Steam — mapujemy gatunek → tag ID
GENRE_TO_TAG = {
    "Roguelite": "roguelite",
    "Roguelike": "roguelike",
    "Survival": "survival",
    "Crafting": "crafting",
    "Cozy": "cozy",
    "Horror": "horror",
    "Puzzle": "puzzle",
    "Visual Novel": "visual-novel",
    "Idle": "idler",
    "Platformer": "platformer",
    "RPG": "rpg",
    "Strategy": "strategy",
    "Simulation": "simulation",
}


# ── HTTP Client (współdzielony) ───────────────────────────────────────────────
def _get_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(30.0, connect=10.0),
        headers={"User-Agent": "GDIntel/1.0 (gamedev analytics tool)"},
        follow_redirects=True,
    )


# ── SteamSpy API ─────────────────────────────────────────────────────────────
def fetch_steamspy_tag(tag: str, page: int = 0) -> list[dict]:
    """
    Pobiera top gry dla danego tagu z SteamSpy.
    Zwraca listę słowników z danymi gry.

    Przykład:
        games = fetch_steamspy_tag("roguelite")
    """
    cache_key = f"spy_tag_{tag}_{page}"
    if cache_key in _cache:
        return _cache[cache_key]

    with _get_client() as client:
        resp = client.get(STEAMSPY_BASE, params={
            "request": "tag",
            "tag": tag,
            "page": page,
        })
        resp.raise_for_status()
        data = resp.json()

    # SteamSpy zwraca dict {app_id: {...}} — normalizujemy do listy
    games = []
    for app_id, info in data.items():
        games.append({
            "app_id": int(app_id),
            "name": info.get("name", ""),
            "developer": info.get("developer", ""),
            "publisher": info.get("publisher", ""),
            "owners_min": _parse_owners(info.get("owners", "0 .. 0"))[0],
            "owners_max": _parse_owners(info.get("owners", "0 .. 0"))[1],
            "players_forever": info.get("players_forever", 0),
            "average_playtime": info.get("average_forever", 0),
            "median_playtime": info.get("median_forever", 0),
            "price_usd": int(info.get("price", 0) or 0) / 100, # centy → dolary
            "positive": info.get("positive", 0),
            "negative": info.get("negative", 0),
            "tags": info.get("tags", {}),
            "genre": tag,
        })

    # Throttle — SteamSpy ma limit 1 req/s
    time.sleep(1.1)

    _cache[cache_key] = games
    return games


def fetch_steamspy_top100() -> list[dict]:
    """Pobiera top 100 gier z SteamSpy (według 2-tygodniowej aktywności)."""
    cache_key = "spy_top100"
    if cache_key in _cache:
        return _cache[cache_key]

    with _get_client() as client:
        resp = client.get(STEAMSPY_BASE, params={"request": "top100in2weeks"})
        resp.raise_for_status()
        data = resp.json()

    games = [
        {
            "app_id": int(app_id),
            "name": info.get("name", ""),
            "owners_min": _parse_owners(info.get("owners", "0 .. 0"))[0],
            "owners_max": _parse_owners(info.get("owners", "0 .. 0"))[1],
            "average_playtime": info.get("average_forever", 0),
            "price_usd": info.get("price", 0) / 100,
            "positive": info.get("positive", 0),
            "negative": info.get("negative", 0),
            "tags": info.get("tags", {}),
        }
        for app_id, info in data.items()
    ]

    time.sleep(1.1)
    _cache[cache_key] = games
    return games


def fetch_game_details(app_id: int) -> dict[str, Any] | None:
    """
    Pobiera szczegóły gry ze Steam Store API.
    Zwraca dict z genres, release_date, screenshots itp.
    """
    cache_key = f"steam_details_{app_id}"
    if cache_key in _cache:
        return _cache[cache_key]

    with _get_client() as client:
        resp = client.get(
            f"{STEAM_STORE_BASE}/appdetails",
            params={"appids": app_id, "cc": "us", "l": "en"},
        )
        resp.raise_for_status()
        data = resp.json()

    game_data = data.get(str(app_id), {})
    if not game_data.get("success"):
        return None

    info = game_data["data"]

    result = {
        "app_id": app_id,
        "name": info.get("name", ""),
        "short_description": info.get("short_description", ""),
        "genres": [g["description"] for g in info.get("genres", [])],
        "categories": [c["description"] for c in info.get("categories", [])],
        "release_date": _parse_date(info.get("release_date", {}).get("date", "")),
        "platforms": {
            "windows": info.get("platforms", {}).get("windows", False),
            "mac": info.get("platforms", {}).get("mac", False),
            "linux": info.get("platforms", {}).get("linux", False),
        },
        "is_free": info.get("is_free", False),
        "metacritic_score": info.get("metacritic", {}).get("score"),
        "header_image": info.get("header_image", ""),
    }

    time.sleep(0.5)  # grzeczny scraper — throttle
    _cache[cache_key] = result
    return result


# ── Aggregate fetch (używaj tego w UI) ──────────────────────────────────────
def fetch_genre_data(genre: str, pages: int = 1) -> list[dict]:
    """
    Pobiera dane dla gatunku (kilka stron SteamSpy).
    Gotowe do wrzucenia do bazy danych.
    """
    tag = GENRE_TO_TAG.get(genre, genre.lower().replace(" ", "-"))
    all_games = []

    for page in range(pages):
        try:
            games = fetch_steamspy_tag(tag, page)
            all_games.extend(games)
            console.print(f"[cyan]→[/cyan] {genre} strona {page}: {len(games)} gier")
        except Exception as e:
            console.print(f"[red]✗[/red] Błąd {genre} strona {page}: {e}")
            break

    return all_games


def fetch_all_genres(pages_per_genre: int = 1) -> dict[str, list[dict]]:
    """
    Pobiera dane dla wszystkich zdefiniowanych gatunków.
    Używaj ostrożnie — każdy gatunek = 1+ request do SteamSpy.
    """
    results = {}
    for genre in track(list(GENRE_TO_TAG.keys()), description="Pobieranie danych Steam..."):
        results[genre] = fetch_genre_data(genre, pages_per_genre)
    return results


# ── Helpers ──────────────────────────────────────────────────────────────────
def _parse_owners(owners_str: str) -> tuple[int, int]:
    """
    SteamSpy zwraca: "20,000 .. 50,000" → (20000, 50000)
    """
    try:
        parts = owners_str.replace(",", "").split("..")
        return int(parts[0].strip()), int(parts[1].strip())
    except Exception:
        return 0, 0


def _parse_date(date_str: str) -> datetime | None:
    """Parsuje różne formaty dat Steam."""
    formats = ["%d %b, %Y", "%b %d, %Y", "%b %Y", "%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


# ── Quick test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    console.print("[bold]Test scrapera SteamSpy[/bold]")
    games = fetch_steamspy_tag("roguelite", page=0)
    console.print(f"Pobrano {len(games)} gier roguelite")
    if games:
        g = games[0]
        console.print(f"Przykład: {g['name']} | owners: {g['owners_min']:,}–{g['owners_max']:,}")
