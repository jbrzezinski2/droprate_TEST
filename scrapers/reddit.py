"""
scrapers/reddit.py — Pobieranie sygnałów z Reddit dla gamedev trendów.

Analizowane subreddity:
  r/indiegaming     — gracze dyskutują o indie
  r/gamedev         — devs dyskutują o developmencie
  r/games           — ogólna dyskusja o grach
  r/patientgamers   — gracze z długą listą do zagrania

Wynik: słowa kluczowe, gatunki, gry które "buzzują".

Wymaga kluczy Reddit OAuth (darmowe):
  reddit.com/prefs/apps → utwórz "script" app
"""
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
from cachetools import TTLCache
from rich.console import Console
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

console = Console()
_cache: TTLCache = TTLCache(maxsize=200, ttl=3600)  # 1h cache

REDDIT_BASE = "https://oauth.reddit.com"
REDDIT_AUTH = "https://www.reddit.com/api/v1/access_token"

# Subreddity do monitorowania
GAMEDEV_SUBREDDITS = [
    "indiegaming",
    "gamedev",
    "games",
    "patientgamers",
    "SteamDeals",
]

# Słowa kluczowe → gatunek (do klasyfikacji postów)
GENRE_KEYWORDS: dict[str, list[str]] = {
    "Roguelite": ["roguelite", "roguelike", "run-based", "rogue-lite", "deckbuilder", "dead cells", "hades", "slay the spire"],
    "Cozy":      ["cozy", "cosy", "relaxing", "chill", "farming sim", "stardew", "wholesome", "cute"],
    "Survival":  ["survival", "crafting", "base building", "open world survival", "valheim", "rust", "minecraft"],
    "Horror":    ["horror", "scary", "jumpscare", "atmospheric horror", "psychological horror"],
    "Puzzle":    ["puzzle", "brain teaser", "logic puzzle", "sokoban"],
    "Idle":      ["idle game", "incremental", "clicker", "idle rpg"],
    "Visual Novel": ["visual novel", "vn", "dating sim", "kinetic novel"],
    "Platformer": ["platformer", "metroidvania", "2d platformer", "side-scroller"],
}


# ── Auth ──────────────────────────────────────────────────────────────────────
_reddit_token: str | None = None
_token_expires: float = 0.0


def _get_reddit_token() -> str | None:
    """Client Credentials OAuth dla Reddit."""
    global _reddit_token, _token_expires

    if not settings.reddit_client_id or not settings.reddit_client_secret:
        return None

    if _reddit_token and time.time() < _token_expires - 30:
        return _reddit_token

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                REDDIT_AUTH,
                data={"grant_type": "client_credentials"},
                auth=(settings.reddit_client_id, settings.reddit_client_secret),
                headers={"User-Agent": settings.reddit_user_agent},
            )
            resp.raise_for_status()
            data = resp.json()
            _reddit_token = data["access_token"]
            _token_expires = time.time() + data.get("expires_in", 3600)
            return _reddit_token
    except Exception as e:
        console.print(f"[yellow]⚠[/yellow] Reddit auth błąd: {e}")
        return None


def _reddit_headers() -> dict | None:
    token = _get_reddit_token()
    if not token:
        return None
    return {
        "Authorization": f"Bearer {token}",
        "User-Agent": settings.reddit_user_agent,
    }


# ── Fetch Posts ───────────────────────────────────────────────────────────────
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def fetch_subreddit_hot(subreddit: str, limit: int = 50) -> list[dict]:
    """Pobiera hot posty z subredditu."""
    cache_key = f"reddit_hot_{subreddit}_{limit}"
    if cache_key in _cache:
        return _cache[cache_key]

    headers = _reddit_headers()
    if not headers:
        return []

    with httpx.Client(timeout=20.0) as client:
        resp = client.get(
            f"{REDDIT_BASE}/r/{subreddit}/hot",
            headers=headers,
            params={"limit": limit, "raw_json": 1},
        )
        resp.raise_for_status()
        data = resp.json()

    posts = []
    for child in data.get("data", {}).get("children", []):
        p = child["data"]
        posts.append({
            "id": p.get("id"),
            "title": p.get("title", ""),
            "selftext": p.get("selftext", "")[:500],  # tylko pierwsze 500 znaków
            "score": p.get("score", 0),
            "num_comments": p.get("num_comments", 0),
            "upvote_ratio": p.get("upvote_ratio", 0.0),
            "url": p.get("url", ""),
            "created_utc": datetime.fromtimestamp(p.get("created_utc", 0)),
            "subreddit": subreddit,
            "flair": p.get("link_flair_text", ""),
        })

    time.sleep(0.5)  # Reddit rate limit: 60 req/min
    _cache[cache_key] = posts
    return posts


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def fetch_subreddit_search(subreddit: str, query: str, limit: int = 25) -> list[dict]:
    """Przeszukuje subreddit po frazie."""
    headers = _reddit_headers()
    if not headers:
        return []

    with httpx.Client(timeout=20.0) as client:
        resp = client.get(
            f"{REDDIT_BASE}/r/{subreddit}/search",
            headers=headers,
            params={"q": query, "sort": "relevance", "t": "month", "limit": limit, "raw_json": 1},
        )
        resp.raise_for_status()
        data = resp.json()

    posts = [
        {
            "title": p["data"].get("title", ""),
            "score": p["data"].get("score", 0),
            "num_comments": p["data"].get("num_comments", 0),
            "subreddit": subreddit,
        }
        for p in data.get("data", {}).get("children", [])
    ]
    time.sleep(0.5)
    return posts


