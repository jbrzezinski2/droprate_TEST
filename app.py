"""
app.py — DropRate Dashboard z globalnym filtrem i interaktywnym UI
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
html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; background-color: #0f1117 !important; color: #e2e8f0 !important; }
.stApp { background-color: #0f1117 !important; }
#MainMenu, footer { visibility: hidden; }
section[data-testid="stSidebar"] { display: none !important; }
.block-container { padding: 20px 32px 60px !important; max-width: 1400px !important; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] { background: #1e2130 !important; border-radius: 10px !important; padding: 4px !important; gap: 2px !important; border: 1px solid #2d3348 !important; margin-bottom: 20px !important; }
.stTabs [data-baseweb="tab"] { background: transparent !important; color: #94a3b8 !important; border: none !important; border-radius: 8px !important; padding: 8px 16px !important; font-size: 13px !important; font-weight: 500 !important; }
.stTabs [aria-selected="true"] { background: #6366f1 !important; color: #fff !important; font-weight: 600 !important; }
.stTabs [data-baseweb="tab-panel"] { padding-top: 4px !important; }

/* Filter bar */
.filter-bar { background: #1e2130; border: 1px solid #2d3348; border-radius: 12px; padding: 12px 20px; margin-bottom: 20px; }

/* Metrics */
[data-testid="metric-container"] { background: #1e2130 !important; border: 1px solid #2d3348 !important; border-radius: 12px !important; padding: 14px 18px !important; }
[data-testid="stMetricValue"] { color: #f1f5f9 !important; font-weight: 700 !important; }
[data-testid="stMetricLabel"] { color: #64748b !important; font-size: 12px !important; }
[data-testid="stMetricDelta"] svg { display: none; }

/* Buttons */
.stButton button { background: #6366f1 !important; color: white !important; border: none !important; border-radius: 8px !important; font-weight: 600 !important; padding: 8px 18px !important; font-size: 13px !important; }
.stButton button:hover { background: #4f46e5 !important; }

/* Inputs */
.stMultiSelect [data-baseweb="select"] > div,
.stSelectbox [data-baseweb="select"] > div { background: #1e2130 !important; border-color: #2d3348 !important; color: #e2e8f0 !important; }
.stMultiSelect span { background: #312e81 !important; color: #c7d2fe !important; }
.stSlider [data-baseweb="slider"] { color: #6366f1 !important; }

/* Dataframe */
.stDataFrame { border-radius: 10px !important; overflow: hidden !important; }

/* Progress */
.stProgress > div > div > div { background: #6366f1 !important; }

/* Chat */
.stChatMessage { background: #1e2130 !important; border: 1px solid #2d3348 !important; border-radius: 12px !important; }

/* Expander */
.streamlit-expanderHeader { background: #1e2130 !important; border-radius: 8px !important; color: #94a3b8 !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: #0f1117; }
::-webkit-scrollbar-thumb { background: #2d3348; border-radius: 4px; }
</style>
""", unsafe_allow_html=True)

# ── Init ──────────────────────────────────────────────────────────────────────
@st.cache_resource
def initialize():
    init_db()
    return True
initialize()

# ── Session State — globalne filtry ──────────────────────────────────────────
ALL_GENRES = ["Roguelite","Cozy","Survival","Horror","Idle","Puzzle","Visual Novel","Platformer","RPG","Action","Strategy","Simulation"]

if "selected_genres" not in st.session_state:
    st.session_state.selected_genres = ALL_GENRES
if "days_range" not in st.session_state:
    st.session_state.days_range = 30
if "min_roi" not in st.session_state:
    st.session_state.min_roi = 0

# ── Cache data ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=1800)
def load_genre_stats(): return get_genre_stats_df()
@st.cache_data(ttl=1800)
def load_trend_history(days): return get_trend_history_df(days=days)
@st.cache_data(ttl=1800)
def load_top_games(): return get_top_games_df(limit=20)
@st.cache_data(ttl=600)
def load_market_context(): return get_market_context()

# ── Apply filters ─────────────────────────────────────────────────────────────
def apply_genre_filter(df, col="genre"):
    if df.empty or col not in df.columns:
        return df
    return df[df[col].isin(st.session_state.selected_genres)]

