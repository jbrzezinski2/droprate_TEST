"""
pages/forecast.py — Strona prognozy i kalkulatora ROI.

Streamlit wielostronicowy: ten plik jest automatycznie wykrywany
jako podstrona jeśli jest w folderze pages/.

Uruchom: streamlit run app.py → pojawi się w nawigacji.
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from utils.data_processor import get_trend_history_df, get_genre_stats_df
from utils.forecasting import (
    forecast_genre_trend,
    forecast_all_genres,
    get_top_opportunity_genres,
    estimate_solo_dev_revenue,
    plot_forecast,
    ForecastResult,
)

st.set_page_config(page_title="GDIntel — Prognoza", page_icon="📡", layout="wide")

# ── Custom CSS (spójny z app.py) ─────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #080c14; }
    section[data-testid="stSidebar"] { background: #0d1117; border-right: 1px solid #1e2d40; }
    [data-testid="metric-container"] { background: #0d1117; border: 1px solid #1e2d40; padding: 12px 16px; }
    [data-testid="metric-container"] [data-testid="stMetricValue"] { color: #00d4aa; font-size: 24px !important; font-weight: 700; }
    h1, h2, h3 { color: #d8e0f0 !important; }
    .stButton button { background: #00d4aa; color: #000; font-weight: 700; border: none; }
</style>
""", unsafe_allow_html=True)

st.title("📡 Prognoza trendów")
st.caption("Prophet time-series forecasting + kalkulator ROI dla solo deva")

# ── Ładowanie danych ──────────────────────────────────────────────────────────
@st.cache_data(ttl=1800)
def load_data():
    return get_trend_history_df(days=60), get_genre_stats_df()

trend_df, genre_df = load_data()
available_genres = trend_df["genre"].unique().tolist() if not trend_df.empty else [
    "Roguelite", "Cozy", "Survival", "Horror", "Idle"
]

# ═══════════════════════════════════════════════════════════════════════════
# SEKCJA 1: PROGNOZA TRENDU
# ═══════════════════════════════════════════════════════════════════════════
st.subheader("📈 Prognoza trendu gatunku")

col_ctrl, col_metric, col_horizon = st.columns(3)
with col_ctrl:
    selected_genre = st.selectbox("Gatunek", available_genres, index=0)
with col_metric:
    metric = st.selectbox(
        "Metryka",
        options=["avg_owners", "avg_revenue", "avg_review", "twitch_viewers"],
        format_func=lambda x: {
            "avg_owners": "Avg właściciele",
            "avg_revenue": "Avg przychód ($)",
            "avg_review": "Review score (%)",
            "twitch_viewers": "Widzów Twitch",
        }[x],
    )
with col_horizon:
    horizon = st.slider("Horyzont prognozy (dni)", 30, 180, 90, step=15)

if st.button("🔮 Generuj prognozę", use_container_width=False):
    with st.spinner(f"Prognozuję {selected_genre}..."):
        result = forecast_genre_trend(trend_df, selected_genre, metric, horizon)

    if result:
        # Metryki
        m1, m2, m3, m4 = st.columns(4)
        m1.metric(
            "Aktualna wartość",
            f"{result.last_value:,.0f}",
        )
        m2.metric(
            f"Prognoza ({horizon}d)",
            f"{result.predicted_value:,.0f}",
            delta=f"{result.trend_pct:+.1f}%",
            delta_color="normal" if result.trend_direction != "down" else "inverse",
        )
        m3.metric(
            "Kierunek",
            {"up": "↑ Rosnący", "down": "↓ Malejący", "flat": "→ Stabilny"}[result.trend_direction],
        )
        m4.metric(
            "Metoda",
            "Prophet" if result.method == "prophet" else "Regresja",
        )

        # Wykres
        fig = plot_forecast(result, dark_mode=True)
        st.plotly_chart(fig, use_container_width=True)

        # Interpretacja
        if result.trend_direction == "up":
            st.success(
                f"✅ **{selected_genre}** rośnie o **{result.trend_pct:.1f}%** "
                f"w ciągu {horizon} dni. Dobry moment na wejście."
            )
        elif result.trend_direction == "down":
            st.warning(
                f"⚠️ **{selected_genre}** spada o **{abs(result.trend_pct):.1f}%** "
                f"w ciągu {horizon} dni. Rozważ inny gatunek."
            )
        else:
            st.info(f"ℹ️ **{selected_genre}** jest stabilny (±{abs(result.trend_pct):.1f}%).")

        # Przedział ufności
        st.caption(
            f"Szerokość przedziału ufności: ±{result.confidence_interval:.0f}% "
            f"wartości prognozowanej. {'Wysoka niepewność.' if result.confidence_interval > 30 else 'Dobra precyzja.'}"
        )
    else:
        st.warning("Niewystarczająca ilość danych historycznych. Dodaj więcej dat w seed/scraping.")

st.divider()

# ═══════════════════════════════════════════════════════════════════════════
# SEKCJA 2: TOP SZANSE (wszystkie gatunki)
# ═══════════════════════════════════════════════════════════════════════════
st.subheader("🏆 Ranking szans — wszystkie gatunki")