# ── Analiza ───────────────────────────────────────────────────────────────────
@dataclass
class RedditSignal:
    """Sygnał trendów z Reddit dla jednego gatunku."""
    genre: str
    mention_count: int
    total_score: int          # suma upvote'ów postów z wzmianką
    avg_comments: float       # średnia komentarzy (engagement)
    top_posts: list[str] = field(default_factory=list)
    sentiment_score: float = 0.0   # 0..1 (pozytywny bias)
    trend_velocity: float = 0.0    # wzrost wzmianek (jeśli dane historyczne)


def classify_post_genres(post: dict) -> list[str]:
    """
    Klasyfikuje post do gatunków na podstawie tytułu i tekstu.
    Prosty keyword matching — wystarczy dla MVP.
    """
    text = (post.get("title", "") + " " + post.get("selftext", "")).lower()
    matched_genres = []

    for genre, keywords in GENRE_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            matched_genres.append(genre)

    return matched_genres


def calculate_sentiment(text: str) -> float:
    """
    Prosta analiza sentymentu bez LLM (keyword-based).
    Zwraca: 0.0 (bardzo negatywny) .. 1.0 (bardzo pozytywny)

    W produkcji: zamień na Claude API z batch processing.
    """
    positive_words = {
        "great", "love", "amazing", "awesome", "best", "excellent",
        "fantastic", "perfect", "beautiful", "fun", "addictive",
        "recommend", "worth", "brilliant", "outstanding", "gem",
        "underrated", "hidden gem", "10/10", "masterpiece",
    }
    negative_words = {
        "bad", "terrible", "awful", "boring", "disappointment",
        "waste", "broken", "buggy", "overpriced", "mediocre",
        "avoid", "refund", "incomplete", "unfinished", "cash grab",
    }

    words = re.findall(r"\b\w+\b", text.lower())
    pos = sum(1 for w in words if w in positive_words)
    neg = sum(1 for w in words if w in negative_words)
    total = pos + neg

    return (pos / total) if total > 0 else 0.5


def analyze_reddit_trends(
    subreddits: list[str] | None = None,
    posts_per_sub: int = 50,
) -> dict[str, RedditSignal]:
    """
    Główna funkcja analizy — zbiera posty i klasyfikuje do gatunków.

    Args:
        subreddits: lista subredditów do przeszukania (domyślnie GAMEDEV_SUBREDDITS)
        posts_per_sub: ile postów per subreddit

    Returns:
        dict {genre: RedditSignal}
    """
    if not settings.reddit_client_id:
        console.print("[yellow]⚠[/yellow] Brak kluczy Reddit — pomijam analizę Reddit")
        return {}

    subs = subreddits or GAMEDEV_SUBREDDITS
    genre_data: dict[str, list[dict]] = {g: [] for g in GENRE_KEYWORDS}

    for sub in subs:
        console.print(f"[cyan]→[/cyan] Analizuję r/{sub}...")
        posts = fetch_subreddit_hot(sub, posts_per_sub)

        for post in posts:
            genres = classify_post_genres(post)
            for genre in genres:
                if genre in genre_data:
                    genre_data[genre].append(post)

    # Buduj sygnały
    signals: dict[str, RedditSignal] = {}
    for genre, posts in genre_data.items():
        if not posts:
            continue

        signals[genre] = RedditSignal(
            genre=genre,
            mention_count=len(posts),
            total_score=sum(p.get("score", 0) for p in posts),
            avg_comments=sum(p.get("num_comments", 0) for p in posts) / len(posts),
            top_posts=[
                p["title"] for p in
                sorted(posts, key=lambda x: x.get("score", 0), reverse=True)[:3]
            ],
            sentiment_score=sum(
                calculate_sentiment(p.get("title", "") + " " + p.get("selftext", ""))
                for p in posts
            ) / len(posts),
        )

    # Sortuj wg wzmianek
    return dict(sorted(signals.items(), key=lambda x: x[1].mention_count, reverse=True))


def get_trending_games_from_reddit(subreddit: str = "indiegaming", limit: int = 100) -> Counter:
    """
    Wyciąga nazwy gier z postów (uproszczone — wykrywa frazę w cudzysłowie lub po 'game:').
    Zwraca Counter {nazwa_gry: liczba_wzmianek}.
    """
    posts = fetch_subreddit_hot(subreddit, limit)
    game_mentions: Counter = Counter()

    for post in posts:
        # Wzorce: "Gra X", [Gra X], "just finished X" itp.
        text = post.get("title", "")
        quoted = re.findall(r'"([^"]{3,40})"|\[([^\]]{3,40})\]', text)
        for match in quoted:
            name = (match[0] or match[1]).strip()
            if name and not name.lower().startswith("http"):
                game_mentions[name] += 1

        # Uwzględnij score jako wagę
        weight = max(1, post.get("score", 1) // 100)
        for name in list(game_mentions.keys()):
            game_mentions[name] += weight - 1  # już dodano 1 wyżej

    return game_mentions


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not settings.reddit_client_id:
        console.print("[yellow]Brak kluczy Reddit — test pominięty[/yellow]")
        console.print("Dodaj REDDIT_CLIENT_ID i REDDIT_CLIENT_SECRET do .env")
    else:
        console.print("[bold]Analiza Reddit trendów gamedev[/bold]\n")
        signals = analyze_reddit_trends(["indiegaming", "gamedev"], posts_per_sub=30)
        for genre, signal in signals.items():
            console.print(
                f"  {genre:15} | wzmianki: {signal.mention_count:3} | "
                f"score: {signal.total_score:5} | sentiment: {signal.sentiment_score:.2f}"
            )
