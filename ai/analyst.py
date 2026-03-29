"""
ai/analyst.py — Integracja z Claude API.

Dwa tryby:
  1. stream_analysis()  — streaming odpowiedzi do UI (Streamlit st.write_stream)
  2. generate_report()  — jednorazowy raport (z cache w DB)

System prompt jest wzbogacony o dane z bazy (uproszczony RAG).
"""
import hashlib
import json
from datetime import datetime, timedelta
from typing import Generator

import anthropic
from rich.console import Console

from config import settings
from db.database import get_session
from db.models import AIReport

console = Console()

# ── Client ────────────────────────────────────────────────────────────────────
def _get_client() -> anthropic.Anthropic:
    if not settings.has_anthropic_key:
        raise ValueError(
            "Brak ANTHROPIC_API_KEY w .env! "
            "Pobierz klucz na console.anthropic.com"
        )
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


# ── System Prompt Builder ─────────────────────────────────────────────────────
def build_system_prompt(market_context: dict | None = None) -> str:
    """
    Buduje system prompt z danymi rynkowymi z bazy danych.
    market_context: dane przekazane z UI (filtrowane dane gamedev)
    """
    base_prompt = """Jesteś GDIntel AI — ekspertem analitykiem rynku gier indie.
Pomagasz deweloperom gier podejmować lepsze decyzje biznesowe.

TWOJA ROLA:
- Analizujesz dane rynkowe Steam, Twitch, Itch.io
- Identyfikujesz wschodzące trendy gatunkowe
- Oceniasz ROI i ryzyko inwestycji w konkretne gatunki
- Doradzasz w kwestiach timingu premiery, wyceny, marketingu
- Odpowiadasz ZAWSZE po polsku, konkretnie i z liczbami

ZASADY:
- Używaj danych z kontekstu gdy są dostępne
- Podawaj zakresy (np. "$30k–$80k") zamiast jednej liczby
- Wskazuj niepewność gdy dane są niepełne
- Bądź bezpośredni — dev potrzebuje decyzji, nie ogólników
- Gdy czegoś nie wiesz — powiedz to wprost"""

    if not market_context:
        return base_prompt

    # Wzbogać prompt o aktualne dane z DB
    context_str = "\n\nAKTUALNE DANE RYNKOWE (z bazy GDIntel):\n"

    if "top_genres" in market_context:
        context_str += "\nTop gatunki wg liczby właścicieli gier:\n"
        for genre, stats in market_context["top_genres"].items():
            context_str += (
                f"  • {genre}: avg owners {stats.get('avg_owners', 0):,}, "
                f"avg review {stats.get('avg_review', 0):.0f}%, "
                f"gier w DB: {stats.get('count', 0)}\n"
            )

    if "total_games" in market_context:
        context_str += f"\nŁączna liczba gier w bazie: {market_context['total_games']:,}"

    if "last_updated" in market_context:
        context_str += f"\nOstatnia aktualizacja danych: {market_context['last_updated']}"

    return base_prompt + context_str