def apply_roi_filter(df, col="roi_score"):
    if df.empty or col not in df.columns:
        return df
    return df[df[col] >= st.session_state.min_roi]

# ── Plotly dark theme ─────────────────────────────────────────────────────────
BG   = "rgba(0,0,0,0)"
FONT = dict(family="Inter", color="#94a3b8", size=12)
GRID = "#1e2130"
COLORS = ["#6366f1","#8b5cf6","#06b6d4","#10b981","#f59e0b","#ef4444","#ec4899","#84cc16"]

def dark_layout(**kw):
    base = dict(paper_bgcolor=BG, plot_bgcolor=BG, font=FONT,
        margin=dict(t=10, b=30, l=40, r=10))
    if "xaxis" not in kw:
        base["xaxis"] = dict(gridcolor=GRID, linecolor=GRID)
    if "yaxis" not in kw:
        base["yaxis"] = dict(gridcolor=GRID, linecolor=GRID)
    base.update(kw)
    return base

# ── HEADER ────────────────────────────────────────────────────────────────────
db_stats = get_db_stats()

h1, h2 = st.columns([5, 1])
with h1:
    st.markdown("## 🎮 **Drop**Rate &nbsp; <span style='font-size:14px;color:#64748b;font-weight:400'>GameDev Intelligence Platform</span>", unsafe_allow_html=True)
with h2:
    st.markdown(f"<div style='text-align:right;padding-top:14px;font-size:12px;color:#64748b'>🟢 LIVE &nbsp;|&nbsp; {db_stats['games']:,} gier</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# GLOBALNY PASEK FILTRÓW — zawsze widoczny
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("🔧 Filtry globalne — zmień tu, dane zmieniają się wszędzie", expanded=True):
    fc1, fc2, fc3, fc4, fc5 = st.columns([3, 1, 1, 1, 1])

    with fc1:
        new_genres = st.multiselect(
            "Gatunki",
            options=ALL_GENRES,
            default=st.session_state.selected_genres,
            key="genre_filter_widget",
        )

    with fc2:
        new_days = st.selectbox(
            "Horyzont czasowy",
            options=[7, 14, 30, 60, 90],
            index=[7,14,30,60,90].index(st.session_state.days_range),
            format_func=lambda x: f"{x} dni",
        )

    with fc3:
        new_roi = st.slider("Min ROI Score", 0, 90, st.session_state.min_roi, step=10)

    with fc4:
        st.write("")
        st.write("")
        if st.button("✅ Zastosuj", use_container_width=True):
            st.session_state.selected_genres = new_genres
            st.session_state.days_range = new_days
            st.session_state.min_roi = new_roi
            st.cache_data.clear()
            st.rerun()

    with fc5:
        st.write("")
        st.write("")
        if st.button("↺ Reset", use_container_width=True):
            st.session_state.selected_genres = ALL_GENRES
            st.session_state.days_range = 30
            st.session_state.min_roi = 0
            st.cache_data.clear()
            st.rerun()

# Załaduj i przefiltruj dane
raw_genre_df = load_genre_stats()
genre_df     = apply_roi_filter(apply_genre_filter(raw_genre_df))
trend_df     = apply_genre_filter(load_trend_history(st.session_state.days_range))
top_df       = apply_genre_filter(load_top_games())

# Aktywne filtry info
active = []
if len(st.session_state.selected_genres) < len(ALL_GENRES):
    active.append(f"Gatunki: {', '.join(st.session_state.selected_genres)}")
if st.session_state.min_roi > 0:
    active.append(f"Min ROI: {st.session_state.min_roi}")
if st.session_state.days_range != 30:
    active.append(f"Okres: {st.session_state.days_range} dni")
if active:
    st.caption(f"🔍 Aktywne filtry: {' · '.join(active)}")

st.write("")

# ── TABS ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Overview", "📈 Trendy", "🎯 Gatunki",
    "🔄 Przepływy", "🤖 AI Analyst", "⚙️ Dane"
])

