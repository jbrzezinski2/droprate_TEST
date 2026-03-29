"""
app.py — DropRate Dashboard (Streamlit) — Light SaaS UI
"""
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* ── Reset & Base ── */
*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif !important;
    background-color: #f8fafc !important;
    color: #0f172a !important;
}
.stApp { background-color: #f8fafc !important; }

/* ── Hide default elements ── */
#MainMenu, footer, header { visibility: hidden; }
section[data-testid="stSidebar"] { display: none; }
.block-container {
    padding: 0 !important;
    max-width: 100% !important;
}

/* ── Top Navigation Bar ── */
.topbar {
    background: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    padding: 0 40px;
    display: flex;
    align-items: center;
    gap: 0;
    position: sticky;
    top: 0;
    z-index: 999;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.topbar-logo {
    font-size: 20px;
    font-weight: 800;
    color: #0f172a;
    padding: 16px 32px 16px 0;
    border-right: 1px solid #e2e8f0;
    margin-right: 8px;
    letter-spacing: -0.5px;
    white-space: nowrap;
}
.topbar-logo span { color: #6366f1; }

/* ── Page Content ── */
.page-wrap {
    padding: 32px 40px 60px;
    max-width: 1400px;
    margin: 0 auto;
}

/* ── Page Header ── */
.page-header {
    margin-bottom: 28px;
}
.page-title {
    font-size: 28px;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: -0.5px;
    margin-bottom: 4px;
}
.page-sub {
    font-size: 14px;
    color: #64748b;
    font-weight: 400;
}

/* ── KPI Cards ── */
.kpi-row {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 16px;
    margin-bottom: 28px;
}
.kpi-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 20px 22px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    transition: box-shadow 0.2s, transform 0.2s;
}
.kpi-card:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,0.08);
    transform: translateY(-2px);
}
.kpi-label {
    font-size: 12px;
    font-weight: 500;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 8px;
}
.kpi-value {
    font-size: 26px;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: -0.5px;
    margin-bottom: 4px;
}
.kpi-delta-up { font-size: 12px; color: #10b981; font-weight: 500; }
.kpi-delta-down { font-size: 12px; color: #ef4444; font-weight: 500; }
.kpi-delta-neutral { font-size: 12px; color: #94a3b8; font-weight: 500; }

/* ── Section Cards ── */
.card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
    padding: 24px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    margin-bottom: 20px;
}
.card-title {
    font-size: 15px;
    font-weight: 700;
    color: #0f172a;
    margin-bottom: 4px;
    letter-spacing: -0.2px;
}
.card-sub {
    font-size: 12px;
    color: #94a3b8;
    margin-bottom: 18px;
}

/* ── Tab Navigation ── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    gap: 4px !important;
    border-bottom: 2px solid #e2e8f0 !important;
    padding-bottom: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    border: none !important;
    color: #64748b !important;
    font-weight: 500 !important;
    font-size: 14px !important;
    padding: 10px 18px !important;
    border-radius: 0 !important;
    border-bottom: 2px solid transparent !important;
    margin-bottom: -2px !important;
}
.stTabs [aria-selected="true"] {
    color: #6366f1 !important;
    border-bottom: 2px solid #6366f1 !important;
    font-weight: 600 !important;
}
.stTabs [data-baseweb="tab-panel"] {
    padding-top: 24px !important;
}

/* ── Buttons ── */
.stButton button {
    background: #6366f1 !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    padding: 10px 20px !important;
    transition: all 0.2s !important;
    box-shadow: 0 2px 8px rgba(99,102,241,0.25) !important;
}
.stButton button:hover {
    background: #4f46e5 !important;
    box-shadow: 0 4px 16px rgba(99,102,241,0.35) !important;
    transform: translateY(-1px) !important;
}

/* ── Metrics ── */
[data-testid="metric-container"] {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 12px !important;
    padding: 16px 20px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
}
[data-testid="stMetricValue"] {
    font-size: 24px !important;
    font-weight: 800 !important;
    color: #0f172a !important;
}
[data-testid="stMetricLabel"] {
    font-size: 12px !important;
    color: #94a3b8 !important;
    font-weight: 500 !important;
}

/* ── Dataframe ── */
.stDataFrame {
    border: 1px solid #e2e8f0 !important;
    border-radius: 12px !important;
    overflow: hidden !important;
}

/* ── Select & Input ── */
.stSelectbox > div > div,
.stMultiSelect > div > div {
    border-radius: 8px !important;
    border-color: #e2e8f0 !important;
    background: #ffffff !important;
}

/* ── Divider ── */
hr { border-color: #e2e8f0 !important; }

/* ── Alert/Info boxes ── */
.stAlert {
    border-radius: 10px !important;
}

/* ── Chat ── */
.stChatMessage {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 12px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
}
.stChatInputContainer {
    border-top: 1px solid #e2e8f0 !important;
    background: #ffffff !important;
    border-radius: 12px !important;
}

/* ── Badge ── */
.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.04em;
}
.badge-green { background: #d1fae5; color: #065f46; }
.badge-blue  { background: #dbeafe; color: #1e40af; }
.badge-red   { background: #fee2e2; color: #991b1b; }
.badge-purple{ background: #ede9fe; color: #5b21b6; }

/* ── Spinner ── */
.stSpinner > div { border-top-color: #6366f1 !important; }

/* ── Progress bar ── */
.stProgress > div > div > div {
    background: #6366f1 !important;
    border-radius: 4px !important;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #f1f5f9; }
::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }

/* ── Status dot ── */
.status-dot {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #10b981;
    box-shadow: 0 0 0 3px rgba(16,185,129,0.2);
    animation: pulse 2s infinite;
    margin-right: 6px;
}
@keyframes pulse { 0%,100%{opacity:1;} 50%{opacity:0.5;} }
</style>
""", unsafe_allow_html=True)

# ── Init ─────────────────────────────────────────────────────────────────────
@st.cache_resource
def initialize():
    init_db()
    return True

initialize()

# ── Top Bar ──────────────────────────────────────────────────────────────────
db_stats = get_db_stats()

st.markdown(f"""
<div class="topbar">
    <div class="topbar-logo">Drop<span>Rate</span></div>
</div>
""", unsafe_allow_html=True)

# ── Main Content ─────────────────────────────────────────────────────────────
st.markdown('<div class="page-wrap">', unsafe_allow_html=True)

# ── Cache helpers ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=1800)
def load_genre_stats():
    return get_genre_stats_df()

@st.cache_data(ttl=1800)
def load_trend_history():
    return get_trend_history_df(days=30)

@st.cache_data(ttl=1800)
def load_top_games():
    return get_top_games_df(limit=10)

@st.cache_data(ttl=600)
def load_market_context():
    return get_market_context()

# ── Plotly theme ──────────────────────────────────────────────────────────────
PLOT_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter", color="#64748b", size=12),
    margin=dict(t=20, b=40, l=40, r=20),
    xaxis=dict(gridcolor="#f1f5f9", linecolor="#e2e8f0"),
    yaxis=dict(gridcolor="#f1f5f9", linecolor="#e2e8f0"),
)
COLORS = ["#6366f1","#8b5cf6","#06b6d4","#10b981","#f59e0b","#ef4444","#ec4899","#84cc16"]

genre_df  = load_genre_stats()
trend_df  = load_trend_history()
top_df    = load_top_games()

# ── TABS ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Overview",
    "📈 Trendy",
    "🎯 Gatunki",
    "🔄 Przepływy graczy",
    "🤖 AI Analyst",
    "⚙️ Dane",
])

# ════════════════════════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ════════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("""
    <div class="page-header">
        <div class="page-title">Market Overview</div>
        <div class="page-sub"><span class="status-dot"></span>Dane rynku gier indie — Steam · SteamSpy · AI</div>
    </div>
    """, unsafe_allow_html=True)

    # KPI Row
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Gier w bazie", f"{db_stats['games']:,}", help="Gry z danymi SteamSpy")
    c2.metric("Gatunków", len(genre_df) if not genre_df.empty else 0)
    c3.metric("Rynek indie", "$4.8B", delta="+8.4% r/r")
    c4.metric("Avg hit rate", "2.4%", delta="-0.7%", delta_color="inverse")
    c5.metric("AI adopcja", "67%", delta="+34% r/r")

    st.write("")

    # Charts row
    col_l, col_r = st.columns([3, 2], gap="large")

    with col_l:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">ROI Score per gatunek</div>', unsafe_allow_html=True)
        st.markdown('<div class="card-sub">Composite score: przychód, recenzje, czas dev, nasycenie</div>', unsafe_allow_html=True)
        if not genre_df.empty:
            fig = px.bar(
                genre_df.head(8),
                x="roi_score", y="genre",
                orientation="h",
                color="roi_score",
                color_continuous_scale=[[0,"#c7d2fe"],[1,"#6366f1"]],
                text=genre_df.head(8)["roi_score"].round(0).astype(int),
            )
            fig.update_layout(**PLOT_LAYOUT, height=320, coloraxis_showscale=False,
                yaxis={"categoryorder":"total ascending","title":""},
                xaxis={"title":"ROI Score"})
            fig.update_traces(textposition="outside", marker_line_width=0)
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col_r:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Podział platform 2025</div>', unsafe_allow_html=True)
        st.markdown('<div class="card-sub">Globalny rynek gier wg platformy</div>', unsafe_allow_html=True)
        fig2 = go.Figure(go.Pie(
            labels=["Mobile","PC","Console","VR/AR","Cloud"],
            values=[48,24,28,2,3],
            hole=0.6,
            marker_colors=COLORS,
        ))
        fig2.update_layout(**PLOT_LAYOUT, height=220,
            showlegend=True,
            legend=dict(orientation="v", x=1.0, y=0.5, font=dict(size=11)))
        fig2.update_traces(textinfo="percent", textfont_size=11)
        st.plotly_chart(fig2, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Top games table
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">Top 10 gier wg szacowanego przychodu</div>', unsafe_allow_html=True)
    st.markdown('<div class="card-sub">Dane: SteamSpy — szacunki na podstawie liczby właścicieli</div>', unsafe_allow_html=True)
    if not top_df.empty:
        display = top_df[["name","genre","owners_mid","price_usd","review_score","estimated_revenue"]].copy()
        display.columns = ["Gra","Gatunek","Właściciele","Cena ($)","Review (%)","Est. przychód ($)"]
        display["Właściciele"] = display["Właściciele"].apply(lambda x: f"{x:,}")
        display["Est. przychód ($)"] = display["Est. przychód ($)"].apply(lambda x: f"${x:,.0f}")
        display["Review (%)"] = display["Review (%)"].apply(lambda x: f"{x:.0f}%")
        display["Cena ($)"] = display["Cena ($)"].apply(lambda x: f"${x:.2f}")
        st.dataframe(display, use_container_width=True, hide_index=True)
    else:
        st.info("Pobierz dane w zakładce **⚙️ Dane**.")
    st.markdown('</div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════════
# TAB 2 — TRENDY
# ════════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown('<div class="page-header"><div class="page-title">Analiza trendów</div><div class="page-sub">Zmiany w czasie — właściciele, przychody, recenzje</div></div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Trend właścicieli — 30 dni</div>', unsafe_allow_html=True)
        st.markdown('<div class="card-sub">Średnia liczba właścicieli per gatunek</div>', unsafe_allow_html=True)
        if not trend_df.empty and "recorded_at" in trend_df.columns:
            fig = px.line(trend_df, x="recorded_at", y="avg_owners", color="genre",
                color_discrete_sequence=COLORS)
            fig.update_layout(**PLOT_LAYOUT, height=300)
            fig.update_traces(line_width=2)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Brak danych trendów. Zaktualizuj dane w zakładce ⚙️.")
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Avg Review Score per gatunek</div>', unsafe_allow_html=True)
        st.markdown('<div class="card-sub">Im wyższy, tym lepszy odbiór przez graczy</div>', unsafe_allow_html=True)
        if not genre_df.empty:
            fig2 = px.bar(
                genre_df.sort_values("avg_review", ascending=False).head(8),
                x="genre", y="avg_review",
                color="avg_review",
                color_continuous_scale=[[0,"#dbeafe"],[1,"#6366f1"]],
            )
            fig2.update_layout(**PLOT_LAYOUT, height=300, coloraxis_showscale=False,
                xaxis_title="", yaxis_title="Review Score (%)")
            fig2.update_traces(marker_line_width=0)
            st.plotly_chart(fig2, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Heatmap sezonowości
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">Sezonowość sprzedaży Steam</div>', unsafe_allow_html=True)
    st.markdown('<div class="card-sub">Relatywna sprzedaż per miesiąc — Q4 dominuje (Halloween, Winter Sale)</div>', unsafe_allow_html=True)
    import numpy as np
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
        color_continuous_scale=[[0,"#ede9fe"],[1,"#6366f1"]], aspect="auto")
    fig3.update_layout(**PLOT_LAYOUT, height=240)
    st.plotly_chart(fig3, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════════
# TAB 3 — GATUNKI
# ════════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown('<div class="page-header"><div class="page-title">Analiza gatunków</div><div class="page-sub">Porównanie ROI, przychodów, cen i retencji</div></div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Przychód vs Cena</div>', unsafe_allow_html=True)
        st.markdown('<div class="card-sub">Rozmiar bańki = liczba gier w gatunku</div>', unsafe_allow_html=True)
        if not genre_df.empty:
            fig = px.scatter(genre_df, x="avg_price", y="avg_revenue",
                size="game_count", color="roi_score",
                hover_name="genre",
                color_continuous_scale=[[0,"#c7d2fe"],[1,"#6366f1"]],
                size_max=50)
            fig.update_layout(**PLOT_LAYOUT, height=340,
                xaxis_title="Średnia cena ($)", yaxis_title="Avg przychód ($)")
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Retencja — Avg czas gry</div>', unsafe_allow_html=True)
        st.markdown('<div class="card-sub">Dłuższy czas = lepsza retencja graczy</div>', unsafe_allow_html=True)
        if not genre_df.empty:
            fig2 = px.bar(
                genre_df.sort_values("avg_playtime_h", ascending=False),
                x="genre", y="avg_playtime_h",
                color="avg_playtime_h",
                color_continuous_scale=[[0,"#dbeafe"],[1,"#6366f1"]],
                text=genre_df.sort_values("avg_playtime_h", ascending=False)["avg_playtime_h"].round(1),
            )
            fig2.update_layout(**PLOT_LAYOUT, height=340, coloraxis_showscale=False,
                xaxis_title="", yaxis_title="Avg czas gry (h)")
            fig2.update_traces(textposition="outside", marker_line_width=0)
            st.plotly_chart(fig2, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Tabela rankingowa
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">Ranking gatunków — pełne dane</div>', unsafe_allow_html=True)
    st.markdown('<div class="card-sub">Sortowanie wg ROI Score (composite)</div>', unsafe_allow_html=True)
    if not genre_df.empty:
        disp = genre_df.copy()
        disp["avg_revenue"] = disp["avg_revenue"].apply(lambda x: f"${x:,.0f}")
        disp["avg_owners"] = disp["avg_owners"].apply(lambda x: f"{x:,}")
        disp["avg_review"] = disp["avg_review"].apply(lambda x: f"{x:.0f}%")
        disp["avg_price"] = disp["avg_price"].apply(lambda x: f"${x:.2f}")
        disp["roi_score"] = disp["roi_score"].apply(lambda x: f"{x:.0f}")
        disp = disp[["genre","game_count","avg_owners","avg_revenue","avg_review","avg_price","roi_score"]]
        disp.columns = ["Gatunek","Gier","Avg właściciele","Avg przychód","Avg review","Avg cena","ROI Score"]
        st.dataframe(disp, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════════
# TAB 4 — PRZEPŁYWY GRACZY
# ════════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown('<div class="page-header"><div class="page-title">Przepływy graczy</div><div class="page-sub">Skąd i dokąd migrują gracze po porzuceniu gry</div></div>', unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">Mapa migracji gatunków</div>', unsafe_allow_html=True)
    st.markdown('<div class="card-sub">Przepływ graczy między gatunkami (tys. graczy szacunkowo)</div>', unsafe_allow_html=True)
    labels = ["Roguelite","Horror","Puzzle","Platformer","Survival","Cozy","Idle","Visual Novel"]
    fig_s = go.Figure(go.Sankey(
        node=dict(pad=20, thickness=20, label=labels,
            color=COLORS[:len(labels)],
            line=dict(color="#e2e8f0", width=0.5)),
        link=dict(
            source=[0,0,1,1,2,2,3,3],
            target=[4,5,4,6,5,7,5,7],
            value=[420,280,190,120,150,95,180,110],
            color=["rgba(99,102,241,0.15)"]*8,
        ),
    ))
    fig_s.update_layout(paper_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter", size=12, color="#64748b"), height=380)
    st.plotly_chart(fig_s, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Retencja (30 / 90 / 180 dni)</div>', unsafe_allow_html=True)
        ret = pd.DataFrame({"Gatunek":["Roguelite","Cozy","Survival","Horror","Idle"],
            "30 dni":[68,75,70,45,80],"90 dni":[42,58,52,28,65],"180 dni":[28,45,38,18,55]})
        fig_r = px.bar(ret.melt(id_vars="Gatunek",var_name="Okres",value_name="Retencja (%)"),
            x="Gatunek", y="Retencja (%)", color="Okres",
            barmode="group", color_discrete_sequence=["#6366f1","#8b5cf6","#c7d2fe"])
        fig_r.update_layout(**PLOT_LAYOUT, height=300)
        st.plotly_chart(fig_r, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Kanały pozyskania graczy</div>', unsafe_allow_html=True)
        acq = pd.DataFrame({"Kanał":["TikTok/Reels","Steam organiczny","Reddit/Discord","YouTube","Influencerzy","Prasa"],
            "Udział (%)": [34,28,16,12,6,4]})
        fig_a = px.pie(acq, names="Kanał", values="Udział (%)",
            hole=0.55, color_discrete_sequence=COLORS)
        fig_a.update_layout(paper_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter",color="#64748b"), height=300,
            legend=dict(font=dict(size=11)))
        fig_a.update_traces(textinfo="percent+label", textfont_size=11)
        st.plotly_chart(fig_a, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════════
# TAB 5 — AI ANALYST
# ════════════════════════════════════════════════════════════════════════════════
with tab5:
    st.markdown('<div class="page-header"><div class="page-title">AI Analyst</div><div class="page-sub">Powered by Claude — zadaj pytanie o rynek gamedev</div></div>', unsafe_allow_html=True)

    if not settings.has_anthropic_key:
        st.error("⚠️ Brak ANTHROPIC_API_KEY. Dodaj klucz w Secrets na Streamlit Cloud.")
        st.stop()

    market_ctx = load_market_context()

    # Quick questions
    st.markdown("**Szybkie analizy:**")
    q_cols = st.columns(4)
    quick_questions = [
        "Który gatunek ma najlepszy ROI dla solo deva w 2025?",
        "Kiedy najlepiej wydać grę indie na Steam?",
        "Jak AI obniża koszty produkcji gier?",
        "Jakie są red flags przy wyborze gatunku?",
    ]
    for i, (col, q) in enumerate(zip(q_cols, quick_questions)):
        if col.button(q[:32] + "...", key=f"qq_{i}", use_container_width=True):
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
    if st.button("📄 Generuj Weekly Report", use_container_width=False):
        with st.spinner("Generuję raport tygodniowy..."):
            report = get_weekly_market_summary(market_ctx)
        st.markdown(report)

# ════════════════════════════════════════════════════════════════════════════════
# TAB 6 — DANE
# ════════════════════════════════════════════════════════════════════════════════
with tab6:
    st.markdown('<div class="page-header"><div class="page-title">Zarządzanie danymi</div><div class="page-sub">Aktualizacja danych Steam i konfiguracja</div></div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Aktualizuj dane</div>', unsafe_allow_html=True)
        st.markdown('<div class="card-sub">Pobiera dane Steam i automatycznie oblicza trendy gatunków</div>', unsafe_allow_html=True)

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
                    genre_buckets = {}
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
            st.success(f"✅ Gotowe! Pobrano {total_saved} gier, obliczono {len(genre_buckets)} gatunków.")
            st.cache_data.clear()
            st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Status bazy danych</div>', unsafe_allow_html=True)
        st.markdown('<div class="card-sub">Aktualne statystyki</div>', unsafe_allow_html=True)
        stats = get_db_stats()
        m1, m2, m3 = st.columns(3)
        m1.metric("Gier", f"{stats['games']:,}")
        m2.metric("Trendy", stats['genre_trends'])
        m3.metric("AI cache", stats['ai_reports'])
        st.divider()
        st.markdown('<div class="card-title">Konfiguracja</div>', unsafe_allow_html=True)
        cfg = {
            "Claude API": "✅ Aktywny" if settings.has_anthropic_key else "❌ Brak klucza",
            "Twitch API": "✅ Aktywny" if settings.has_twitch_keys else "⚠️ Opcjonalny",
            "Baza danych": "SQLite (lokalny)",
            "Środowisko": settings.app_env,
        }
        for k, v in cfg.items():
            st.text(f"{k}: {v}")
        st.markdown('</div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)
