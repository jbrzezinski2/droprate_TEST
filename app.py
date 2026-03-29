"""
app.py — GDIntel Dashboard (Streamlit)

Uruchomienie:
    streamlit run app.py

Wymagania:
    cp .env.example .env  # i uzupełnij klucze
    pip install -r requirements.txt
    python -c "from db.database import init_db; init_db()"
"""
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from config import settings
from db.database import init_db, get_db_stats
from utils.data_processor import (
    get_genre_stats_df,
    get_trend_history_df,
    get_top_games_df,
    get_market_context,
)
from ai.analyst import stream_analysis, get_weekly_market_summary

# ── Konfiguracja Streamlit ───────────────────────────────────────────────────
st.set_page_config(
    page_title="GDIntel — GameDev Intelligence",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Główne tło */
    .stApp { background-color: #080c14; }
    
    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: #0d1117;
        border-right: 1px solid #1e2d40;
    }

    /* Metryki */
    [data-testid="metric-container"] {
        background: #0d1117;
        border: 1px solid #1e2d40;
        padding: 12px 16px;
    }
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: #00d4aa;
        font-size: 28px !important;
        font-weight: 700;
    }

    /* Dataframe */
    .stDataFrame { background: #0d1117; }

    /* Przyciski */
    .stButton button {
        background: #00d4aa;
        color: #000;
        font-weight: 700;
        border: none;
    }
    .stButton button:hover { background: #00b894; }

    /* Chat */
    .stChatMessage { background: #0d1117; border: 1px solid #1e2d40; }
    
    /* Nagłówki */
    h1, h2, h3 { color: #d8e0f0 !important; }
</style>
""", unsafe_allow_html=True)


# ── Init ─────────────────────────────────────────────────────────────────────
@st.cache_resource
def initialize():
    """Inicjalizacja bazy danych — tylko raz na start aplikacji."""
    init_db()
    return True


initialize()


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎮 GDIntel")
    st.markdown("*GameDev Intelligence Platform*")
    st.divider()

    page = st.radio(
        "Nawigacja",
        ["📊 Overview", "📈 Trendy", "🎯 Gatunki", "🔄 Przepływy graczy", "🤖 AI Analyst", "⚙️ Dane"],
        label_visibility="collapsed",
    )

    st.divider()

    # Status systemu
    st.markdown("**Status systemu**")
    db_stats = get_db_stats()
    col1, col2 = st.columns(2)
    col1.metric("Gry w DB", f"{db_stats['games']:,}")
    col2.metric("Trendy", db_stats['genre_trends'])

    ai_status = "✅ OK" if settings.has_anthropic_key else "❌ Brak klucza"
    twitch_status = "✅ OK" if settings.has_twitch_keys else "⚠️ Brak"
    st.caption(f"Claude API: {ai_status}")
    st.caption(f"Twitch API: {twitch_status}")

    st.divider()
    st.caption("Dane: SteamSpy + Steam Store")
    st.caption("AI: Claude (Anthropic)")


# ── Dane ─────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=1800)  # cache 30 min
def load_genre_stats():
    return get_genre_stats_df()

@st.cache_data(ttl=1800)
def load_trend_history():
    return get_trend_history_df(days=30)

@st.cache_data(ttl=600)
def load_market_context():
    return get_market_context()


# ── STRONY ───────────────────────────────────────────────────────────────────

# ── 1. OVERVIEW ─────────────────────────────────────────────────────────────
if page == "📊 Overview":
    st.title("📊 Market Overview")
    st.caption("Dane rynku gier indie — Steam + Twitch")

    genre_df = load_genre_stats()

    # KPI Row
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Gier w bazie", f"{db_stats['games']:,}", help="Gry z danymi SteamSpy")
    col2.metric("Gatunków", len(genre_df) if not genre_df.empty else 0)
    col3.metric("Rynek indie", "$4.8B", delta="+8.4% r/r")
    col4.metric("Avg hit rate", "2.4%", delta="-0.7%", delta_color="inverse")
    col5.metric("AI adopcja", "67%", delta="+34% r/r")

    st.divider()

    if genre_df.empty:
        st.info("⚠️ Baza danych jest pusta. Pobierz dane w zakładce **⚙️ Dane**. Wykresy pokazują dane demonstracyjne.")

    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.subheader("ROI Score per gatunek")
        if not genre_df.empty:
            fig = px.bar(
                genre_df.head(10),
                x="roi_score", y="genre",
                orientation="h",
                color="roi_score",
                color_continuous_scale=["#1e2d40", "#00d4aa"],
                labels={"roi_score": "ROI Score", "genre": "Gatunek"},
                text=genre_df.head(10)["roi_score"].round(0).astype(int),
            )
            fig.update_layout(
                plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
                font_color="#8892a8", showlegend=False,
                coloraxis_showscale=False,
                yaxis={"categoryorder": "total ascending"},
                height=380,
            )
            fig.update_traces(textposition="outside", textfont_color="#d8e0f0")
            st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.subheader("Nasycenie vs Potencjał")
        if not genre_df.empty:
            fig2 = px.scatter(
                genre_df,
                x="game_count", y="roi_score",
                size="avg_revenue",
                color="avg_review",
                hover_name="genre",
                color_continuous_scale="Teal",
                labels={
                    "game_count": "Nasycenie (liczba gier)",
                    "roi_score": "Potencjał ROI",
                    "avg_review": "Avg review %",
                },
                size_max=40,
            )
            fig2.update_layout(
                plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
                font_color="#8892a8", height=380,
            )
            st.plotly_chart(fig2, use_container_width=True)

    # Top gry
    st.subheader("Top 10 gier wg szacowanego przychodu")
    top_df = get_top_games_df(limit=10)
    if not top_df.empty:
        display_df = top_df[["name", "owners_mid", "price_usd", "review_score", "estimated_revenue", "playtime_h"]].copy()
        display_df.columns = ["Gra", "Właściciele", "Cena ($)", "Review (%)", "Est. Przychód ($)", "Avg Czas Gry (h)"]
        display_df["Właściciele"] = display_df["Właściciele"].apply(lambda x: f"{x:,}")
        display_df["Est. Przychód ($)"] = display_df["Est. Przychód ($)"].apply(lambda x: f"${x:,.0f}")
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("Brak danych o grach. Pobierz dane w **⚙️ Dane**.")


# ── 2. TRENDY ───────────────────────────────────────────────────────────────
elif page == "📈 Trendy":
    st.title("📈 Analiza trendów")

    trend_df = load_trend_history()
    genre_df = load_genre_stats()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Trend właścicieli — 30 dni")
        if not trend_df.empty:
            fig = px.line(
                trend_df, x="recorded_at", y="avg_owners", color="genre",
                labels={"recorded_at": "Data", "avg_owners": "Avg właściciele", "genre": "Gatunek"},
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            fig.update_layout(
                plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
                font_color="#8892a8", height=340,
            )
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Avg Review Score per gatunek")
        if not genre_df.empty:
            fig2 = px.bar(
                genre_df.sort_values("avg_review", ascending=False).head(8),
                x="genre", y="avg_review",
                color="avg_review",
                color_continuous_scale=["#ef233c", "#ffd166", "#00d4aa"],
                labels={"genre": "Gatunek", "avg_review": "Review Score (%)"},
                range_color=[60, 90],
            )
            fig2.update_layout(
                plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
                font_color="#8892a8", height=340, coloraxis_showscale=False,
            )
            st.plotly_chart(fig2, use_container_width=True)

    # Sezonowość
    st.subheader("Sezonowość sprzedaży Steam — heatmapa")
    st.caption("Relatywna sprzedaż per miesiąc (dane historyczne Steam)")

    months = ["Sty", "Lut", "Mar", "Kwi", "Maj", "Cze", "Lip", "Sie", "Wrz", "Paź", "Lis", "Gru"]
    genres_heat = ["Roguelite", "Cozy", "Survival", "Horror", "Puzzle"]
    # Przykładowe dane sezonowości (w produkcji: z bazy)
    import numpy as np
    heat_data = np.array([
        [60, 55, 62, 70, 75, 72, 68, 73, 80, 90, 95, 88],
        [55, 52, 60, 68, 72, 70, 65, 70, 76, 85, 92, 85],
        [50, 48, 55, 62, 68, 65, 62, 67, 74, 82, 90, 80],
        [45, 42, 48, 55, 62, 58, 56, 62, 70, 78, 86, 76],
        [42, 38, 44, 52, 58, 55, 52, 58, 65, 74, 82, 72],
    ])

    fig3 = px.imshow(
        heat_data,
        labels=dict(x="Miesiąc", y="Gatunek", color="Relatywna sprzedaż"),
        x=months, y=genres_heat,
        color_continuous_scale="Teal",
        aspect="auto",
    )
    fig3.update_layout(
        plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
        font_color="#8892a8", height=280,
    )
    st.plotly_chart(fig3, use_container_width=True)


# ── 3. GATUNKI ──────────────────────────────────────────────────────────────
elif page == "🎯 Gatunki":
    st.title("🎯 Analiza gatunków")

    genre_df = load_genre_stats()

    # Filtr gatunku
    if not genre_df.empty:
        selected_genre = st.selectbox(
            "Wybierz gatunek do analizy",
            ["Wszystkie"] + genre_df["genre"].tolist(),
        )
    else:
        selected_genre = "Wszystkie"

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Szacowany przychód vs Cena")
        if not genre_df.empty:
            fig = px.scatter(
                genre_df,
                x="avg_price", y="avg_revenue",
                size="game_count", color="roi_score",
                hover_name="genre",
                text="genre",
                color_continuous_scale="Teal",
                labels={
                    "avg_price": "Średnia cena ($)",
                    "avg_revenue": "Avg przychód ($)",
                    "roi_score": "ROI Score",
                },
                size_max=50,
            )
            fig.update_traces(textposition="top center", textfont_size=10)
            fig.update_layout(
                plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
                font_color="#8892a8", height=380,
            )
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Retencja — Avg czas gry (h)")
        if not genre_df.empty:
            fig2 = go.Figure(go.Bar(
                x=genre_df.sort_values("avg_playtime_h", ascending=False)["genre"],
                y=genre_df.sort_values("avg_playtime_h", ascending=False)["avg_playtime_h"],
                marker_color="#00d4aa",
                text=genre_df.sort_values("avg_playtime_h", ascending=False)["avg_playtime_h"].round(1),
                textposition="outside",
            ))
            fig2.update_layout(
                plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
                font_color="#8892a8", height=380,
                xaxis_title="Gatunek", yaxis_title="Avg czas gry (h)",
            )
            st.plotly_chart(fig2, use_container_width=True)

    # Tabela rankingowa
    st.subheader("Ranking gatunków — pełne dane")
    if not genre_df.empty:
        display = genre_df.copy()
        display["avg_revenue"] = display["avg_revenue"].apply(lambda x: f"${x:,.0f}")
        display["avg_owners"] = display["avg_owners"].apply(lambda x: f"{x:,}")
        display["avg_review"] = display["avg_review"].apply(lambda x: f"{x:.0f}%")
        display["avg_price"] = display["avg_price"].apply(lambda x: f"${x:.2f}")
        display["roi_score"] = display["roi_score"].apply(lambda x: f"{x:.0f}")
        display.columns = ["Gatunek", "Liczba gier", "Avg właściciele", "Avg przychód", "Total przychód", "Avg review", "Avg czas (h)", "Avg cena", "ROI Score"]
        st.dataframe(display[["Gatunek", "Liczba gier", "Avg właściciele", "Avg przychód", "Avg review", "Avg cena", "ROI Score"]], use_container_width=True, hide_index=True)


# ── 4. PRZEPŁYWY GRACZY ─────────────────────────────────────────────────────
elif page == "🔄 Przepływy graczy":
    st.title("🔄 Przepływy graczy")
    st.caption("Skąd i dokąd migrują gracze po porzuceniu gry")

    # Sankey diagram — przepływy
    st.subheader("Mapa migracji gatunków")

    # W produkcji: dane z bazy/ankiet/analizy recenzji
    # Prototyp: dane statyczne
    labels = ["Roguelite", "Horror", "Puzzle", "Platformer", "Survival", "Cozy", "Idle", "Visual Novel"]
    source = [0, 0, 1, 1, 2, 2, 3, 3]
    target = [4, 5, 4, 6, 5, 7, 5, 7]
    value  = [420, 280, 190, 120, 150, 95, 180, 110]
    colors = ["#00d4aa", "#06d6a0", "#4d9fff", "#9b5de5", "#ff6b35", "#ffd166", "#ef233c", "#8892a8"]

    fig_sankey = go.Figure(go.Sankey(
        node=dict(
            pad=15, thickness=25,
            label=labels,
            color=colors,
            line=dict(color="#0d1117", width=0.5),
        ),
        link=dict(
            source=source, target=target, value=value,
            color=["rgba(0,212,170,0.3)", "rgba(0,212,170,0.2)",
                   "rgba(77,159,255,0.3)", "rgba(77,159,255,0.2)",
                   "rgba(6,214,160,0.3)", "rgba(6,214,160,0.2)",
                   "rgba(255,107,53,0.3)", "rgba(255,107,53,0.2)"],
        ),
    ))
    fig_sankey.update_layout(
        paper_bgcolor="#0d1117", font_color="#8892a8",
        height=420,
        title_text="Przepływ graczy między gatunkami (tys. graczy)",
        title_font_color="#d8e0f0",
    )
    st.plotly_chart(fig_sankey, use_container_width=True)

    # Retencja 30/90/180 dni
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Retencja graczy (30 / 90 / 180 dni)")
        ret_data = pd.DataFrame({
            "Gatunek": ["Roguelite", "Cozy", "Survival", "Horror", "Idle"],
            "30 dni": [68, 75, 70, 45, 80],
            "90 dni": [42, 58, 52, 28, 65],
            "180 dni": [28, 45, 38, 18, 55],
        })
        fig_ret = px.bar(
            ret_data.melt(id_vars="Gatunek", var_name="Okres", value_name="Retencja (%)"),
            x="Gatunek", y="Retencja (%)", color="Okres",
            barmode="group",
            color_discrete_sequence=["#00d4aa", "#4d9fff", "#ff6b35"],
        )
        fig_ret.update_layout(
            plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
            font_color="#8892a8", height=320,
        )
        st.plotly_chart(fig_ret, use_container_width=True)

    with col2:
        st.subheader("Kanały pozyskania graczy")
        acq_data = pd.DataFrame({
            "Kanał": ["TikTok/Reels", "Steam organiczny", "Reddit/Discord", "YouTube", "Influencerzy", "Prasa"],
            "Udział (%)": [34, 28, 16, 12, 6, 4],
        })
        fig_acq = px.pie(
            acq_data, names="Kanał", values="Udział (%)",
            color_discrete_sequence=px.colors.qualitative.Set2,
            hole=0.4,
        )
        fig_acq.update_layout(
            paper_bgcolor="#0d1117", font_color="#8892a8", height=320,
        )
        st.plotly_chart(fig_acq, use_container_width=True)


# ── 5. AI ANALYST ───────────────────────────────────────────────────────────
elif page == "🤖 AI Analyst":
    st.title("🤖 AI Analyst")
    st.caption("Powered by Claude — zadaj pytanie o rynek gamedev")

    if not settings.has_anthropic_key:
        st.error("⚠️ Brak ANTHROPIC_API_KEY w pliku .env. Dodaj klucz i zrestartuj aplikację.")
        st.code('ANTHROPIC_API_KEY=sk-ant-...')
        st.stop()

    market_ctx = load_market_context()

    # Szybkie pytania
    st.markdown("**Szybkie analizy:**")
    q_cols = st.columns(4)
    quick_questions = [
        "Który gatunek ma najlepszy ROI dla solo deva w 2025?",
        "Kiedy najlepiej wydać grę indie na Steam?",
        "Jak AI obniża koszty produkcji gier?",
        "Jakie są red flags przy wyborze gatunku?",
    ]

    for i, (col, q) in enumerate(zip(q_cols, quick_questions)):
        if col.button(q[:30] + "...", key=f"qq_{i}", use_container_width=True):
            st.session_state.setdefault("messages", [])
            st.session_state.messages.append({"role": "user", "content": q})

    st.divider()

    # Inicjalizacja historii czatu
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": (
                    "Cześć! Jestem GDIntel AI — analitykiem rynku gier indie. "
                    f"Mam dostęp do danych {market_ctx.get('total_games', 0):,} gier z bazy. "
                    "Zapytaj mnie o trendy, ROI gatunków, timing premiery lub strategię marketingową."
                ),
            }
        ]

    # Wyświetl historię
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🎮" if msg["role"] == "assistant" else "👤"):
            st.markdown(msg["content"])

    # Input
    if prompt := st.chat_input("Zapytaj o rynek gamedev..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)

        with st.chat_message("assistant", avatar="🎮"):
            # Historia czatu (bez pierwszej wiadomości systemowej)
            history = [
                m for m in st.session_state.messages[1:-1]
                if m["role"] in ("user", "assistant")
            ]

            response = st.write_stream(
                stream_analysis(prompt, history, market_ctx)
            )

        st.session_state.messages.append({"role": "assistant", "content": response})

    # Weekly report
    st.divider()
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("📄 Generuj Weekly Report", use_container_width=True):
            with st.spinner("Generuję raport tygodniowy..."):
                report = get_weekly_market_summary(market_ctx)
            st.markdown(report)


# ── 6. DANE ─────────────────────────────────────────────────────────────────
elif page == "⚙️ Dane":
    st.title("⚙️ Zarządzanie danymi")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Pobierz dane Steam")
        st.caption("SteamSpy API — publiczne, bez klucza. Throttle: 1 req/s.")

        selected_genres = st.multiselect(
            "Gatunki do pobrania",
            options=list(__import__("scrapers.steam", fromlist=["GENRE_TO_TAG"]).GENRE_TO_TAG.keys()),
            default=["Roguelite", "Cozy", "Survival", "Horror"],
        )
        pages_per_genre = st.slider("Stron per gatunek (×50 gier)", 1, 5, 1)

        if st.button("🔄 Pobierz dane Steam", use_container_width=True):
            from scrapers.steam import fetch_genre_data
            from db.models import Game

            progress = st.progress(0)
            status = st.empty()

            with get_session() as db:
                total_saved = 0
                for i, genre in enumerate(selected_genres):
                    status.text(f"Pobieranie: {genre}...")
                    try:
                        games = fetch_genre_data(genre, pages=pages_per_genre)
                        for g_data in games:
                            # Upsert (update or insert)
                            existing = db.query(Game).filter_by(app_id=g_data["app_id"]).first()
                            if existing:
                                for k, v in g_data.items():
                                    if hasattr(existing, k):
                                        setattr(existing, k, v)
                            else:
                                game = Game(
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
                                )
                                db.add(game)
                            total_saved += 1

                        status.text(f"✓ {genre}: {len(games)} gier")
                    except Exception as e:
                        status.text(f"✗ {genre}: {e}")

                    progress.progress((i + 1) / len(selected_genres))

            st.success(f"✅ Zapisano {total_saved} gier w bazie danych!")
            st.cache_data.clear()
            st.rerun()

    with col2:
        st.subheader("Status bazy danych")
        stats = get_db_stats()
        st.metric("Gier", f"{stats['games']:,}")
        st.metric("Rekordów trendów", stats['genre_trends'])
        st.metric("Raportów AI (cache)", stats['ai_reports'])

        st.divider()
        st.subheader("Wyczyść cache")
        if st.button("🗑️ Wyczyść cache Streamlit", use_container_width=True):
            st.cache_data.clear()
            st.success("Cache wyczyszczony!")

        st.divider()
        st.subheader("Konfiguracja (.env)")
        config_data = {
            "Claude API": "✅ Skonfigurowany" if settings.has_anthropic_key else "❌ Brak klucza",
            "Twitch API": "✅ Skonfigurowany" if settings.has_twitch_keys else "⚠️ Opcjonalny",
            "Baza danych": settings.database_url.split("///")[0],
            "Środowisko": settings.app_env,
            "Cache TTL": f"{settings.cache_ttl_seconds}s",
        }
        for k, v in config_data.items():
            st.text(f"{k}: {v}")
