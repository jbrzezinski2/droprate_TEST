"""
utils/forecasting.py — Prognozowanie trendów przy użyciu Meta Prophet.

Prophet to biblioteka do forecasting'u szeregów czasowych,
świetna dla danych z sezonowością (np. sprzedaż gier w Q4).

Użycie:
    from utils.forecasting import forecast_genre_trend, forecast_revenue

Jeśli baza ma mało danych (<14 punktów) — fallback do prostej regresji liniowej.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from rich.console import Console

warnings.filterwarnings("ignore")  # Prophet bywa gadatliwy
console = Console()


# ── Struktury danych ────────────────────────────────────────────────────────
@dataclass
class ForecastResult:
    """Wynik prognozy — dane + metadane."""
    genre: str
    metric: str                  # "owners" | "revenue" | "review_score"
    historical: pd.DataFrame     # kolumny: ds, y
    forecast: pd.DataFrame       # kolumny: ds, yhat, yhat_lower, yhat_upper
    horizon_days: int
    method: Literal["prophet", "linear_fallback"]
    trend_direction: Literal["up", "down", "flat"]
    trend_pct: float             # % zmiana na horyzoncie
    confidence_interval: float   # szerokość CI jako % wartości

    @property
    def last_value(self) -> float:
        return self.historical["y"].iloc[-1] if not self.historical.empty else 0.0

    @property
    def predicted_value(self) -> float:
        return self.forecast["yhat"].iloc[-1] if not self.forecast.empty else 0.0

    @property
    def summary(self) -> str:
        direction = "↑" if self.trend_direction == "up" else ("↓" if self.trend_direction == "down" else "→")
        return (
            f"{self.genre} / {self.metric}: "
            f"{self.last_value:,.0f} → {self.predicted_value:,.0f} "
            f"({direction}{abs(self.trend_pct):.1f}% / {self.horizon_days}d) "
            f"[{self.method}]"
        )


# ── Prophet Forecast ────────────────────────────────────────────────────────
def forecast_genre_trend(
    historical_df: pd.DataFrame,
    genre: str,
    metric: str = "avg_owners",
    horizon_days: int = 90,
) -> ForecastResult | None:
    """
    Prognozuje trend dla gatunku na podstawie historycznych danych z bazy.

    Args:
        historical_df: DataFrame z kolumnami 'recorded_at' i <metric>
                       (z get_trend_history_df())
        genre:         Nazwa gatunku np. "Roguelite"
        metric:        Kolumna do prognozowania
        horizon_days:  Na ile dni w przód prognozować

    Returns:
        ForecastResult lub None gdy za mało danych
    """
    # Filtruj do wybranego gatunku
    df = historical_df[historical_df["genre"] == genre].copy()
    df = df.dropna(subset=["recorded_at", metric])
    df = df.sort_values("recorded_at")

    if df.empty or metric not in df.columns:
        console.print(f"[yellow]⚠[/yellow] Brak danych dla {genre}/{metric}")
        return None

    # Prophet potrzebuje kolumn 'ds' i 'y'
    prophet_df = pd.DataFrame({
        "ds": pd.to_datetime(df["recorded_at"]),
        "y": df[metric].astype(float),
    }).dropna()

    # Minimum danych
    MIN_POINTS = 7
    if len(prophet_df) < MIN_POINTS:
        console.print(
            f"[dim]Za mało danych dla Prophet ({len(prophet_df)} < {MIN_POINTS})"
            f" — fallback do regresji[/dim]"
        )
        return _linear_forecast(prophet_df, genre, metric, horizon_days)

    return _prophet_forecast(prophet_df, genre, metric, horizon_days)


def _prophet_forecast(
    df: pd.DataFrame,
    genre: str,
    metric: str,
    horizon_days: int,
) -> ForecastResult:
    """Prophet wyłączony na Windows — używamy regresji liniowej."""
    return _linear_forecast(df, genre, metric, horizon_days)
    try:
        from prophet import Prophet  # lazy import — ciężka biblioteka
    except ImportError:
        console.print("[yellow]Prophet nie zainstalowany — pip install prophet[/yellow]")
        return _linear_forecast(df, genre, metric, horizon_days)

    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
        changepoint_prior_scale=0.05,   # niżej = mniej agresywne zmiany
        seasonality_prior_scale=10.0,
        interval_width=0.80,            # 80% przedział ufności
        uncertainty_samples=500,
    )

    # Dodaj sezonowość Steam: Q4 (Halloween, Winter Sale) jest wyraźna
    model.add_seasonality(
        name="steam_seasonal",
        period=365.25 / 4,  # kwartalna
        fourier_order=5,
    )

    model.fit(df)

    future = model.make_future_dataframe(periods=horizon_days, freq="D")
    forecast = model.predict(future)

    # Tylko przyszłość
    forecast_only = forecast[forecast["ds"] > df["ds"].max()].copy()

    return _build_result(df, forecast_only, genre, metric, horizon_days, "prophet")


def _linear_forecast(
    df: pd.DataFrame,
    genre: str,
    metric: str,
    horizon_days: int,
) -> ForecastResult:
    """Fallback — prosta regresja liniowa gdy za mało danych dla Prophet."""
    if df.empty:
        empty = pd.DataFrame(columns=["ds", "yhat", "yhat_lower", "yhat_upper"])
        return ForecastResult(
            genre=genre, metric=metric, historical=df, forecast=empty,
            horizon_days=horizon_days, method="linear_fallback",
            trend_direction="flat", trend_pct=0.0, confidence_interval=0.0,
        )

    # Konwersja dat → liczby (dni od startu)
    x = (df["ds"] - df["ds"].min()).dt.days.values
    y = df["y"].values

    # Regresja
    coeffs = np.polyfit(x, y, 1) if len(x) > 1 else [0, y[0]]
    slope, intercept = coeffs

    # Generuj przyszłe punkty
    last_day = x.max()
    future_days = np.arange(last_day + 1, last_day + horizon_days + 1)
    future_dates = [df["ds"].max() + timedelta(days=int(d - last_day)) for d in future_days]
    yhat = slope * future_days + intercept

    # Uncertainty: ±15% prostego szacunku
    uncertainty = np.abs(yhat) * 0.15

    forecast_df = pd.DataFrame({
        "ds": future_dates,
        "yhat": yhat,
        "yhat_lower": yhat - uncertainty,
        "yhat_upper": yhat + uncertainty,
    })

    return _build_result(df, forecast_df, genre, metric, horizon_days, "linear_fallback")


def _build_result(
    historical: pd.DataFrame,
    forecast: pd.DataFrame,
    genre: str,
    metric: str,
    horizon_days: int,
    method: Literal["prophet", "linear_fallback"],
) -> ForecastResult:
    """Buduje ForecastResult z obliczonymi metadanymi."""
    last_val = historical["y"].iloc[-1] if not historical.empty else 0.0
    pred_val = forecast["yhat"].iloc[-1] if not forecast.empty else last_val

    if last_val > 0:
        trend_pct = (pred_val - last_val) / last_val * 100
    else:
        trend_pct = 0.0

    if trend_pct > 2:
        direction: Literal["up", "down", "flat"] = "up"
    elif trend_pct < -2:
        direction = "down"
    else:
        direction = "flat"

    # Szerokość CI jako % wartości
    if not forecast.empty and pred_val > 0:
        ci_width = (forecast["yhat_upper"].iloc[-1] - forecast["yhat_lower"].iloc[-1])
        confidence_interval = ci_width / pred_val * 100
    else:
        confidence_interval = 0.0

    return ForecastResult(
        genre=genre,
        metric=metric,
        historical=historical,
        forecast=forecast,
        horizon_days=horizon_days,
        method=method,
        trend_direction=direction,
        trend_pct=trend_pct,
        confidence_interval=confidence_interval,
    )


# ── Wykresy ─────────────────────────────────────────────────────────────────
def plot_forecast(result: ForecastResult, dark_mode: bool = True) -> go.Figure:
    """
    Plotly wykres prognozy z przedziałem ufności.
    Gotowy do wklejenia do Streamlit: st.plotly_chart(fig)
    """
    bg = "#0d1117" if dark_mode else "#ffffff"
    font_color = "#8892a8" if dark_mode else "#444444"
    grid_color = "rgba(255,255,255,0.04)" if dark_mode else "rgba(0,0,0,0.06)"

    color_map = {
        "avg_owners": "#00d4aa",
        "avg_revenue": "#4d9fff",
        "avg_review": "#ffd166",
        "twitch_viewers": "#9b5de5",
    }
    line_color = color_map.get(result.metric, "#00d4aa")

    fig = go.Figure()

    # Przedział ufności
    if not result.forecast.empty:
        fig.add_trace(go.Scatter(
            x=pd.concat([result.forecast["ds"], result.forecast["ds"][::-1]]),
            y=pd.concat([result.forecast["yhat_upper"], result.forecast["yhat_lower"][::-1]]),
            fill="toself",
            fillcolor=f"rgba({_hex_to_rgb(line_color)}, 0.12)",
            line=dict(color="rgba(0,0,0,0)"),
            name="Przedział ufności 80%",
            showlegend=True,
        ))

        # Linia prognozy
        fig.add_trace(go.Scatter(
            x=result.forecast["ds"],
            y=result.forecast["yhat"],
            line=dict(color=line_color, width=2, dash="dash"),
            name=f"Prognoza ({result.horizon_days}d)",
        ))

    # Linia historyczna
    if not result.historical.empty:
        fig.add_trace(go.Scatter(
            x=result.historical["ds"],
            y=result.historical["y"],
            line=dict(color=line_color, width=2.5),
            name="Dane historyczne",
            mode="lines+markers",
            marker=dict(size=4),
        ))

    # Pionowa linia podziału historia/prognoza
    if not result.historical.empty:
        fig.add_vline(
            x=result.historical["ds"].max(),
            line_dash="dot",
            line_color="#5a6580",
            annotation_text="Teraz",
            annotation_font_color="#5a6580",
        )

    direction_label = "↑" if result.trend_direction == "up" else ("↓" if result.trend_direction == "down" else "→")
    metric_labels = {
        "avg_owners": "Avg właściciele",
        "avg_revenue": "Avg przychód ($)",
        "avg_review": "Avg review (%)",
        "twitch_viewers": "Widzów Twitch",
    }

    fig.update_layout(
        title=dict(
            text=f"{result.genre} — {metric_labels.get(result.metric, result.metric)} "
                 f"| Prognoza: {direction_label}{abs(result.trend_pct):.1f}% / {result.horizon_days}d",
            font=dict(color=font_color, size=14),
        ),
        plot_bgcolor=bg, paper_bgcolor=bg,
        font=dict(color=font_color),
        xaxis=dict(gridcolor=grid_color, title="Data"),
        yaxis=dict(gridcolor=grid_color, title=metric_labels.get(result.metric, result.metric)),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        hovermode="x unified",
        height=380,
        margin=dict(t=60, b=40, l=60, r=20),
    )

    return fig


def _hex_to_rgb(hex_color: str) -> str:
    """#00d4aa → 0, 212, 170"""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r}, {g}, {b}"


