"""
app.py — DropRate Dashboard
"""
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from config import settings
from db.database import init_db, get_db_stats, get_session
from utils.data_processor import (
    get_genre_stats_df,
    get_trend_history_df,
    get_top_games_df,
    get_market_context,
    _classify_genre,
)
from ai.analyst import stream_analysis, get_weekly_market_summary

st.set_page_config(
    page_title="DropRate — GameDev Intelligence",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif !important;
    background-color: #0f1117 !important;
    color: #e2e8f0 !important;
}
.stApp { background-color: #0f1117 !important; }
#MainMenu, footer { visibility: hidden; }
section[data-testid="stSidebar"] { display: none !important; }
.block-container { padding: 24px 40px 60px !important; max-width: 1400px !important; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    background: #1e2130 !important;
    border-radius: 12px !important;
    padding: 4px !important;
    gap: 2px !important;
    border: 1px solid #2d3348 !important;
    margin-bottom: 24px !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: #94a3b8 !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 8px 18px !important;
    font-size: 13px !important;
    font-weight: 500 !important;
}
.stTabs [aria-selected="true"] {
    background: #6366f1 !important;
    color: #ffffff !important;
    font-weight: 600 !important;
}
.stTabs [data-baseweb="tab-panel"] { padding-top: 8px !important; }

/* Metrics */
[data-testid="metric-container"] {
    background: #1e2130 !important;
    border: 1px solid #2d3348 !important;
    border-radius: 12px !important;
    padding: 16px 20px !important;
}
[data-testid="stMetricValue"] { color: #f1f5f9 !important; font-weight: 700 !important; }
[data-testid="stMetricLabel"] { color: #64748b !important; font-size: 12px !important; }

/* Buttons */
.stButton button {
    background: #6366f1 !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    padding: 10px 20px !important;
}
.stButton button:hover { background: #4f46e5 !important; }

/* Dataframe */
.stDataFrame { border-radius: 10px !important; overflow: hidden !important; }

/* Inputs */
.stMultiSelect [data-baseweb="select"] > div { background: #1e2130 !important; border-color: #2d3348 !important; }
.stSelectbox [data-baseweb="select"] > div { background: #1e2130 !important; border-color: #2d3348 !important; }

/* Progress */
.stProgress > div > div > div { background: #6366f1 !important; }

/* Chat */
.stChatMessage { background: #1e2130 !important; border: 1px solid #2d3348 !important; border-radius: 12px !important; }
</style>
""", unsafe_allow_html=True)

# ── Init ─────────────────────────────────────────────────────────────────────
@st.cache_resource
def initialize():
    init_db()
    return True
initialize()

# ── Header ───────────────────────────────────────────────────────────────────
col_logo, col_status = st.columns([6, 1])
with col_logo:
    st.markdown("## 🎮 **Drop**Rate")
with col_status:
    db_stats = get_db_stats()
    st.markdown(f"<div style='text-align:right;padding-top:12px;font-size:12px;color:#64748b'>● LIVE &nbsp;|&nbsp; {db_stats['games']:,} gier</div>", unsafe_allow_html=True)

st.divider()

# ── Cache ─────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=1800)
def load_genre_stats(): return get_genre_stats_df()
@st.cache_data(ttl=1800)
def load_trend_history(): return get_trend_history_df(days=30)
@st.cache_data(ttl=1800)
def load_top_games(): return get_top_games_df(limit=10)
@st.cache_data(ttl=600)
def load_market_context(): return get_market_context()

genre_df = load_genre_stats()
trend_df = load_trend_history()
top_df   = load_top_games()

# ── Plotly config ─────────────────────────────────────────────────────────────
BG = "rgba(0,0,0,0)"
FONT = dict(family="Inter", color="#94a3b8", size=12)
GRID = "#1e2130"
COLORS = ["#6366f1","#8b5cf6","#06b6d4","#10b981","#f59e0b","#ef4444","#ec4899","#84cc16"]

def dark_layout(**kw):
    return dict(paper_bgcolor=BG, plot_bgcolor=BG, font=FONT,
        margin=dict(t=10,b=30,l=40,r=10),
        xaxis=dict(gridcolor=GRID, linecolor=GRID),
        yaxis=dict(gridcolor=GRID, linecolor=GRID), **kw)

# ── TABS ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Overview", "📈 Trendy", "🎯 Gatunki",
    "🔄 Przepływy graczy", "🤖 AI Analyst", "⚙️ Dane"
])

# ═══════════════ TAB 1 — OVERVIEW ════════════════════════════════════════════
with tab1:
    st.markdown("### Market Overview")
    st.caption("Dane rynku gier indie — Steam · SteamSpy · AI")
    st.write("")

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Gier w bazie", f"{db_stats['games']:,}")
    c2.metric("Gatunków", len(genre_df) if not genre_df.empty else 0)
    c3.metric("Rynek indie", "$4.8B", delta="+8.4% r/r")
    c4.metric("Avg hit rate", "2.4%", delta="-0.7%", delta_color="inverse")
    c5.metric("AI adopcja", "67%", delta="+34% r/r")

    st.write("")

    col_l, col_r = st.columns([3,2], gap="large")

    with col_l:
        st.markdown("**ROI Score per gatunek**")
        if not genre_df.empty:
            fig = px.bar(genre_df.head(8), x="roi_score", y="genre",
                orientation="h", color="roi_score",
                color_continuous_scale=[[0,"#312e81"],[1,"#6366f1"]],
                text=genre_df.head(8)["roi_score"].round(0).astype(int))
            fig.update_layout(**dark_layout(height=320, coloraxis_showscale=False,
                yaxis={"categoryorder":"total ascending","title":""},
                xaxis={"title":"ROI Score"}))
            fig.update_traces(textposition="outside", textfont_color="#e2e8f0", marker_line_width=0)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Brak danych. Zaktualizuj w zakładce ⚙️ Dane.")

    with col_r:
        st.markdown("**Podział platform 2025**")
        fig2 = go.Figure(go.Pie(
            labels=["Mobile","PC","Console","VR/AR","Cloud"],
            values=[48,24,28,2,3], hole=0.55,
            marker_colors=COLORS))
        fig2.update_layout(paper_bgcolor=BG, font=FONT, height=320,
            margin=dict(t=10,b=10,l=10,r=10),
            legend=dict(font=dict(size=11,color="#94a3b8")))
        fig2.update_traces(textinfo="percent", textfont_size=11)
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("**Top 10 gier wg szacowanego przychodu**")
    if not top_df.empty:
        disp = top_df[["name","genre","owners_mid","price_usd","review_score","estimated_revenue"]].copy()
        disp.columns = ["Gra","Gatunek","Właściciele","Cena ($)","Review (%)","Est. przychód ($)"]
        disp["Właściciele"] = disp["Właściciele"].apply(lambda x: f"{x:,}")
        disp["Est. przychód ($)"] = disp["Est. przychód ($)"].apply(lambda x: f"${x:,.0f}")
        disp["Review (%)"] = disp["Review (%)"].apply(lambda x: f"{x:.0f}%")
        disp["Cena ($)"] = disp["Cena ($)"].apply(lambda x: f"${x:.2f}")
        st.dataframe(disp, use_container_width=True, hide_index=True)
    else:
        st.info("Pobierz dane w zakładce ⚙️ Dane.")

# ═══════════════ TAB 2 — TRENDY ══════════════════════════════════════════════
with tab2:
    st.markdown("### Analiza trendów")
    st.caption("Zmiany w czasie — właściciele, przychody, recenzje")
    st.write("")

    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown("**Trend właścicieli — 30 dni**")
        if not trend_df.empty and "recorded_at" in trend_df.columns:
            fig = px.line(trend_df, x="recorded_at", y="avg_owners", color="genre",
                color_discrete_sequence=COLORS)
            fig.update_layout(**dark_layout(height=300))
            fig.update_traces(line_width=2)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Brak danych trendów. Zaktualizuj w ⚙️ Dane.")

    with col2:
        st.markdown("**Avg Review Score per gatunek**")
        if not genre_df.empty:
            fig2 = px.bar(genre_df.sort_values("avg_review", ascending=False).head(8),
                x="genre", y="avg_review", color="avg_review",
                color_continuous_scale=[[0,"#312e81"],[1,"#6366f1"]])
            fig2.update_layout(**dark_layout(height=300, coloraxis_showscale=False,
                xaxis_title="", yaxis_title="Review Score (%)"))
            fig2.update_traces(marker_line_width=0)
            st.plotly_chart(fig2, use_container_width=True)

    st.markdown("**Sezonowość sprzedaży Steam**")
    months = ["Sty","Lut","Mar","Kwi","Maj","Cze","Lip","Sie","Wrz","Paź","Lis","Gru"]
    genres_h = ["Roguelite","Cozy","Survival","Horror","Puzzle"]
    heat_data = np.array([
        [60,55,62,70,75,72,68,73,80,90,95,88],
        [55,52,60,68,72,70,65,70,76,85,92,85],
        [50,48,55,62,68,65,62,67,74,82,90,80],
        [45,42,48,55,62,58,56,62,70,78,86,76],
        [42,38,44,52,58,55,52,58,65,74,82,72],
    ])
    fig3 = px.imshow(heat_data, labels=dict(x="Miesiąc",y="Gatunek",color="Sprzedaż"),
        x=months, y=genres_h,
        color_continuous_scale=[[0,"#1e1b4b"],[1,"#6366f1"]], aspect="auto")
    fig3.update_layout(**dark_layout(height=240))
    st.plotly_chart(fig3, use_container_width=True)

# ═══════════════ TAB 3 — GATUNKI ═════════════════════════════════════════════
with tab3:
    st.markdown("### Analiza gatunków")
    st.caption("Porównanie ROI, przychodów, cen i retencji")
    st.write("")

    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown("**Przychód vs Cena**")
        if not genre_df.empty:
            fig = px.scatter(genre_df, x="avg_price", y="avg_revenue",
                size="game_count", color="roi_score", hover_name="genre",
                color_continuous_scale=[[0,"#312e81"],[1,"#6366f1"]], size_max=50)
            fig.update_layout(**dark_layout(height=340,
                xaxis_title="Średnia cena ($)", yaxis_title="Avg przychód ($)"))
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("**Retencja — Avg czas gry**")
        if not genre_df.empty:
            srt = genre_df.sort_values("avg_playtime_h", ascending=False)
            fig2 = px.bar(srt, x="genre", y="avg_playtime_h",
                color="avg_playtime_h",
                color_continuous_scale=[[0,"#312e81"],[1,"#6366f1"]],
                text=srt["avg_playtime_h"].round(1))
            fig2.update_layout(**dark_layout(height=340, coloraxis_showscale=False,
                xaxis_title="", yaxis_title="Avg czas gry (h)"))
            fig2.update_traces(textposition="outside", textfont_color="#e2e8f0", marker_line_width=0)
            st.plotly_chart(fig2, use_container_width=True)

    st.markdown("**Ranking gatunków — pełne dane**")
    if not genre_df.empty:
        disp = genre_df.copy()
        disp["avg_revenue"] = disp["avg_revenue"].apply(lambda x: f"${x:,.0f}")
        disp["avg_owners"]  = disp["avg_owners"].apply(lambda x: f"{x:,}")
        disp["avg_review"]  = disp["avg_review"].apply(lambda x: f"{x:.0f}%")
        disp["avg_price"]   = disp["avg_price"].apply(lambda x: f"${x:.2f}")
        disp["roi_score"]   = disp["roi_score"].apply(lambda x: f"{x:.0f}")
        disp = disp[["genre","game_count","avg_owners","avg_revenue","avg_review","avg_price","roi_score"]]
        disp.columns = ["Gatunek","Gier","Avg właściciele","Avg przychód","Avg review","Avg cena","ROI Score"]
        st.dataframe(disp, use_container_width=True, hide_index=True)

# ═══════════════ TAB 4 — PRZEPŁYWY ════════════════════════════════════════════
with tab4:
    st.markdown("### Przepływy graczy")
    st.caption("Skąd i dokąd migrują gracze po porzuceniu gry")
    st.write("")

    labels = ["Roguelite","Horror","Puzzle","Platformer","Survival","Cozy","Idle","Visual Novel"]
    fig_s = go.Figure(go.Sankey(
        node=dict(pad=20, thickness=20, label=labels, color=COLORS[:len(labels)],
            line=dict(color="#2d3348", width=0.5)),
        link=dict(source=[0,0,1,1,2,2,3,3], target=[4,5,4,6,5,7,5,7],
            value=[420,280,190,120,150,95,180,110],
            color=["rgba(99,102,241,0.2)"]*8),
    ))
    fig_s.update_layout(paper_bgcolor=BG, font=dict(family="Inter",size=12,color="#94a3b8"), height=380, margin=dict(t=10,b=10))
    st.plotly_chart(fig_s, use_container_width=True)

    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown("**Retencja (30 / 90 / 180 dni)**")
        ret = pd.DataFrame({"Gatunek":["Roguelite","Cozy","Survival","Horror","Idle"],
            "30 dni":[68,75,70,45,80],"90 dni":[42,58,52,28,65],"180 dni":[28,45,38,18,55]})
        fig_r = px.bar(ret.melt(id_vars="Gatunek",var_name="Okres",value_name="Retencja (%)"),
            x="Gatunek", y="Retencja (%)", color="Okres", barmode="group",
            color_discrete_sequence=["#6366f1","#8b5cf6","#c7d2fe"])
        fig_r.update_layout(**dark_layout(height=300))
        st.plotly_chart(fig_r, use_container_width=True)

    with col2:
        st.markdown("**Kanały pozyskania graczy**")
        acq = pd.DataFrame({"Kanał":["TikTok/Reels","Steam organiczny","Reddit/Discord","YouTube","Influencerzy","Prasa"],
            "Udział (%)": [34,28,16,12,6,4]})
        fig_a = px.pie(acq, names="Kanał", values="Udział (%)", hole=0.55,
            color_discrete_sequence=COLORS)
        fig_a.update_layout(paper_bgcolor=BG, font=FONT, height=300, margin=dict(t=10,b=10))
        fig_a.update_traces(textinfo="percent+label", textfont_size=11)
        st.plotly_chart(fig_a, use_container_width=True)

# ═══════════════ TAB 5 — AI ANALYST ══════════════════════════════════════════
with tab5:
    st.markdown("### AI Analyst")
    st.caption("Powered by Claude — zadaj pytanie o rynek gamedev")
    st.write("")

    if not settings.has_anthropic_key:
        st.error("⚠️ Brak ANTHROPIC_API_KEY. Dodaj klucz w Secrets na Streamlit Cloud.")
        st.stop()

    market_ctx = load_market_context()

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

    st.write("")

    if "messages" not in st.session_state:
        st.session_state.messages = [{
            "role": "assistant",
            "content": (
                f"Cześć! Jestem DropRate AI — analitykiem rynku gier indie. "
                f"Mam dostęp do danych {market_ctx.get('total_games', 0):,} gier z bazy. "
                "Zapytaj mnie o trendy, ROI gatunków, timing premiery lub strategię marketingową."
            ),
        }]

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🎮" if msg["role"] == "assistant" else "👤"):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Zapytaj o rynek gamedev..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)
        with st.chat_message("assistant", avatar="🎮"):
            history = [m for m in st.session_state.messages[1:-1] if m["role"] in ("user","assistant")]
            response = st.write_stream(stream_analysis(prompt, history, market_ctx))
        st.session_state.messages.append({"role": "assistant", "content": response})

    st.divider()
    if st.button("📄 Generuj Weekly Report"):
        with st.spinner("Generuję raport..."):
            report = get_weekly_market_summary(market_ctx)
        st.markdown(report)

# ═══════════════ TAB 6 — DANE ═════════════════════════════════════════════════
with tab6:
    st.markdown("### Zarządzanie danymi")
    st.caption("Aktualizacja danych Steam i konfiguracja")
    st.write("")

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown("**Aktualizuj dane**")
        st.caption("Pobiera dane Steam i automatycznie oblicza trendy gatunków")

        selected_genres = st.multiselect(
            "Gatunki do pobrania",
            options=list(__import__("scrapers.steam", fromlist=["GENRE_TO_TAG"]).GENRE_TO_TAG.keys()),
            default=["Roguelite", "Cozy", "Survival", "Horror"],
        )

        if st.button("🔄 Aktualizuj dane i trendy", use_container_width=True):
            from scrapers.steam import fetch_genre_data
            from db.models import Game, GenreTrend
            from datetime import datetime, timezone

            progress = st.progress(0)
            status = st.empty()
            total_saved = 0
            steps = len(selected_genres) + 1
            genre_buckets = {}

            for i, genre in enumerate(selected_genres):
                status.text(f"[{i+1}/{len(selected_genres)}] Pobieranie: {genre}...")
                try:
                    games = fetch_genre_data(genre, pages=1)
                    for g_data in games:
                        try:
                            with get_session() as db:
                                existing = db.query(Game).filter_by(app_id=g_data["app_id"]).first()
                                if existing:
                                    existing.owners_min = g_data.get("owners_min", 0)
                                    existing.owners_max = g_data.get("owners_max", 0)
                                    existing.positive = g_data.get("positive", 0)
                                    existing.negative = g_data.get("negative", 0)
                                    existing.price_usd = int(g_data.get("price_usd", 0) or 0)
                                else:
                                    db.add(Game(
                                        app_id=g_data["app_id"], name=g_data["name"],
                                        developer=g_data.get("developer",""), publisher=g_data.get("publisher",""),
                                        owners_min=g_data.get("owners_min",0), owners_max=g_data.get("owners_max",0),
                                        players_forever=g_data.get("players_forever",0),
                                        average_playtime=g_data.get("average_playtime",0),
                                        median_playtime=g_data.get("median_playtime",0),
                                        price_usd=int(g_data.get("price_usd",0) or 0),
                                        positive=g_data.get("positive",0), negative=g_data.get("negative",0),
                                        tags=g_data.get("tags",{}),
                                    ))
                                total_saved += 1
                        except Exception:
                            pass
                except Exception as e:
                    status.text(f"✗ {genre}: {e}")
                progress.progress((i + 1) / steps)

            status.text("Obliczam trendy gatunków...")
            try:
                with get_session() as db:
                    db.query(GenreTrend).delete()
                    all_games = db.query(Game).filter(Game.owners_max > 0).all()
                    for game in all_games:
                        g = _classify_genre(game.tags or {})
                        genre_buckets.setdefault(g, []).append(game)
                    now = datetime.now(timezone.utc)
                    for g, gg in genre_buckets.items():
                        owners = [x.owners_mid for x in gg]
                        revenues = [x.estimated_revenue for x in gg]
                        reviews = [x.review_score for x in gg if x.positive + x.negative > 0]
                        db.add(GenreTrend(
                            genre=g, recorded_at=now, game_count=len(gg),
                            avg_owners=int(sum(owners)/len(owners)) if owners else 0,
                            total_owners=sum(owners),
                            avg_revenue=sum(revenues)/len(revenues) if revenues else 0.0,
                            avg_review_score=sum(reviews)/len(reviews) if reviews else 0.0,
                            avg_playtime_h=sum(x.average_playtime/60 for x in gg)/len(gg),
                            avg_price=sum(x.price_usd for x in gg)/len(gg),
                        ))
            except Exception as e:
                st.error(f"Błąd trendów: {e}")

            progress.progress(1.0)
            st.success(f"✅ Gotowe! {total_saved} gier, {len(genre_buckets)} gatunków.")
            st.cache_data.clear()
            st.rerun()

    with col2:
        st.markdown("**Status bazy danych**")
        stats = get_db_stats()
        m1, m2, m3 = st.columns(3)
        m1.metric("Gier", f"{stats['games']:,}")
        m2.metric("Trendy", stats['genre_trends'])
        m3.metric("AI cache", stats['ai_reports'])

        st.divider()
        st.markdown("**Konfiguracja**")
        cfg = {
            "Claude API": "✅ Aktywny" if settings.has_anthropic_key else "❌ Brak klucza",
            "Twitch API": "✅ Aktywny" if settings.has_twitch_keys else "⚠️ Opcjonalny",
            "Środowisko": settings.app_env,
        }
        for k, v in cfg.items():
            st.text(f"{k}: {v}")