# ═══════════════════════════════ TAB 1 — OVERVIEW ════════════════════════════
with tab1:
    st.markdown("### Market Overview")
    st.caption(f"Dane przefiltrowane · {len(genre_df)} gatunków · {st.session_state.days_range} dni")
    st.write("")

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Gier w bazie", f"{db_stats['games']:,}")
    c2.metric("Gatunków (filtr)", len(genre_df) if not genre_df.empty else 0)
    c3.metric("Rynek indie", "$4.8B", delta="+8.4% r/r")
    c4.metric("Avg hit rate", "2.4%", delta="-0.7%", delta_color="inverse")
    c5.metric("AI adopcja", "67%", delta="+34% r/r")

    st.write("")

    col_l, col_r = st.columns([3, 2], gap="large")

    with col_l:
        st.markdown("**ROI Score per gatunek**")
        if not genre_df.empty:
            # Kliknięcie na gatunek → filtruje resztę
            selected_point = st.selectbox(
                "Podświetl gatunek",
                options=["Wszystkie"] + genre_df["genre"].tolist(),
                key="highlight_genre"
            )
            df_plot = genre_df.head(10).copy()
            df_plot["highlight"] = df_plot["genre"].apply(
                lambda x: "Wybrany" if (selected_point != "Wszystkie" and x == selected_point) else "Pozostałe"
            )
            fig = px.bar(df_plot, x="roi_score", y="genre", orientation="h",
                color="highlight" if selected_point != "Wszystkie" else "roi_score",
                color_discrete_map={"Wybrany":"#6366f1","Pozostałe":"#2d3348"},
                color_continuous_scale=[[0,"#312e81"],[1,"#6366f1"]],
                text=df_plot["roi_score"].round(0).astype(int))
            fig.update_layout(**dark_layout(height=360, coloraxis_showscale=False, showlegend=False,
                yaxis={"categoryorder":"total ascending","title":""},
                xaxis={"title":"ROI Score"}))
            fig.update_traces(textposition="outside", textfont_color="#e2e8f0", marker_line_width=0)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Brak danych. Zmień filtry lub zaktualizuj dane w ⚙️ Dane.")

    with col_r:
        st.markdown("**Podział platform 2025**")
        fig2 = go.Figure(go.Pie(
            labels=["Mobile","PC","Console","VR/AR","Cloud"],
            values=[48,24,28,2,3], hole=0.55,
            marker_colors=COLORS))
        fig2.update_layout(paper_bgcolor=BG, font=FONT, height=200,
            margin=dict(t=5,b=5,l=5,r=5),
            legend=dict(font=dict(size=11,color="#94a3b8")))
        fig2.update_traces(textinfo="percent", textfont_size=10)
        st.plotly_chart(fig2, use_container_width=True)

        st.markdown("**Szybkie statystyki (filtr)**")
        if not genre_df.empty:
            best = genre_df.iloc[0]
            st.metric("Najlepszy ROI", best["genre"], delta=f"Score: {best['roi_score']:.0f}")
            st.metric("Avg właściciele", f"{genre_df['avg_owners'].mean():,.0f}")
            st.metric("Avg review", f"{genre_df['avg_review'].mean():.0f}%")

    st.write("")
    st.markdown("**Top gry wg szacowanego przychodu**")
    if not top_df.empty:
        disp = top_df[["name","genre","owners_mid","price_usd","review_score","estimated_revenue"]].copy()
        disp.columns = ["Gra","Gatunek","Właściciele","Cena ($)","Review (%)","Est. przychód ($)"]
        disp["Właściciele"] = disp["Właściciele"].apply(lambda x: f"{x:,}")
        disp["Est. przychód ($)"] = disp["Est. przychód ($)"].apply(lambda x: f"${x:,.0f}")
        disp["Review (%)"] = disp["Review (%)"].apply(lambda x: f"{x:.0f}%")
        disp["Cena ($)"] = disp["Cena ($)"].apply(lambda x: f"${x:.2f}")
        st.dataframe(disp, use_container_width=True, hide_index=True)
    else:
        st.info("Brak danych. Zaktualizuj w ⚙️ Dane.")