# ── Multi-genre forecast ─────────────────────────────────────────────────────
def forecast_all_genres(
    trend_df: pd.DataFrame,
    metric: str = "avg_owners",
    horizon_days: int = 90,
) -> dict[str, ForecastResult]:
    """
    Prognozuje wszystkie gatunki z podanego DataFrame.
    Zwraca dict {genre: ForecastResult}.
    """
    results = {}
    genres = trend_df["genre"].unique()

    for genre in genres:
        result = forecast_genre_trend(trend_df, genre, metric, horizon_days)
        if result:
            results[genre] = result
            console.print(f"  {result.summary}")

    return results


def get_top_opportunity_genres(
    forecasts: dict[str, ForecastResult],
    top_n: int = 3,
) -> list[ForecastResult]:
    """
    Zwraca top N gatunków wg prognozowanego wzrostu.
    Filtruje tylko gatunki z trendem rosnącym.
    """
    rising = [r for r in forecasts.values() if r.trend_direction == "up"]
    return sorted(rising, key=lambda r: r.trend_pct, reverse=True)[:top_n]


# ── Revenue Model ─────────────────────────────────────────────────────────────
def estimate_solo_dev_revenue(
    genre: str,
    dev_months: int,
    price_usd: float,
    marketing_budget_pln: float = 1000.0,
    scenario: Literal["pessimistic", "base", "optimistic"] = "base",
) -> dict:
    """
    Prosta kalkulacja oczekiwanego przychodu dla solo deva.
    
    Model bazuje na medianie SteamSpy dla gatunku i scenariuszach.
    
    Returns dict z:
        - first_year_revenue_usd: przychód rok 1
        - break_even_months: miesiące do break-even
        - monthly_run_rate: stabilny MRR po peak
        - roi_pct: zwrot z inwestycji (dev time + koszty)
    """
    # Bazowe dane per gatunek (mediana indie, SteamSpy 2024)
    genre_baselines = {
        "Roguelite":    {"med_owners": 8_000,  "peak_month": 1, "tail_factor": 0.35},
        "Cozy":         {"med_owners": 10_000, "peak_month": 1, "tail_factor": 0.40},
        "Survival":     {"med_owners": 12_000, "peak_month": 1, "tail_factor": 0.30},
        "Horror":       {"med_owners": 5_000,  "peak_month": 1, "tail_factor": 0.25},
        "Idle":         {"med_owners": 4_000,  "peak_month": 2, "tail_factor": 0.50},
        "Puzzle":       {"med_owners": 3_500,  "peak_month": 1, "tail_factor": 0.20},
        "Visual Novel": {"med_owners": 3_000,  "peak_month": 1, "tail_factor": 0.30},
        "Platformer":   {"med_owners": 3_000,  "peak_month": 1, "tail_factor": 0.20},
    }

    baseline = genre_baselines.get(genre, {"med_owners": 5_000, "peak_month": 1, "tail_factor": 0.30})

    # Scenariusze
    multipliers = {"pessimistic": 0.3, "base": 1.0, "optimistic": 2.8}
    mult = multipliers[scenario]

    # Właściciele (szacunek)
    owners = int(baseline["med_owners"] * mult)

    # Marketing boost (liniowy, prosty model)
    marketing_boost = 1 + (marketing_budget_pln / 5000) * 0.2  # +20% za 5k PLN
    owners = int(owners * marketing_boost)

    # Przychód (Steam bierze 30%)
    gross_per_owner = price_usd * 0.70
    first_year_revenue = owners * gross_per_owner

    # Koszty: dev time (zakładamy 0 kosztu czasu) + narzędzia
    tool_costs_usd = (marketing_budget_pln / 4.0) + (dev_months * 50)  # ~200 PLN/mies. narzędzia
    net_revenue = first_year_revenue - tool_costs_usd

    # MRR po stabilizacji (długi ogon)
    monthly_run_rate = (owners * baseline["tail_factor"] * gross_per_owner) / 12

    # Break-even (w miesiącach od premiery)
    if monthly_run_rate > 0:
        break_even = tool_costs_usd / monthly_run_rate
    else:
        break_even = float("inf")

    # ROI
    roi_pct = (net_revenue / tool_costs_usd * 100) if tool_costs_usd > 0 else 0.0

    return {
        "scenario": scenario,
        "genre": genre,
        "dev_months": dev_months,
        "price_usd": price_usd,
        "estimated_owners": owners,
        "gross_revenue_usd": round(first_year_revenue, 2),
        "net_revenue_usd": round(net_revenue, 2),
        "tool_costs_usd": round(tool_costs_usd, 2),
        "monthly_run_rate_usd": round(monthly_run_rate, 2),
        "break_even_months": round(break_even, 1),
        "roi_pct": round(roi_pct, 1),
    }


# ── Quick test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from utils.data_processor import _fallback_trend_df

    console.print("[bold]Test forecasting (fallback data)[/bold]\n")
    df = _fallback_trend_df()

    result = forecast_genre_trend(df, "Roguelite", "avg_owners", horizon_days=60)
    if result:
        console.print(result.summary)

    console.print("\n[bold]Test kalkulatora ROI[/bold]")
    for scenario in ("pessimistic", "base", "optimistic"):
        r = estimate_solo_dev_revenue("Roguelite", 6, 14.99, 1000.0, scenario)
        console.print(
            f"  [{scenario:12}] owners: {r['estimated_owners']:,} | "
            f"net: ${r['net_revenue_usd']:,.0f} | "
            f"ROI: {r['roi_pct']:.0f}%"
        )
