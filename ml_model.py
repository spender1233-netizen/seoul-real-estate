"""
4단계 개선: 가격 예측 머신러닝 모델
- 랜덤포레스트 기반 아파트 매매가 예측
- 특성: 구, 면적, 층, 건축년도, 월
- 대시보드 통합
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import pandas as pd
import numpy as np
from datetime import date

from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.preprocessing import LabelEncoder

from db_save import query_to_df
from config import SEOUL_GU_CODES


# ── 데이터 로드 및 전처리 ──────────────────────────────────

def load_training_data() -> pd.DataFrame:
    """DB에서 학습용 데이터 로드"""
    df = query_to_df("""
        SELECT
            gu, area, floor, build_year,
            trade_year, trade_month, price
        FROM apt_trade
        WHERE price IS NOT NULL
          AND area IS NOT NULL
          AND floor IS NOT NULL
          AND build_year IS NOT NULL
          AND price > 0
    """)
    return df


def preprocess(df: pd.DataFrame):
    """전처리 + 특성 엔지니어링"""
    df = df.copy()

    # 건물 나이 계산
    current_year = date.today().year
    df["building_age"] = current_year - df["build_year"]

    # 면적 구간 (원-핫 대신 수치형 구간)
    df["area_group"] = pd.cut(
        df["area"],
        bins=[0, 40, 60, 85, 115, 999],
        labels=[1, 2, 3, 4, 5]
    ).astype(float)

    # 구 인코딩
    le = LabelEncoder()
    df["gu_encoded"] = le.fit_transform(df["gu"])

    features = ["gu_encoded", "area", "floor", "building_age",
                "trade_month", "area_group"]
    target = "price"

    return df[features + [target]].dropna(), le, features


# ── 모델 학습 ──────────────────────────────────────────────

@st.cache_resource(show_spinner="모델 학습 중...")
def train_model():
    """랜덤포레스트 모델 학습 (캐시)"""
    df = load_training_data()
    if df.empty or len(df) < 30:
        return None, None, None, None

    processed, le, features = preprocess(df)

    X = processed[features]
    y = processed["price"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=12,
        min_samples_leaf=3,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    r2  = r2_score(y_test, y_pred)

    return model, le, features, {"mae": mae, "r2": r2, "n": len(processed)}


# ── 예측 ──────────────────────────────────────────────────

def predict_price(model, le, features,
                  gu, area, floor, build_year, month=None):
    """단일 예측"""
    if month is None:
        month = date.today().month

    current_year = date.today().year
    building_age = current_year - build_year

    area_group = 1
    if area < 40:   area_group = 1
    elif area < 60: area_group = 2
    elif area < 85: area_group = 3
    elif area < 115:area_group = 4
    else:           area_group = 5

    try:
        gu_encoded = le.transform([gu])[0]
    except ValueError:
        return None, "학습 데이터에 없는 구입니다."

    X = pd.DataFrame([{
        "gu_encoded":   gu_encoded,
        "area":         area,
        "floor":        floor,
        "building_age": building_age,
        "trade_month":  month,
        "area_group":   area_group,
    }])

    pred = model.predict(X)[0]

    # 예측 범위 (트리 개별 예측의 표준편차)
    preds = np.array([tree.predict(X)[0] for tree in model.estimators_])
    std = preds.std()

    return pred, std


# ── 특성 중요도 ────────────────────────────────────────────

def get_feature_importance(model, features) -> pd.DataFrame:
    importance = model.feature_importances_
    labels = {
        "gu_encoded":   "구",
        "area":         "전용면적",
        "floor":        "층",
        "building_age": "건물나이",
        "trade_month":  "거래월",
        "area_group":   "면적구간",
    }
    df = pd.DataFrame({
        "특성": [labels.get(f, f) for f in features],
        "중요도": importance,
    }).sort_values("중요도", ascending=False)
    return df


# ── Streamlit 페이지 ───────────────────────────────────────

def show_ml_page():
    st.subheader("가격 예측 ML 모델")
    st.caption("랜덤포레스트 기반 아파트 매매가 예측")

    model, le, features, metrics = train_model()

    if model is None:
        st.warning("학습 데이터가 부족합니다. 더 많은 데이터를 수집해주세요. (최소 30건)")
        st.caption("예시: `python main.py --all-gu --ym 202503 --types 매매`")
        return

    # 모델 성능 지표
    col1, col2, col3 = st.columns(3)
    col1.metric("학습 데이터", f"{metrics['n']:,}건")
    col2.metric("평균 오차 (MAE)", f"{int(metrics['mae']):,}만원")
    col3.metric("설명력 (R²)", f"{metrics['r2']:.3f}")

    st.divider()

    # 예측 입력 폼
    st.subheader("가격 예측")

    col1, col2 = st.columns(2)
    with col1:
        gu = st.selectbox("구 선택", list(SEOUL_GU_CODES.keys()))
        area = st.slider("전용면적 (㎡)", 10.0, 200.0, 84.0, 0.5)
    with col2:
        floor = st.slider("층", 1, 50, 10)
        build_year = st.slider("건축년도", 1970, 2024, 2000)

    if st.button("예측하기", use_container_width=True):
        pred, std = predict_price(model, le, features,
                                  gu, area, floor, build_year)

        if pred is None:
            st.error(std)
        else:
            st.success(f"예측 매매가: **{int(pred):,}만원** ({int(pred/10000*100)/100:.1f}억)")

            col1, col2, col3 = st.columns(3)
            col1.metric("예측가 하한", f"{int(pred - std):,}만원")
            col2.metric("예측가", f"{int(pred):,}만원")
            col3.metric("예측가 상한", f"{int(pred + std):,}만원")

            st.caption(f"건물나이: {date.today().year - build_year}년 | "
                      f"면적: {area}㎡ | {floor}층")

    st.divider()

    # 특성 중요도
    st.subheader("가격 결정 요인")
    st.caption("모델이 가격 예측에 가장 많이 활용한 특성")

    importance_df = get_feature_importance(model, features)

    import plotly.express as px
    fig = px.bar(
        importance_df,
        x="중요도", y="특성",
        orientation="h",
        color="중요도",
        color_continuous_scale="Blues",
        text=importance_df["중요도"].apply(lambda x: f"{x:.1%}"),
        height=300,
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        yaxis=dict(autorange="reversed"),
        coloraxis_showscale=False,
        margin=dict(l=0, r=40, t=10, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    # 면적별 예측가 비교
    st.subheader(f"{gu} 면적별 예측가 비교")
    area_range = [33, 49, 59, 84, 99, 114, 134, 165]
    rows = []
    for a in area_range:
        p, s = predict_price(model, le, features, gu, a, floor, build_year)
        if p:
            rows.append({"면적(㎡)": a, "예측가(만원)": int(p),
                         "하한": int(p-s), "상한": int(p+s)})

    if rows:
        df_area = pd.DataFrame(rows)
        fig2 = px.line(
            df_area, x="면적(㎡)", y="예측가(만원)",
            markers=True,
            error_y=df_area["상한"] - df_area["예측가(만원)"],
            error_y_minus=df_area["예측가(만원)"] - df_area["하한"],
            title=f"{gu} 면적별 예측 매매가",
            height=320,
        )
        st.plotly_chart(fig2, use_container_width=True)
