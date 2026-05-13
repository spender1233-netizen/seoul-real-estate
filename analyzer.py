"""
3단계: 부동산 데이터 분석
- 구별/동별 평균 매매가
- 월별 가격 추세
- 면적별 단가 (㎡당)
- 전세가율
- 단지별 히스토리
- 이상치 탐지
"""

import logging
import pandas as pd
import numpy as np
from db_save import query_to_df

logger = logging.getLogger(__name__)


# ── 1. 기본 통계 ───────────────────────────────────────────

def stats_by_gu() -> pd.DataFrame:
    """구별 매매가 통계"""
    df = query_to_df("""
        SELECT
            gu                          AS 구,
            COUNT(*)                    AS 거래건수,
            ROUND(AVG(price))           AS 평균가,
            ROUND(MIN(price))           AS 최저가,
            ROUND(MAX(price))           AS 최고가
        FROM apt_trade
        WHERE price IS NOT NULL
        GROUP BY gu
        ORDER BY 평균가 DESC
    """)
    return df


def stats_by_dong(gu: str) -> pd.DataFrame:
    """특정 구의 동별 매매가 통계
    - 법정동(역삼동, 대치동)이 있으면 법정동 기준 집계
    - API가 아파트 동호수(502동)를 반환하면 아파트명+동호수로 표시
    """
    df = query_to_df("""
        SELECT
            gu                          AS 구,
            dong                        AS 법정동,
            apt_name                    AS 아파트,
            COUNT(*)                    AS 거래건수,
            ROUND(AVG(price))           AS 평균가,
            ROUND(MIN(price))           AS 최저가,
            ROUND(MAX(price))           AS 최고가
        FROM apt_trade
        WHERE gu = ? AND price IS NOT NULL
        GROUP BY dong, apt_name
        ORDER BY 평균가 DESC
    """, (gu,))

    if df.empty:
        return df

    # 동 이름이 숫자(아파트 동호수)인지 법정동인지 구분
    import re as _re
    def make_label(row):
        dong = str(row["법정동"]).strip()
        apt  = str(row["아파트"]).strip()
        # 숫자로만 구성되거나 "숫자동" 패턴이면 아파트 동호수
        if _re.match(r"^\d+동?$", dong) or _re.match(r"^\d+$", dong):
            return f"{apt} ({dong})"  # 예: 은마아파트 (502동)
        else:
            return dong               # 예: 역삼동

    df["동"] = df.apply(make_label, axis=1)
    return df[["동", "거래건수", "평균가", "최저가", "최고가"]]


# ── 2. 월별 추세 ───────────────────────────────────────────

def monthly_trend(gu: str = None) -> pd.DataFrame:
    """월별 평균 매매가 추세"""
    where = "WHERE price IS NOT NULL"
    params = ()
    if gu:
        where += " AND gu = ?"
        params = (gu,)

    df = query_to_df(f"""
        SELECT
            trade_year   AS 년,
            trade_month  AS 월,
            COUNT(*)     AS 거래건수,
            ROUND(AVG(price))   AS 평균가,
            ROUND(MIN(price))   AS 최저가,
            ROUND(MAX(price))   AS 최고가
        FROM apt_trade
        {where}
        GROUP BY trade_year, trade_month
        ORDER BY trade_year, trade_month
    """, params)

    if not df.empty:
        df["전월대비"] = df["평균가"].diff()
        df["전월대비(%)"] = (df["평균가"].pct_change() * 100).round(2)
    return df


# ── 3. 면적별 단가 ─────────────────────────────────────────

def price_per_sqm(gu: str = None) -> pd.DataFrame:
    """면적 구간별 ㎡당 단가"""
    where = "WHERE price IS NOT NULL AND area IS NOT NULL AND area > 0"
    params = ()
    if gu:
        where += " AND gu = ?"
        params = (gu,)

    df = query_to_df(f"""
        SELECT
            CASE
                WHEN area < 40  THEN '~40㎡'
                WHEN area < 60  THEN '40~60㎡'
                WHEN area < 85  THEN '60~85㎡'
                WHEN area < 115 THEN '85~115㎡'
                ELSE '115㎡~'
            END                         AS 면적구간,
            COUNT(*)                    AS 거래건수,
            ROUND(AVG(price / area))    AS 평균단가_만원per㎡,
            ROUND(AVG(price))           AS 평균거래가
        FROM apt_trade
        {where}
        GROUP BY 면적구간
        ORDER BY MIN(area)
    """, params)
    return df


# ── 4. 단지별 히스토리 ─────────────────────────────────────

def apt_history(apt_name: str, area: float = None) -> pd.DataFrame:
    """특정 단지의 거래 히스토리"""
    where = "WHERE apt_name LIKE ?"
    params = [f"%{apt_name}%"]

    if area:
        where += " AND ABS(area - ?) < 3"
        params.append(area)

    df = query_to_df(f"""
        SELECT
            gu, dong, apt_name  AS 아파트,
            area                AS 전용면적,
            floor               AS 층,
            price               AS 거래금액,
            trade_date          AS 거래일자,
            trade_type          AS 거래유형
        FROM apt_trade
        {where}
        ORDER BY trade_date DESC
        LIMIT 50
    """, tuple(params))
    return df


# ── 5. 전세가율 ────────────────────────────────────────────