# ═══════════════════════════════ TAB 2 — TRENDY ══════════════════════════════
with tab2:
    st.markdown("### Analiza trendów")
    st.caption(f"Okres: ostatnie {st.session_state.days_range} dni · {len(st.session_state.selected_genres)} gatunków")
    st.write("")

    # Metryka trendu per gatunek
    if not genre_df.empty:
        cols = st.columns(min(len(genre_df), 4))
        for i, (_, row) in enumerate(genre_df.head(4).iterrows()):
            cols[i].metric(row["genre"], f"{row['avg_owners']:,.0f}", delta=f"ROI {row['roi_score']:.0f}")
        st.write("")

    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown("**Trend właścicieli**")
        metric_opt = st.selectbox("Metryka", ["avg_owners","avg_revenue","avg_review"], key="trend_metric",
            format_func=lambda x: {"avg_owners":"Właściciele","avg_revenue":"Przychód ($)","avg_review":"Review (%)"}[x])
        if not trend_df.empty and "recorded_at" in trend_df.columns:
            filtered_trend = apply_genre_filter(trend_df)
            fig = px.line(filtered_trend, x="recorded_at", y=metric_opt, color="genre",
                color_discrete_sequence=COLORS)
            fig.update_layout(**dark_layout(height=300))
            fig.update_traces(line_width=2)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Brak danych trendów. Zaktualizuj dane w ⚙️.")

    with col2:
        st.markdown("**Review Score per gatunek**")
        if not genre_df.empty:
            sort_by = st.selectbox("Sortuj wg", ["avg_review","roi_score","avg_revenue"], key="genre_sort",
                format_func=lambda x: {"avg_review":"Review","roi_score":"ROI","avg_revenue":"Przychód"}[x])
            df_sorted = genre_df.sort_values(sort_by, ascending=False).head(8)
            fig2 = px.bar(df_sorted, x="genre", y=sort_by,
                color=sort_by, color_continuous_scale=[[0,"#312e81"],[1,"#6366f1"]],
                text=df_sorted[sort_by].round(1))
            fig2.update_layout(**dark_layout(height=300, coloraxis_showscale=False,
                xaxis_title="", yaxis_title=sort_by))
            fig2.update_traces(textposition="outside", textfont_color="#e2e8f0", marker_line_width=0)
            st.plotly_chart(fig2, use_container_width=True)

    st.markdown("**Sezonowość sprzedaży Steam**")
    months = ["Sty","Lut","Mar","Kwi","Maj","Cze","Lip","Sie","Wrz","Paź","Lis","Gru"]
    sel_g = [g for g in ["Roguelite","Cozy","Survival","Horror","Puzzle"] if g in st.session_state.selected_genres]
    if not sel_g:
        sel_g = ["Roguelite","Cozy","Survival","Horror","Puzzle"]
    heat_all = {
        "Roguelite": [60,55,62,70,75,72,68,73,80,90,95,88],
        "Cozy":      [55,52,60,68,72,70,65,70,76,85,92,85],
        "Survival":  [50,48,55,62,68,65,62,67,74,82,90,80],
        "Horror":    [45,42,48,55,62,58,56,62,70,78,86,76],
        "Puzzle":    [42,38,44,52,58,55,52,58,65,74,82,72],
    }
    heat_data = np.array([heat_all.get(g, [50]*12) for g in sel_g])
    fig3 = px.imshow(heat_data, labels=dict(x="Miesiąc",y="Gatunek",color="Sprzedaż"),
        x=months, y=sel_g,
        color_continuous_scale=[[0,"#1e1b4b"],[1,"#6366f1"]], aspect="auto")
    fig3.update_layout(**dark_layout(height=max(180, len(sel_g)*50)))
    st.plotly_chart(fig3, use_container_width=True)

