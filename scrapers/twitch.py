"""
scrapers/twitch.py — Pobieranie danych z Twitch API (viewership per gra).

Wymaga TWITCH_CLIENT_ID i TWITCH_CLIENT_SECRET w .env.
Jeśli brak kluczy — zwraca puste dane (nie blokuje reszty aplikacji).
"""
import time
from cachetools import TTLCache
from rich.console import Console
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

console = Console()
_cache: TTLCache = TTLCache(maxsize=500, ttl=1800)  # 30min cache

TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_API_BASE = "https://api.twitch.tv/helix"

_access_token: str | None = None
_token_expires_at: float = 0.0


# ── Auth ──────────────────────────────────────────────────────────────────────
def _get_access_token() -> str | None:
    """
    Pobiera OAuth token od Twitcha (Client Credentials flow).
    Token jest ważny ~60 dni — cache'ujemy w pamięci.
    """
    global _access_token, _token_expires_at

    if not settings.has_twitch_keys:
        return None

    # Jeśli token jest ważny — użyj z cache
    if _access_token and time.time() < _token_expires_at - 60:
        return _access_token

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(TWITCH_AUTH_URL, params={
                "client_id": settings.twitch_client_id,
                "client_secret": settings.twitch_client_secret,
                "grant_type": "client_credentials",
            })
            resp.raise_for_status()
            data = resp.json()
            _access_token = data["access_token"]
            _token_expires_at = time.time() + data.get("expires_in", 3600)
            console.print("[green]✓[/green] Twitch token uzyskany")
            return _access_token
    except Exception as e:
        console.print(f"[yellow]⚠[/yellow] Twitch auth błąd: {e}")
        return None


def _twitch_headers() -> dict | None:
    token = _get_access_token()
    if not token:
        return None
    return {
        "Authorization": f"Bearer {token}",
        "Client-Id": settings.twitch_client_id,
    }


# ── API Calls ─────────────────────────────────────────────────────────────────
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def fetch_top_games(limit: int = 100) -> list[dict]:
    """
    Pobiera top gry na Twitchu wg liczby widzów.
    Bardzo dobry sygnał trendów — viral games widać tu jako pierwsze.
    """
    cache_key = f"twitch_top_{limit}"
    if cache_key in _cache:
        return _cache[cache_key]

    headers = _twitch_headers()
    if not headers:
        console.print("[yellow]⚠[/yellow] Twitch API niedostępne (brak kluczy)")
        return []

    with httpx.Client(timeout=20.0) as client:
        resp = client.get(
            f"{TWITCH_API_BASE}/games/top",
            headers=headers,
            params={"first": min(limit, 100)},
        )
        resp.raise_for_status()
        data = resp.json()

    games = [
        {
            "twitch_game_id": item["id"],
            "name": item["name"],
            "box_art_url": item.get("box_art_url", ""),
        }
        for item in data.get("data", [])
    ]

    _cache[cache_key] = games
    return games


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def fetch_game_streams(game_name: str) -> dict:
    """
    Pobiera liczbę aktywnych streamów i widzów dla konkretnej gry.

    Przykład:
        stats = fetch_game_streams("Hades")
        # {"viewer_count": 45320, "stream_count": 890}
    """
    cache_key = f"twitch_streams_{game_name.lower()}"
    if cache_key in _cache:
        return _cache[cache_key]

    headers = _twitch_headers()
    if not headers:
        return {"viewer_count": 0, "stream_count": 0}

    # Najpierw znajdź game_id
    with httpx.Client(timeout=15.0) as client:
        game_resp = client.get(
            f"{TWITCH_API_BASE}/games",
            headers=headers,
            params={"name": game_name},
        )
        game_resp.raise_for_status()
        games = game_resp.json().get("data", [])

        if not games:
            return {"viewer_count": 0, "stream_count": 0}

        game_id = games[0]["id"]

        # Pobierz streamy dla tej gry
        streams_resp = client.get(
            f"{TWITCH_API_BASE}/streams",
            headers=headers,
            params={"game_id": game_id, "first": 100},
        )
        streams_resp.raise_for_status()
        streams = streams_resp.json().get("data", [])

    result = {
        "viewer_count": sum(s.get("viewer_count", 0) for s in streams),
        "stream_count": len(streams),
    }

    _cache[cache_key] = result
    return result


def fetch_genre_viewership(genre_keywords: list[str]) -> int:
    """
    Przybliżona liczba widzów dla gatunku na Twitchu.
    Szuka gier po słowach kluczowych i sumuje widzów.
    """
    top_games = fetch_top_games(200)
    total_viewers = 0

    keywords_lower = [k.lower() for k in genre_keywords]

    for game in top_games:
        game_name_lower = game["name"].lower()
        if any(kw in game_name_lower for kw in keywords_lower):
            stats = fetch_game_streams(game["name"])
            total_viewers += stats["viewer_count"]
            time.sleep(0.3)  # throttle

    return total_viewers


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not settings.has_twitch_keys:
        console.print("[yellow]Brak kluczy Twitch w .env — test pominięty[/yellow]")
    else:
        games = fetch_top_games(20)
        console.print(f"Top {len(games)} gier na Twitchu:")
        for i, g in enumerate(games[:5], 1):
            console.print(f"  {i}. {g['name']}")
