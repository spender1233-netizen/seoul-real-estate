"""
4단계: 부동산 대시보드
streamlit run dashboard.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from analyzer import (
    stats_by_gu, stats_by_dong, monthly_trend,
    price_per_sqm, detect_outliers, apt_history
)
from db_save import get_db_stats

# ── 페이지 설정 ────────────────────────────────────────────
st.set_page_config(
    page_title="서울 부동산 실거래가 대시보드",
    page_icon="🏙️",
    layout="wide",
)

st.title("🏙️ 서울 아파트 실거래가 대시보드")
st.caption("국토교통부 실거래가 공개시스템 데이터 기반")

# ── 사이드바 ───────────────────────────────────────────────
with st.sidebar:
    st.header("🔍 필터")
    stats = get_db_stats()

    gu_options = stats["수집된구"] if stats["수집된구"] else ["강남구"]
    selected_gu = st.selectbox("구 선택", gu_options)

    st.divider()
    st.metric("매매 총 건수", f"{stats['매매건수']:,}건")
    st.metric("전월세 총 건수", f"{stats['전월세건수']:,}건")
    st.metric("수집된 구", f"{len(stats['수집된구'])}개")

# ── 상단 요약 카드 ─────────────────────────────────────────
st.subheader(f"📊 {selected_gu} 요약")

df_gu = stats_by_gu()
gu_row = df_gu[df_gu["구"] == selected_gu]

if not gu_row.empty:
    r = gu_row.iloc[0]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("총 거래건수",  f"{int(r['거래건수']):,}건")
    col2.metric("평균 매매가",  f"{int(r['평균가']):,}만원")
    col3.metric("최저 매매가",  f"{int(r['최저가']):,}만원")
    col4.metric("최고 매매가",  f"{int(r['최고가']):,}만원")

st.divider()

# ── 탭 구성 ───────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📈 가격 추세", "🗺️ 동별 분석", "📐 면적별 단가", "🔎 단지 검색", "⚠️ 이상 거래"
])


# ── TAB 1: 월별 추세 ───────────────────────────────────────
with tab1:
    st.subheader("월별 평균 매매가 추세")
    df_trend = monthly_trend(selected_gu)

    if df_trend.empty:
        st.info("데이터가 부족합니다. 여러 달 데이터를 수집하면 추세를 볼 수 있어요.")
        st.caption("예시: `python main.py --gu 강남구 --months 6`")
    else:
        df_trend["연월"] = df_trend["년"].astype(str) + "-" + df_trend["월"].astype(str).str.zfill(2)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_trend["연월"], y=df_trend["평균가"],
            mode="lines+markers+text",
            name="평균가",
            text=[f"{int(v):,}" for v in df_trend["평균가"]],
            textposition="top center",
            line=dict(color="#4C72B0", width=2),
            marker=dict(size=8),
        ))
        fig.add_trace(go.Bar(
            x=df_trend["연월"], y=df_trend["거래건수"],
            name="거래건수", yaxis="y2",
            marker_color="rgba(100,160,100,0.3)",
        ))
        fig.update_layout(
            yaxis=dict(title="평균가 (만원)"),
            yaxis2=dict(title="거래건수", overlaying="y", side="right"),
            hovermode="x unified",
            height=400,
        )
        st.plotly_chart(fig, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            st.dataframe(
                df_trend[["연월", "거래건수", "평균가", "전월대비(%)"]]
                .rename(columns={"연월": "기간"}),
                hide_index=True, use_container_width=True
            )


# ── TAB 2: 동별 분석 ───────────────────────────────────────
with tab2:
    st.subheader(f"{selected_gu} 동별 평균 매매가")
    df_dong = stats_by_dong(selected_gu)

    if df_dong.empty:
        st.info("데이터가 없습니다.")
    else:
        fig2 = px.bar(
            df_dong.head(15),
            x="평균가", y="동",
            orientation="h",
            color="평균가",
            color_continuous_scale="Blues",
            text=df_dong.head(15)["평균가"].apply(lambda x: f"{int(x):,}만"),
            labels={"평균가": "평균 매매가 (만원)", "동": "법정동"},
            height=500,
        )
        fig2.update_traces(textposition="outside")
        fig2.update_layout(yaxis=dict(autorange="reversed"), coloraxis_showscale=False)
        st.plotly_chart(fig2, use_container_width=True)

        st.dataframe(
            df_dong.rename(columns={"동": "법정동"}),
            hide_index=True, use_container_width=True
        )


# ── TAB 3: 면적별 단가 ─────────────────────────────────────
with tab3:
    st.subheader("면적 구간별 ㎡당 단가")
    df_sqm = price_per_sqm(selected_gu)

    if df_sqm.empty:
        st.info("데이터가 없습니다.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            fig3 = px.bar(
                df_sqm,
                x="면적구간", y="평균단가_만원per㎡",
                color="평균단가_만원per㎡",
                color_continuous_scale="Oranges",
                text=df_sqm["평균단가_만원per㎡"].apply(lambda x: f"{int(x):,}만/㎡"),
                labels={"평균단가_만원per㎡": "㎡당 단가 (만원)", "면적구간": "면적 구간"},
                height=400,
            )
            fig3.update_traces(textposition="outside")
            fig3.update_layout(coloraxis_showscale=False)
            st.plotly_chart(fig3, use_container_width=True)

        with col2:
            fig4 = px.pie(
                df_sqm, values="거래건수", names="면적구간",
                title="면적 구간별 거래 비중",
                hole=0.4,
            )
            st.plotly_chart(fig4, use_container_width=True)

        st.dataframe(df_sqm, hide_index=True, use_container_width=True)


# ── TAB 4: 단지 검색 ───────────────────────────────────────
with tab4:
    st.subheader("단지별 거래 내역 검색")
    search = st.text_input("아파트 이름 검색", placeholder="예: 래미안, 은마, 자이")

    if search:
        df_hist = apt_history(search)
        if df_hist.empty:
            st.warning(f"'{search}' 검색 결과가 없습니다.")
        else:
            st.success(f"{len(df_hist)}건 검색됨")

            col1, col2, col3 = st.columns(3)
            col1.metric("평균 매매가", f"{int(df_hist['거래금액'].mean()):,}만원")
            col2.metric("최저가", f"{int(df_hist['거래금액'].min()):,}만원")
            col3.metric("최고가", f"{int(df_hist['거래금액'].max()):,}만원")

            fig5 = px.scatter(
                df_hist,
                x="거래일자", y="거래금액",
                color="전용면적", size="전용면적",
                hover_data=["아파트", "층", "거래유형"],
                labels={"거래금액": "거래금액 (만원)", "거래일자": "거래일"},
                title=f"'{search}' 거래 내역",
                height=350,
            )
            st.plotly_chart(fig5, use_container_width=True)

            st.dataframe(
                df_hist.sort_values("거래일자", ascending=False),
                hide_index=True, use_container_width=True
            )
    else:
        st.info("아파트 이름을 입력하면 거래 내역을 볼 수 있어요.")


# ── TAB 5: 이상 거래 ───────────────────────────────────────
with tab5:
    st.subheader("⚠️ 이상 거래 탐지")
    st.caption("같은 단지·면적 그룹 내에서 시세 대비 ±2.5 표준편차 이상 벗어난 거래")

    threshold = st.slider("탐지 민감도 (σ)", min_value=1.5, max_value=4.0, value=2.5, step=0.5)
    df_out = detect_outliers(selected_gu, threshold)

    if df_out.empty:
        st.success("이상 거래가 탐지되지 않았습니다.")
        st.caption("더 많은 달의 데이터를 수집하면 탐지 정확도가 높아져요.")
    else:
        st.warning(f"{len(df_out)}건의 이상 거래 탐지됨")

        fig6 = px.scatter(
            df_out,
            x="거래일자", y="거래금액",
            size="Z스코어", color="시세대비(%)",
            color_continuous_scale="RdYlGn",
            hover_data=["아파트", "전용면적", "그룹평균"],
            labels={"거래금액": "거래금액 (만원)"},
            height=350,
        )
        st.plotly_chart(fig6, use_container_width=True)
        st.dataframe(df_out, hide_index=True, use_container_width=True)



# ── AI 분석 섹션 (하단 고정) ───────────────────────────────
st.divider()
st.subheader("🤖 AI 시장 분석")
st.caption("OpenAI GPT-4o-mini가 실거래 데이터를 바탕으로 시장을 해설합니다")

col_focus, col_btn = st.columns([3, 1])
with col_focus:
    focus = st.selectbox(
        "분석 초점",
        ["종합", "투자", "실수요", "이상거래"],
        label_visibility="collapsed",
    )
with col_btn:
    run_ai = st.button("🤖 AI 분석 시작", use_container_width=True)

if run_ai:
    from ai_analyst import stream_analysis
    with st.spinner("AI가 데이터를 분석 중입니다..."):
        result_box = st.empty()
        full_text = ""
        for chunk in stream_analysis(selected_gu, focus):
            full_text += chunk
            result_box.markdown(full_text + "▌")
        result_box.markdown(full_text)