with st.expander("Pokaż ranking prognozowanego wzrostu", expanded=True):
    with st.spinner("Prognozuję wszystkie gatunki..."):
        all_forecasts = forecast_all_genres(trend_df, metric="avg_owners", horizon_days=90)

    if all_forecasts:
        top_opps = get_top_opportunity_genres(all_forecasts, top_n=len(all_forecasts))

        ranking_data = []
        for r in top_opps:
            direction_icon = "↑" if r.trend_direction == "up" else ("↓" if r.trend_direction == "down" else "→")
            ranking_data.append({
                "Gatunek": r.genre,
                "Trend": f"{direction_icon} {abs(r.trend_pct):.1f}%",
                "Teraz": f"{r.last_value:,.0f}",
                "Za 90 dni": f"{r.predicted_value:,.0f}",
                "Metoda": r.method.replace("_", " ").title(),
            })

        df_rank = pd.DataFrame(ranking_data)
        st.dataframe(df_rank, use_container_width=True, hide_index=True)
    else:
        st.info("Uruchom seed danych lub poczekaj na scrape Steam.")

st.divider()

# ═══════════════════════════════════════════════════════════════════════════
# SEKCJA 3: KALKULATOR ROI
# ═══════════════════════════════════════════════════════════════════════════
st.subheader("🧮 Kalkulator ROI — Solo Dev")
st.caption("Szacuje przychody na podstawie mediany SteamSpy per gatunek")

col1, col2 = st.columns(2)

with col1:
    roi_genre = st.selectbox("Gatunek gry", list([
        "Roguelite", "Cozy", "Survival", "Horror", "Idle", "Puzzle", "Visual Novel", "Platformer"
    ]), key="roi_genre")
    dev_months = st.slider("Czas developmentu (miesiące)", 2, 24, 6)
    price_usd = st.number_input("Cena gry ($)", min_value=0.99, max_value=59.99, value=12.99, step=1.0)

with col2:
    marketing_pln = st.number_input("Budżet marketingowy (PLN)", min_value=0, max_value=20_000, value=1000, step=500)
    st.write("")  # spacer

if st.button("💰 Oblicz ROI", use_container_width=False):
    results_data = []
    for scenario in ("pessimistic", "base", "optimistic"):
        r = estimate_solo_dev_revenue(roi_genre, dev_months, price_usd, float(marketing_pln), scenario)
        results_data.append(r)

    # Wyświetl trzy scenariusze
    sc_cols = st.columns(3)
    icons = {"pessimistic": "😬", "base": "😊", "optimistic": "🚀"}
    colors = {"pessimistic": "#ef233c", "base": "#00d4aa", "optimistic": "#ffd166"}

    for col, r in zip(sc_cols, results_data):
        with col:
            scenario_name = r["scenario"].capitalize()
            icon = icons[r["scenario"]]
            col.metric(
                f"{icon} {scenario_name}",
                f"${r['net_revenue_usd']:,.0f}",
                help=f"Przychód netto rok 1 | Est. właściciele: {r['estimated_owners']:,}",
            )
            st.caption(f"Właściciele: ~{r['estimated_owners']:,}")
            st.caption(f"Break-even: {r['break_even_months']:.0f} mies.")
            st.caption(f"ROI: {r['roi_pct']:.0f}%")

    # Waterfall wykres
    st.write("")
    base_result = results_data[1]  # scenario: base

    fig_wf = go.Figure(go.Waterfall(
        orientation="v",
        measure=["absolute", "relative", "relative", "total"],
        x=["Koszty (narzędzia/mkt)", "Przychód brutto", "Prowizja Steam (30%)", "Przychód netto"],
        y=[
            -base_result["tool_costs_usd"],
            base_result["gross_revenue_usd"],
            -base_result["gross_revenue_usd"] * 0.30,
            base_result["net_revenue_usd"],
        ],
        connector={"line": {"color": "#1e2d40"}},
        decreasing={"marker": {"color": "#ef233c"}},
        increasing={"marker": {"color": "#00d4aa"}},
        totals={"marker": {"color": "#4d9fff"}},
        text=[
            f"-${base_result['tool_costs_usd']:,.0f}",
            f"+${base_result['gross_revenue_usd']:,.0f}",
            f"-${base_result['gross_revenue_usd'] * 0.30:,.0f}",
            f"${base_result['net_revenue_usd']:,.0f}",
        ],
        textposition="outside",
    ))
    fig_wf.update_layout(
        title="Waterfall ROI — scenariusz bazowy",
        plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
        font_color="#8892a8", height=360,
        yaxis_title="USD",
        title_font_color="#d8e0f0",
        showlegend=False,
    )
    st.plotly_chart(fig_wf, use_container_width=True)

    # Dodatkowy insight
    best = max(results_data, key=lambda x: x["net_revenue_usd"])
    st.info(
        f"💡 Przy scenariuszu **bazowym**: {roi_genre} z ceną ${price_usd:.2f} "
        f"powinien przynieść około **${base_result['net_revenue_usd']:,.0f} netto** w pierwszym roku. "
        f"Break-even po około **{base_result['break_even_months']:.0f} miesiącach** od premiery."
    )
