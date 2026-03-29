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
html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; background-color: #0f1117 !important; color: #e2e8f0 !important; }
.stApp { background-color: #0f1117 !important; }
#MainMenu, footer { visibility: hidden; }
section[data-testid="stSidebar"] { display: none !important; }
.block-container { padding: 16px 24px 60px !important; max-width: 100% !important; }
.stTabs [data-baseweb="tab-list"] { background: #1e2130 !important; border-radius: 10px !important; padding: 4px !important; gap: 2px !important; border: 1px solid #2d3348 !important; margin-bottom: 16px !important; }
.stTabs [data-baseweb="tab"] { background: transparent !important; color: #94a3b8 !important; border: none !important; border-radius: 8px !important; padding: 8px 14px !important; font-size: 13px !important; font-weight: 500 !important; }
.stTabs [aria-selected="true"] { background: #6366f1 !important; color: #fff !important; font-weight: 600 !important; }
.stTabs [data-baseweb="tab-panel"] { padding-top: 4px !important; }
[data-testid="metric-container"] { background: #1e2130 !important; border: 1px solid #2d3348 !important; border-radius: 12px !important; padding: 14px 18px !important; }
[data-testid="stMetricValue"] { color: #f1f5f9 !important; font-weight: 700 !important; }
[data-testid="stMetricLabel"] { color: #64748b !important; font-size: 12px !important; }
[data-testid="stMetricDelta"] svg { display: none; }
.stButton button { background: #6366f1 !important; color: white !important; border: none !important; border-radius: 8px !important; font-weight: 600 !important; padding: 8px 16px !important; font-size: 13px !important; }
.stButton button:hover { background: #4f46e5 !important; }
.stMultiSelect [data-baseweb="select"] > div,
.stSelectbox [data-baseweb="select"] > div { background: #1e2130 !important; border-color: #2d3348 !important; }
.stMultiSelect span { background: #312e81 !important; color: #c7d2fe !important; }
.streamlit-expanderHeader { background: #1a1f2e !important; border-bottom: 1px solid #2d3348 !important; color: #c8d0e0 !important; font-size: 11px !important; font-weight: 700 !important; letter-spacing: 0.08em !important; text-transform: uppercase !important; }
.streamlit-expanderContent { background: #1a1f2e !important; border-bottom: 1px solid #2d3348 !important; }
.stDataFrame { border-radius: 10px !important; overflow: hidden !important; }
.stProgress > div > div > div { background: #6366f1 !important; }
.stChatMessage { background: #1e2130 !important; border: 1px solid #2d3348 !important; border-radius: 12px !important; }
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: #0f1117; }
::-webkit-scrollbar-thumb { background: #2d3348; border-radius: 4px; }
.panel-title { font-size: 10px; font-weight: 700; color: #64748b; letter-spacing: 0.14em; text-transform: uppercase; padding: 6px 0; border-bottom: 1px solid #2d3348; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# ── Init ──────────────────────────────────────────────────────────────────────
def initialize():
    init_db()
    stats = get_db_stats()
    if stats["games"] == 0:
        from utils.seed import seed_games, seed_genre_trends
        seed_games(20)
        seed_genre_trends(30)
    return get_db_stats()

@st.cache_data(ttl=60)
def get_fresh_stats():
    return get_db_stats()

# ── Cache ─────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=1800)
def load_genre_stats(): return get_genre_stats_df()
@st.cache_data(ttl=1800)
def load_trend_history(): return get_trend_history_df(days=30)
@st.cache_data(ttl=1800)
def load_top_games(): return get_top_games_df(limit=20)
@st.cache_data(ttl=600)
def load_market_context(): return get_market_context()

# ── Plotly ────────────────────────────────────────────────────────────────────
BG = "rgba(0,0,0,0)"
FONT = dict(family="Inter", color="#94a3b8", size=12)
GRID = "#1e2130"
COLORS = ["#6366f1","#8b5cf6","#06b6d4","#10b981","#f59e0b","#ef4444","#ec4899","#84cc16"]

def dark_layout(**kw):
    base = dict(paper_bgcolor=BG, plot_bgcolor=BG, font=FONT, margin=dict(t=10,b=30,l=40,r=10))
    if "xaxis" not in kw: base["xaxis"] = dict(gridcolor=GRID, linecolor=GRID)
    if "yaxis" not in kw: base["yaxis"] = dict(gridcolor=GRID, linecolor=GRID)
    base.update(kw)
    return base

# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT
# ══════════════════════════════════════════════════════════════════════════════
main_col, side_col = st.columns([5, 1], gap="large")

# ─────────────────────────────────────────────────────────────────────────────
# PRAWY PANEL — tylko zarządzanie danymi
# ─────────────────────────────────────────────────────────────────────────────
with side_col:
    db_stats = get_fresh_stats()
    st.markdown(f"<div style='font-size:11px;color:#64748b;margin-bottom:8px'>🟢 {db_stats['games']:,} gier</div>", unsafe_allow_html=True)

    st.markdown("<div class='panel-title'>DANE</div>", unsafe_allow_html=True)

    from scrapers.steam import GENRE_TO_TAG
    dl_genres = st.multiselect(
        "Gatunki",
        options=list(GENRE_TO_TAG.keys()),
        default=["Roguelite","Cozy","Survival","Horror"],
        key="dl_genres"
    )

    if st.button("🌱 Dane demo", use_container_width=True):
        with st.spinner("Ładuję..."):
            from utils.seed import seed_games, seed_genre_trends
            from db.models import Game, GenreTrend
            with get_session() as db:
                db.query(GenreTrend).delete()
                db.query(Game).delete()
            seed_games(20)
            seed_genre_trends(30)
        st.success("✅ Załadowano!")
        st.cache_data.clear()
        st.rerun()

    if st.button("🔄 Pobierz Steam", use_container_width=True):
        if not dl_genres:
            st.warning("Wybierz gatunki!")
        else:
            from scrapers.steam import fetch_genre_data
            from db.models import Game, GenreTrend
            from datetime import datetime, timezone

            prog = st.progress(0)
            stat = st.empty()
            saved = 0
            buckets = {}

            for i, genre in enumerate(dl_genres):
                stat.text(f"{genre}...")
                try:
                    games = fetch_genre_data(genre, pages=1)
                    for g in games:
                        try:
                            with get_session() as db:
                                ex = db.query(Game).filter_by(app_id=g["app_id"]).first()
                                if ex:
                                    ex.owners_min = g.get("owners_min",0)
                                    ex.owners_max = g.get("owners_max",0)
                                    ex.positive   = g.get("positive",0)
                                    ex.negative   = g.get("negative",0)
                                    ex.price_usd  = int(g.get("price_usd",0) or 0)
                                else:
                                    db.add(Game(
                                        app_id=g["app_id"], name=g["name"],
                                        developer=g.get("developer",""), publisher=g.get("publisher",""),
                                        owners_min=g.get("owners_min",0), owners_max=g.get("owners_max",0),
                                        players_forever=g.get("players_forever",0),
                                        average_playtime=g.get("average_playtime",0),
                                        median_playtime=g.get("median_playtime",0),
                                        price_usd=int(g.get("price_usd",0) or 0),
                                        positive=g.get("positive",0), negative=g.get("negative",0),
                                        tags=g.get("tags",{}),
                                    ))
                                saved += 1
                        except Exception:
                            pass
                except Exception as e:
                    stat.text(f"✗ {e}")
                prog.progress((i+1)/(len(dl_genres)+1))

            stat.text("Obliczam trendy...")
            try:
                with get_session() as db:
                    db.query(GenreTrend).delete()
                    all_g = db.query(Game).filter(Game.owners_max > 0).all()
                    for game in all_g:
                        gn = _classify_genre(game.tags or {})
                        buckets.setdefault(gn, []).append(game)
                    now = datetime.now(timezone.utc)
                    for gn, gg in buckets.items():
                        own = [x.owners_mid for x in gg]
                        rev = [x.estimated_revenue for x in gg]
                        rw  = [x.review_score for x in gg if x.positive+x.negative > 0]
                        db.add(GenreTrend(
                            genre=gn, recorded_at=now, game_count=len(gg),
                            avg_owners=int(sum(own)/len(own)) if own else 0,
                            total_owners=sum(own),
                            avg_revenue=sum(rev)/len(rev) if rev else 0.0,
                            avg_review_score=sum(rw)/len(rw) if rw else 0.0,
                            avg_playtime_h=sum(x.average_playtime/60 for x in gg)/len(gg),
                            avg_price=sum(x.price_usd for x in gg)/len(gg),
                        ))
            except Exception as e:
                st.error(f"Błąd: {e}")

            prog.progress(1.0)
            st.success(f"✅ {saved} gier")
            st.cache_data.clear()
            st.rerun()

    st.divider()
    st.caption(f"Gier: **{db_stats['games']:,}**")
    st.caption(f"Trendy: **{db_stats['genre_trends']}**")
    st.caption(f"Claude: {'✅' if settings.has_anthropic_key else '❌'}")

# ─────────────────────────────────────────────────────────────────────────────
# LEWA KOLUMNA — treść
# ─────────────────────────────────────────────────────────────────────────────
with main_col:
    st.markdown("## 🎮 **Drop**Rate &nbsp;<span style='font-size:14px;color:#64748b;font-weight:400'>GameDev Intelligence Platform</span>", unsafe_allow_html=True)
    st.write("")

    genre_df = load_genre_stats()
    trend_df = load_trend_history()
    top_df   = load_top_games()

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Overview", "📈 Trendy", "🎯 Gatunki", "🔄 Przepływy", "🤖 AI Analyst"
    ])

    # ═══════════ TAB 1 — OVERVIEW ════════════════════════════════════════════
    with tab1:
        st.markdown("### Market Overview")
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
                sel_g = st.selectbox("Podświetl gatunek", ["Wszystkie"] + genre_df["genre"].tolist(), key="hl")
                df_p = genre_df.head(10).copy()
                df_p["k"] = df_p["genre"].apply(lambda x: "Wybrany" if (sel_g != "Wszystkie" and x == sel_g) else "Pozostałe")
                fig = px.bar(df_p, x="roi_score", y="genre", orientation="h",
                    color="k" if sel_g != "Wszystkie" else "roi_score",
                    color_discrete_map={"Wybrany":"#6366f1","Pozostałe":"#2d3348"},
                    color_continuous_scale=[[0,"#312e81"],[1,"#6366f1"]],
                    text=df_p["roi_score"].round(0).astype(int))
                fig.update_layout(**dark_layout(height=340, coloraxis_showscale=False, showlegend=False,
                    yaxis={"categoryorder":"total ascending","title":""},
                    xaxis={"title":"ROI Score"}))
                fig.update_traces(textposition="outside", textfont_color="#e2e8f0", marker_line_width=0)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Brak danych. Kliknij **🌱 Dane demo** w panelu po prawej.")

        with col_r:
            st.markdown("**Podział platform 2025**")
            fig2 = go.Figure(go.Pie(labels=["Mobile","PC","Console","VR/AR","Cloud"],
                values=[48,24,28,2,3], hole=0.55, marker_colors=COLORS))
            fig2.update_layout(paper_bgcolor=BG, font=FONT, height=200,
                margin=dict(t=5,b=5,l=5,r=5), legend=dict(font=dict(size=10,color="#94a3b8")))
            fig2.update_traces(textinfo="percent", textfont_size=10)
            st.plotly_chart(fig2, use_container_width=True)
            if not genre_df.empty:
                best = genre_df.iloc[0]
                st.metric("Najlepszy ROI", best["genre"], delta=f"Score: {best['roi_score']:.0f}")
                st.metric("Avg właściciele", f"{genre_df['avg_owners'].mean():,.0f}")
                st.metric("Avg review", f"{genre_df['avg_review'].mean():.0f}%")

        if not top_df.empty:
            st.write("")
            st.markdown("**Top gry wg szacowanego przychodu**")
            d = top_df[["name","genre","owners_mid","price_usd","review_score","estimated_revenue"]].copy()
            d.columns = ["Gra","Gatunek","Właściciele","Cena ($)","Review (%)","Est. przychód ($)"]
            d["Właściciele"] = d["Właściciele"].apply(lambda x: f"{x:,}")
            d["Est. przychód ($)"] = d["Est. przychód ($)"].apply(lambda x: f"${x:,.0f}")
            d["Review (%)"] = d["Review (%)"].apply(lambda x: f"{x:.0f}%")
            d["Cena ($)"] = d["Cena ($)"].apply(lambda x: f"${x:.2f}")
            st.dataframe(d, use_container_width=True, hide_index=True)

    # ═══════════ TAB 2 — TRENDY ══════════════════════════════════════════════
    with tab2:
        st.markdown("### Analiza trendów")
        st.write("")

        if not genre_df.empty:
            kpi_cols = st.columns(min(len(genre_df), 4))
            for i, (_, row) in enumerate(genre_df.head(4).iterrows()):
                kpi_cols[i].metric(row["genre"], f"{row['avg_owners']:,.0f}", delta=f"ROI {row['roi_score']:.0f}")
            st.write("")

        col1, col2 = st.columns(2, gap="large")
        with col1:
            st.markdown("**Trend właścicieli**")
            m = st.selectbox("Metryka", ["avg_owners","avg_revenue","avg_review"], key="tm",
                format_func=lambda x: {"avg_owners":"Właściciele","avg_revenue":"Przychód ($)","avg_review":"Review (%)"}[x])
            if not trend_df.empty and "recorded_at" in trend_df.columns:
                fig = px.line(trend_df, x="recorded_at", y=m, color="genre", color_discrete_sequence=COLORS)
                fig.update_layout(**dark_layout(height=280))
                fig.update_traces(line_width=2)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Brak danych trendów.")

        with col2:
            st.markdown("**Porównanie gatunków**")
            sb = st.selectbox("Sortuj wg", ["avg_review","roi_score","avg_revenue"], key="gs",
                format_func=lambda x: {"avg_review":"Review","roi_score":"ROI","avg_revenue":"Przychód"}[x])
            if not genre_df.empty:
                ds = genre_df.sort_values(sb, ascending=False).head(8)
                fig2 = px.bar(ds, x="genre", y=sb, color=sb,
                    color_continuous_scale=[[0,"#312e81"],[1,"#6366f1"]], text=ds[sb].round(1))
                fig2.update_layout(**dark_layout(height=280, coloraxis_showscale=False, xaxis_title="", yaxis_title=sb))
                fig2.update_traces(textposition="outside", textfont_color="#e2e8f0", marker_line_width=0)
                st.plotly_chart(fig2, use_container_width=True)

        st.markdown("**Sezonowość sprzedaży Steam**")
        months = ["Sty","Lut","Mar","Kwi","Maj","Cze","Lip","Sie","Wrz","Paź","Lis","Gru"]
        heat_all = {
            "Roguelite":[60,55,62,70,75,72,68,73,80,90,95,88],
            "Cozy":[55,52,60,68,72,70,65,70,76,85,92,85],
            "Survival":[50,48,55,62,68,65,62,67,74,82,90,80],
            "Horror":[45,42,48,55,62,58,56,62,70,78,86,76],
            "Puzzle":[42,38,44,52,58,55,52,58,65,74,82,72],
        }
        hd = np.array(list(heat_all.values()))
        fig3 = px.imshow(hd, labels=dict(x="Miesiąc",y="Gatunek",color="Sprzedaż"),
            x=months, y=list(heat_all.keys()),
            color_continuous_scale=[[0,"#1e1b4b"],[1,"#6366f1"]], aspect="auto")
        fig3.update_layout(**dark_layout(height=240))
        st.plotly_chart(fig3, use_container_width=True)

    # ═══════════ TAB 3 — GATUNKI ═════════════════════════════════════════════
    with tab3:
        st.markdown("### Analiza gatunków")
        st.write("")

        if not genre_df.empty:
            gs = st.selectbox("Wybierz gatunek", genre_df["genre"].tolist(), key="gd")
            row = genre_df[genre_df["genre"] == gs].iloc[0]
            m1,m2,m3,m4,m5 = st.columns(5)
            m1.metric("Avg właściciele", f"{row['avg_owners']:,.0f}")
            m2.metric("Avg przychód", f"${row['avg_revenue']:,.0f}")
            m3.metric("Avg review", f"{row['avg_review']:.0f}%")
            m4.metric("Avg czas gry", f"{row['avg_playtime_h']:.0f}h")
            m5.metric("ROI Score", f"{row['roi_score']:.0f}")
            st.write("")

            col1, col2 = st.columns(2, gap="large")
            with col1:
                st.markdown("**Przychód vs Cena**")
                fig = px.scatter(genre_df, x="avg_price", y="avg_revenue",
                    size="game_count", color="roi_score", hover_name="genre",
                    color_continuous_scale=[[0,"#312e81"],[1,"#6366f1"]], size_max=50)
                fig.update_layout(**dark_layout(height=320,
                    xaxis_title="Średnia cena ($)", yaxis_title="Avg przychód ($)"))
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.markdown("**Retencja — Avg czas gry**")
                srt = genre_df.sort_values("avg_playtime_h", ascending=False)
                fig2 = px.bar(srt, x="genre", y="avg_playtime_h",
                    color="avg_playtime_h", color_continuous_scale=[[0,"#312e81"],[1,"#6366f1"]],
                    text=srt["avg_playtime_h"].round(1))
                fig2.update_layout(**dark_layout(height=320, coloraxis_showscale=False,
                    xaxis_title="", yaxis_title="Avg czas gry (h)"))
                fig2.update_traces(textposition="outside", textfont_color="#e2e8f0", marker_line_width=0)
                st.plotly_chart(fig2, use_container_width=True)

            st.markdown("**Ranking gatunków**")
            disp = genre_df.copy()
            disp["avg_revenue"] = disp["avg_revenue"].apply(lambda x: f"${x:,.0f}")
            disp["avg_owners"]  = disp["avg_owners"].apply(lambda x: f"{x:,}")
            disp["avg_review"]  = disp["avg_review"].apply(lambda x: f"{x:.0f}%")
            disp["avg_price"]   = disp["avg_price"].apply(lambda x: f"${x:.2f}")
            disp["roi_score"]   = disp["roi_score"].apply(lambda x: f"{x:.0f}")
            disp = disp[["genre","game_count","avg_owners","avg_revenue","avg_review","avg_price","roi_score"]]
            disp.columns = ["Gatunek","Gier","Avg właściciele","Avg przychód","Avg review","Avg cena","ROI"]
            st.dataframe(disp, use_container_width=True, hide_index=True)
        else:
            st.info("Brak danych.")

    # ═══════════ TAB 4 — PRZEPŁYWY ═══════════════════════════════════════════
    with tab4:
        st.markdown("### Przepływy graczy")
        st.write("")

        labels = ["Roguelite","Horror","Puzzle","Platformer","Survival","Cozy","Idle","Visual Novel"]
        fig_s = go.Figure(go.Sankey(
            node=dict(pad=20, thickness=20, label=labels, color=COLORS[:len(labels)],
                line=dict(color="#2d3348", width=0.5)),
            link=dict(source=[0,0,1,1,2,2,3,3], target=[4,5,4,6,5,7,5,7],
                value=[420,280,190,120,150,95,180,110],
                color=["rgba(99,102,241,0.2)"]*8),
        ))
        fig_s.update_layout(paper_bgcolor=BG, font=dict(family="Inter",size=12,color="#94a3b8"),
            height=360, margin=dict(t=10,b=10))
        st.plotly_chart(fig_s, use_container_width=True)

        col1, col2 = st.columns(2, gap="large")
        with col1:
            st.markdown("**Retencja (30 / 90 / 180 dni)**")
            ret = pd.DataFrame({
                "Gatunek":["Roguelite","Cozy","Survival","Horror","Idle","Puzzle","Visual Novel","Platformer"],
                "30 dni":[68,75,70,45,80,72,78,65],
                "90 dni":[42,58,52,28,65,48,55,40],
                "180 dni":[28,45,38,18,55,32,42,25]
            })
            fig_r = px.bar(ret.melt(id_vars="Gatunek",var_name="Okres",value_name="Retencja (%)"),
                x="Gatunek", y="Retencja (%)", color="Okres", barmode="group",
                color_discrete_sequence=["#6366f1","#8b5cf6","#c7d2fe"])
            fig_r.update_layout(**dark_layout(height=280))
            st.plotly_chart(fig_r, use_container_width=True)

        with col2:
            st.markdown("**Kanały pozyskania graczy**")
            acq = pd.DataFrame({"Kanał":["TikTok/Reels","Steam organiczny","Reddit/Discord","YouTube","Influencerzy","Prasa"],
                "Udział (%)": [34,28,16,12,6,4]})
            fig_a = px.pie(acq, names="Kanał", values="Udział (%)", hole=0.55, color_discrete_sequence=COLORS)
            fig_a.update_layout(paper_bgcolor=BG, font=FONT, height=280, margin=dict(t=5,b=5))
            fig_a.update_traces(textinfo="percent+label", textfont_size=10)
            st.plotly_chart(fig_a, use_container_width=True)

    # ═══════════ TAB 5 — AI ANALYST ══════════════════════════════════════════
    with tab5:
        st.markdown("### AI Analyst")
        st.caption("Powered by Claude")
        st.write("")

        if not settings.has_anthropic_key:
            st.error("⚠️ Brak ANTHROPIC_API_KEY.")
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
                "content": "Cześć! Jestem DropRate AI. Zapytaj mnie o trendy, ROI, timing premiery lub strategię.",
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