def jeonse_ratio(gu: str = None) -> pd.DataFrame:
    """전세가율 = 전세보증금 / 매매가 (단지+면적 기준 매칭)"""
    where_trade = "WHERE t.price IS NOT NULL"
    where_rent  = "WHERE r.deposit IS NOT NULL AND r.deal_type = '전세'"
    params = ()

    if gu:
        where_trade += " AND t.gu = ?"
        where_rent  += " AND r.gu = ?"
        params = (gu, gu)

    df = query_to_df(f"""
        SELECT
            t.gu                                        AS 구,
            t.apt_name                                  AS 아파트,
            ROUND(t.area)                               AS 면적,
            ROUND(AVG(t.price))                         AS 평균매매가,
            ROUND(AVG(r.deposit))                       AS 평균전세가,
            ROUND(AVG(r.deposit) * 100.0 / AVG(t.price), 1) AS 전세가율
        FROM apt_trade t
        JOIN apt_rent r
          ON t.apt_name = r.apt_name
         AND ABS(t.area - r.area) < 3
         AND t.gu = r.gu
        {where_trade.replace('WHERE', 'WHERE t.price IS NOT NULL AND')}
        GROUP BY t.gu, t.apt_name, ROUND(t.area)
        HAVING 평균매매가 > 0 AND 평균전세가 > 0
        ORDER BY 전세가율 DESC
        LIMIT 30
    """, params)
    return df


# ── 6. 이상치 탐지 ─────────────────────────────────────────

def detect_outliers(gu: str = None, threshold: float = 2.5) -> pd.DataFrame:
    """
    Z-score 기반 이상 거래 탐지
    같은 단지+면적 그룹에서 평균 대비 threshold 표준편차 이상 벗어난 거래
    """
    where = "WHERE price IS NOT NULL AND area IS NOT NULL"
    params = ()
    if gu:
        where += " AND gu = ?"
        params = (gu,)

    df = query_to_df(f"""
        SELECT
            gu, dong, apt_name AS 아파트,
            area AS 전용면적, floor AS 층,
            price AS 거래금액, trade_date AS 거래일자,
            trade_type AS 거래유형
        FROM apt_trade
        {where}
    """, params)

    if df.empty:
        return pd.DataFrame()

    # 단지+면적 그룹별 Z-score 계산
    df["그룹키"] = df["아파트"] + "_" + df["전용면적"].round(0).astype(str)
    group_stats = df.groupby("그룹키")["거래금액"].agg(["mean", "std"]).reset_index()
    group_stats.columns = ["그룹키", "그룹평균", "그룹표준편차"]

    df = df.merge(group_stats, on="그룹키")
    df = df[df["그룹표준편차"] > 0].copy()
    df["Z스코어"] = ((df["거래금액"] - df["그룹평균"]) / df["그룹표준편차"]).abs().round(2)

    outliers = df[df["Z스코어"] >= threshold].copy()
    outliers["시세대비(%)"] = ((outliers["거래금액"] / df["그룹평균"] - 1) * 100).round(1)
    outliers = outliers.sort_values("Z스코어", ascending=False)

    return outliers[["gu", "아파트", "전용면적", "층", "거래금액", "그룹평균", "시세대비(%)", "Z스코어", "거래일자"]].head(20)


# ── 전체 리포트 출력 ───────────────────────────────────────

def print_report(gu: str = None):
    label = gu if gu else "서울 전체"
    print(f"\n{'='*60}")
    print(f"  📊 부동산 분석 리포트 | {label}")
    print(f"{'='*60}")

    # 구별 통계
    print("\n[1] 구별 평균 매매가 (만원)")
    df = stats_by_gu()
    if not df.empty:
        for _, r in df.iterrows():
            print(f"  {r['구']:<6} | 거래 {r['거래건수']:>4}건 | 평균 {int(r['평균가']):>9,} | 최고 {int(r['최고가']):>9,}")

    # 동별 통계
    if gu:
        print(f"\n[2] {gu} 동별 평균 매매가 TOP 10 (만원)")
        df2 = stats_by_dong(gu)
        for _, r in df2.head(10).iterrows():
            print(f"  {r['동']:<8} | 거래 {r['거래건수']:>3}건 | 평균 {int(r['평균가']):>9,}")

    # 면적별 단가
    print(f"\n[3] 면적별 ㎡당 단가 (만원/㎡)")
    df3 = price_per_sqm(gu)
    if not df3.empty:
        for _, r in df3.iterrows():
            print(f"  {r['면적구간']:<10} | {r['거래건수']:>4}건 | {int(r['평균단가_만원per㎡']):>5,}만원/㎡")

    # 월별 추세
    print(f"\n[4] 월별 거래 추세")
    df4 = monthly_trend(gu)
    if not df4.empty:
        for _, r in df4.iterrows():
            chg = f"({r['전월대비(%)']:+.1f}%)" if pd.notna(r['전월대비(%)']) else ""
            print(f"  {int(r['년'])}-{int(r['월']):02d} | 거래 {int(r['거래건수']):>4}건 | 평균 {int(r['평균가']):>9,} {chg}")

    # 이상치
    print(f"\n[5] 이상 거래 탐지 (시세 대비 ±2.5σ 이상)")
    df5 = detect_outliers(gu)
    if not df5.empty:
        for _, r in df5.head(5).iterrows():
            print(f"  {str(r['아파트'])[:12]:<12} | {r['거래금액']:>8,}만원 | 시세대비 {r['시세대비(%)']:+.1f}% | Z={r['Z스코어']}")
    else:
        print("  이상 거래 없음")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    import sys
    gu = sys.argv[1] if len(sys.argv) > 1 else None
    print_report(gu)
