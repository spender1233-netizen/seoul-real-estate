"""
지도 히트맵 - Folium 기반 (OpenStreetMap)
"""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from analyzer import stats_by_gu

GU_COORDS = {
    "강남구":  (37.5172, 127.0473),
    "강동구":  (37.5301, 127.1238),
    "강북구":  (37.6396, 127.0257),
    "강서구":  (37.5509, 126.8495),
    "관악구":  (37.4784, 126.9516),
    "광진구":  (37.5384, 127.0822),
    "구로구":  (37.4954, 126.8874),
    "금천구":  (37.4600, 126.9001),
    "노원구":  (37.6542, 127.0568),
    "도봉구":  (37.6688, 127.0471),
    "동대문구":(37.5744, 127.0396),
    "동작구":  (37.5124, 126.9393),
    "마포구":  (37.5638, 126.9084),
    "서대문구":(37.5791, 126.9368),
    "서초구":  (37.4837, 127.0324),
    "성동구":  (37.5635, 127.0369),
    "성북구":  (37.5894, 127.0167),
    "송파구":  (37.5145, 127.1059),
    "양천구":  (37.5270, 126.8561),
    "영등포구":(37.5264, 126.8962),
    "용산구":  (37.5324, 126.9900),
    "은평구":  (37.6026, 126.9291),
    "종로구":  (37.5735, 126.9790),
    "중구":    (37.5640, 126.9975),
    "중랑구":  (37.6063, 127.0927),
}


def get_map_data() -> pd.DataFrame:
    df = stats_by_gu()
    if df.empty:
        return pd.DataFrame()
    rows = []
    for _, r in df.iterrows():
        gu = r["구"]
        if gu in GU_COORDS:
            lat, lng = GU_COORDS[gu]
            rows.append({
                "구":      gu,
                "위도":    lat,
                "경도":    lng,
                "거래건수": int(r["거래건수"]),
                "평균가":   int(r["평균가"]),
                "최고가":   int(r["최고가"]),
                "최저가":   int(r["최저가"]),
            })
    return pd.DataFrame(rows)


def show_map_page():
    st.subheader("서울 아파트 가격 히트맵")
    st.caption("구별 평균 매매가를 지도 위에 시각화 — 원을 클릭하면 상세 정보")

    df = get_map_data()
    if df.empty:
        st.info("수집된 데이터가 없습니다. 먼저 데이터를 수집해주세요.")
        return

    col1, col2 = st.columns([2, 1])
    with col1:
        metric = st.selectbox(
            "표시 기준",
            ["평균가", "최고가", "거래건수"],
            label_visibility="collapsed"
        )
    with col2:
        st.metric("수집된 구", f"{len(df)}개")

    # Folium 지도 생성
    m = folium.Map(
        location=[37.5502, 126.9824],
        zoom_start=11,
        tiles="CartoDB positron",
    )

    # 히트맵 레이어
    heat_data = [
        [row["위도"], row["경도"], row[metric]]
        for _, row in df.iterrows()
    ]
    HeatMap(
        heat_data,
        radius=35,
        blur=25,
        min_opacity=0.4,
        gradient={0.2: "blue", 0.5: "yellow", 0.8: "orange", 1.0: "red"},
    ).add_to(m)

    # 구별 원형 마커 + 팝업
    max_val = df[metric].max()
    min_val = df[metric].min()

    for _, row in df.iterrows():
        intensity = (row[metric] - min_val) / (max_val - min_val + 1)
        red  = int(255 * intensity)
        blue = int(255 * (1 - intensity))
        color = f"#{red:02x}50{blue:02x}"

        popup_html = f"""
        <div style="font-family:sans-serif;font-size:13px;min-width:140px">
            <b style="font-size:15px">{row['구']}</b><br>
            평균가: <b>{row['평균가']:,}만원</b><br>
            최고가: {row['최고가']:,}만원<br>
            거래건수: {row['거래건수']}건
        </div>
        """

        folium.CircleMarker(
            location=[row["위도"], row["경도"]],
            radius=18,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.5,
            weight=1.5,
            popup=folium.Popup(popup_html, max_width=200),
            tooltip=f"{row['구']} | {row[metric]:,}만원"
        ).add_to(m)

        # 구 이름 라벨
        folium.Marker(
            location=[row["위도"], row["경도"]],
            icon=folium.DivIcon(
                html=f'<div style="font-size:10px;font-weight:700;color:#111;'
                     f'text-shadow:1px 1px 0 #fff,-1px -1px 0 #fff,'
                     f'1px -1px 0 #fff,-1px 1px 0 #fff;'
                     f'text-align:center;width:60px;margin-left:-30px">'
                     f'{row["구"]}<br>{row[metric]/10000:.1f}억</div>',
                icon_size=(60, 30),
                icon_anchor=(30, 15),
            )
        ).add_to(m)

    # 지도 렌더링
    st_folium(m, width=700, height=560, returned_objects=[], key="folium_map")

    # 데이터 테이블
    st.dataframe(
        df.drop(columns=["위도", "경도"])
          .sort_values("평균가", ascending=False)
          .reset_index(drop=True),
        hide_index=True,
        use_container_width=True,
    )