# ── Streaming Chat ────────────────────────────────────────────────────────────
def stream_analysis(
    user_message: str,
    chat_history: list[dict],
    market_context: dict | None = None,
) -> Generator[str, None, None]:
    """
    Generator streamujący odpowiedź Claude token po tokenie.
    
    Użycie w Streamlit:
        with st.chat_message("assistant"):
            response = st.write_stream(
                stream_analysis(prompt, history, context)
            )
    
    Args:
        user_message: aktualne pytanie użytkownika
        chat_history: lista {"role": "user"|"assistant", "content": "..."}
        market_context: opcjonalne dane z bazy do wzbogacenia kontekstu
    """
    client = _get_client()

    # Buduj messages dla API
    messages = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in chat_history
        if msg["role"] in ("user", "assistant")
    ]
    messages.append({"role": "user", "content": user_message})

    system_prompt = build_system_prompt(market_context)

    with client.messages.stream(
        model=settings.claude_analyst_model,
        max_tokens=settings.claude_max_tokens,
        system=system_prompt,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text


# ── Cached Report Generation ──────────────────────────────────────────────────
def generate_report(
    report_type: str,
    prompt: str,
    market_context: dict | None = None,
    cache_hours: int = 24,
) -> str:
    """
    Generuje raport AI z cache'owaniem w bazie danych.
    Identyczny prompt → odpowiedź z bazy (nie płacimy 2x).

    Args:
        report_type: "weekly" | "genre_analysis" | "trend_alert"
        prompt: treść zapytania
        market_context: dane rynkowe
        cache_hours: ile godzin cache'ować odpowiedź

    Returns:
        Wygenerowany raport jako string
    """
    # Hash promptu jako klucz cache
    prompt_hash = hashlib.sha256(
        f"{report_type}:{prompt}:{json.dumps(market_context or {}, sort_keys=True)}".encode()
    ).hexdigest()

    # Sprawdź cache w DB
    with get_session() as db:
        cached = (
            db.query(AIReport)
            .filter(
                AIReport.prompt_hash == prompt_hash,
                AIReport.expires_at > datetime.utcnow(),
            )
            .first()
        )
        if cached:
            console.print(f"[dim]Cache hit: {report_type}[/dim]")
            return cached.content

    # Generuj nowy raport
    console.print(f"[cyan]→[/cyan] Generuję raport: {report_type}")
    client = _get_client()
    system_prompt = build_system_prompt(market_context)

    response = client.messages.create(
        model=settings.claude_report_model,
        max_tokens=settings.claude_max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}],
    )

    content = response.content[0].text
    tokens_used = response.usage.input_tokens + response.usage.output_tokens

    # Zapisz do cache
    with get_session() as db:
        report = AIReport(
            report_type=report_type,
            prompt_hash=prompt_hash,
            content=content,
            model_used=settings.claude_report_model,
            tokens_used=tokens_used,
            expires_at=datetime.utcnow() + timedelta(hours=cache_hours),
        )
        db.add(report)

    console.print(f"[green]✓[/green] Raport wygenerowany ({tokens_used} tokenów)")
    return content


# ── Preset Prompts ────────────────────────────────────────────────────────────
def get_weekly_market_summary(market_context: dict) -> str:
    """Generuje tygodniowe podsumowanie rynku."""
    prompt = """Przeanalizuj aktualne dane rynkowe gamedev i przygotuj tygodniowy raport.

Format odpowiedzi:
**🔥 TOP TREND TYGODNIA**
[1 akapit o najgorętszym trendzie]

**📊 NAJLEPSZE GATUNKI (ROI)**
[3-5 gatunków z krótką analizą każdego]

**⚠️ CZEGO UNIKAĆ**
[1-2 czerwone flagi]

**🎯 REKOMENDACJA DLA SOLO DEVA**
[konkretna akcja do podjęcia w ciągu 7 dni]"""

    return generate_report("weekly", prompt, market_context, cache_hours=168)  # 1 tydzień


def get_genre_deep_dive(genre: str, market_context: dict) -> str:
    """Głęboka analiza konkretnego gatunku."""
    prompt = f"""Przeanalizuj gatunek: **{genre}**

Odpowiedz na:
1. Czy to dobry moment na wejście? (skala 1-10 z uzasadnieniem)
2. Jaki jest realny zakres przychodu dla indie gry w tym gatunku?
3. Kluczowe funkcje które MUSI mieć gra w tym gatunku żeby odnieść sukces?
4. Główni kompetytorzy i jak się wyróżnić?
5. Optymalny czas developmentu i cena sprzedaży?"""

    return generate_report(f"genre_{genre.lower()}", prompt, market_context, cache_hours=48)


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not settings.has_anthropic_key:
        console.print("[red]Brak ANTHROPIC_API_KEY w .env[/red]")
    else:
        console.print("[bold]Test streaming Claude API[/bold]")
        for chunk in stream_analysis(
            "Który gatunek gry polecasz dla solo deva z 6 miesiącami czasu?",
            chat_history=[],
        ):
            print(chunk, end="", flush=True)
        print()