# ═══════════════════════════════ TAB 3 — GATUNKI ═════════════════════════════
with tab3:
    st.markdown("### Analiza gatunków")
    st.caption("Szczegółowe porównanie — kliknij gatunek by zobaczyć szczegóły")
    st.write("")

    if not genre_df.empty:
        # Interaktywny wybór gatunku
        genre_select = st.selectbox("Wybierz gatunek do analizy",
            options=genre_df["genre"].tolist(), key="genre_detail")

        row = genre_df[genre_df["genre"] == genre_select].iloc[0]
        m1,m2,m3,m4,m5 = st.columns(5)
        m1.metric("Avg właściciele", f"{row['avg_owners']:,.0f}")
        m2.metric("Avg przychód", f"${row['avg_revenue']:,.0f}")
        m3.metric("Avg review", f"{row['avg_review']:.0f}%")
        m4.metric("Avg czas gry", f"{row['avg_playtime_h']:.0f}h")
        m5.metric("ROI Score", f"{row['roi_score']:.0f}")
        st.write("")

    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown("**Przychód vs Cena (rozmiar = liczba gier)**")
        if not genre_df.empty:
            fig = px.scatter(genre_df, x="avg_price", y="avg_revenue",
                size="game_count", color="roi_score", hover_name="genre",
                color_continuous_scale=[[0,"#312e81"],[1,"#6366f1"]], size_max=50)
            fig.update_layout(**dark_layout(height=320,
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
            fig2.update_layout(**dark_layout(height=320, coloraxis_showscale=False,
                xaxis_title="", yaxis_title="Avg czas gry (h)"))
            fig2.update_traces(textposition="outside", textfont_color="#e2e8f0", marker_line_width=0)
            st.plotly_chart(fig2, use_container_width=True)

    st.markdown("**Ranking gatunków**")
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

# ═══════════════════════════════ TAB 4 — PRZEPŁYWY ═══════════════════════════
with tab4:
    st.markdown("### Przepływy graczy")
    st.caption("Skąd i dokąd migrują gracze po porzuceniu gry")
    st.write("")

    labels = ["Roguelite","Horror","Puzzle","Platformer","Survival","Cozy","Idle","Visual Novel"]
    visible = [l for l in labels if l in st.session_state.selected_genres] or labels
    fig_s = go.Figure(go.Sankey(
        node=dict(pad=20, thickness=20, label=labels, color=COLORS[:len(labels)],
            line=dict(color="#2d3348", width=0.5)),
        link=dict(source=[0,0,1,1,2,2,3,3], target=[4,5,4,6,5,7,5,7],
            value=[420,280,190,120,150,95,180,110],
            color=["rgba(99,102,241,0.2)"]*8),
    ))
    fig_s.update_layout(paper_bgcolor=BG, font=dict(family="Inter",size=12,color="#94a3b8"),
        height=380, margin=dict(t=10,b=10))
    st.plotly_chart(fig_s, use_container_width=True)

    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown("**Retencja (30 / 90 / 180 dni)**")
        ret_all = pd.DataFrame({
            "Gatunek":["Roguelite","Cozy","Survival","Horror","Idle","Puzzle","Visual Novel","Platformer"],
            "30 dni": [68,75,70,45,80,72,78,65],
            "90 dni": [42,58,52,28,65,48,55,40],
            "180 dni":[28,45,38,18,55,32,42,25]
        })
        ret_filt = ret_all[ret_all["Gatunek"].isin(st.session_state.selected_genres)]
        if ret_filt.empty:
            ret_filt = ret_all
        fig_r = px.bar(ret_filt.melt(id_vars="Gatunek",var_name="Okres",value_name="Retencja (%)"),
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
        fig_a.update_layout(paper_bgcolor=BG, font=FONT, height=300, margin=dict(t=5,b=5))
        fig_a.update_traces(textinfo="percent+label", textfont_size=10)
        st.plotly_chart(fig_a, use_container_width=True)

# ═══════════════════════════════ TAB 5 — AI ══════════════════════════════════
with tab5:
    st.markdown("### AI Analyst")
    st.caption("Powered by Claude — pytania filtrowane przez aktywne filtry globalne")
    st.write("")

    if not settings.has_anthropic_key:
        st.error("⚠️ Brak ANTHROPIC_API_KEY. Dodaj klucz w Secrets na Streamlit Cloud.")
        st.stop()

    market_ctx = load_market_context()
    # Dodaj info o aktywnych filtrach do kontekstu
    market_ctx["active_genres"] = st.session_state.selected_genres
    market_ctx["days_range"] = st.session_state.days_range

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
                f"Cześć! Jestem DropRate AI. Aktualnie analizuję "
                f"{len(st.session_state.selected_genres)} gatunków "
                f"za ostatnie {st.session_state.days_range} dni. "
                "Zapytaj mnie o trendy, ROI, timing premiery lub strategię."
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
    col_btn, _ = st.columns([1, 3])
    with col_btn:
        if st.button("📄 Generuj Weekly Report", use_container_width=True):
            with st.spinner("Generuję raport..."):
                report = get_weekly_market_summary(market_ctx)
            st.markdown(report)

# ═══════════════════════════════ TAB 6 — DANE ════════════════════════════════
with tab6:
    st.markdown("### Zarządzanie danymi")
    st.caption("Aktualizacja danych Steam — po pobraniu filtry globalne zastosują się automatycznie")
    st.write("")

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown("**Pobierz dane Steam**")
        st.caption("SteamSpy API — publiczne, bez klucza · 1 req/s")

        dl_genres = st.multiselect(
            "Gatunki do pobrania",
            options=list(__import__("scrapers.steam", fromlist=["GENRE_TO_TAG"]).GENRE_TO_TAG.keys()),
            default=["Roguelite", "Cozy", "Survival", "Horror"],
            key="dl_genres"
        )

        if st.button("🔄 Aktualizuj dane i trendy", use_container_width=True):
            from scrapers.steam import fetch_genre_data
            from db.models import Game, GenreTrend
            from datetime import datetime, timezone

            progress = st.progress(0)
            status = st.empty()
            total_saved = 0
            genre_buckets = {}
            steps = len(dl_genres) + 1

            for i, genre in enumerate(dl_genres):
                status.text(f"[{i+1}/{len(dl_genres)}] Pobieranie: {genre}...")
                try:
                    games = fetch_genre_data(genre, pages=1)
                    for g_data in games:
                        try:
                            with get_session() as db:
                                existing = db.query(Game).filter_by(app_id=g_data["app_id"]).first()
                                if existing:
                                    existing.owners_min = g_data.get("owners_min", 0)
                                    existing.owners_max = g_data.get("owners_max", 0)
                                    existing.positive   = g_data.get("positive", 0)
                                    existing.negative   = g_data.get("negative", 0)
                                    existing.price_usd  = int(g_data.get("price_usd", 0) or 0)
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

            status.text("Obliczam trendy...")
            try:
                with get_session() as db:
                    db.query(GenreTrend).delete()
                    all_games = db.query(Game).filter(Game.owners_max > 0).all()
                    for game in all_games:
                        g = _classify_genre(game.tags or {})
                        genre_buckets.setdefault(g, []).append(game)
                    now = datetime.now(timezone.utc)
                    for g, gg in genre_buckets.items():
                        owners   = [x.owners_mid for x in gg]
                        revenues = [x.estimated_revenue for x in gg]
                        reviews  = [x.review_score for x in gg if x.positive + x.negative > 0]
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
            st.success(f"✅ Gotowe! {total_saved} gier · {len(genre_buckets)} gatunków")
            st.cache_data.clear()
            st.rerun()

    with col2:
        st.markdown("**Status systemu**")
        stats = get_db_stats()
        m1, m2, m3 = st.columns(3)
        m1.metric("Gier", f"{stats['games']:,}")
        m2.metric("Trendy", stats['genre_trends'])
        m3.metric("AI cache", stats['ai_reports'])

        st.divider()
        st.markdown("**Aktywne filtry globalne**")
        st.write(f"Gatunki: **{', '.join(st.session_state.selected_genres)}**")
        st.write(f"Horyzont: **{st.session_state.days_range} dni**")
        st.write(f"Min ROI: **{st.session_state.min_roi}**")

        st.divider()
        st.markdown("**Konfiguracja**")
        st.text(f"Claude API: {'✅ Aktywny' if settings.has_anthropic_key else '❌ Brak'}")
        st.text(f"Twitch API: {'✅ Aktywny' if settings.has_twitch_keys else '⚠️ Opcjonalny'}")
        st.text(f"Środowisko: {settings.app_env}")
