"""
수집된 DataFrame을 SQLite DB에 저장

핵심 전략: INSERT OR IGNORE
  - UNIQUE 제약 조건에 걸리면 조용히 스킵 (중복 방지)
  - 새 데이터만 삽입
"""

import sqlite3
import logging
import pandas as pd
from datetime import datetime

from database import get_conn

logger = logging.getLogger(__name__)


# ── 매매 저장 ──────────────────────────────────────────────

TRADE_INSERT = """
    INSERT OR IGNORE INTO apt_trade (
        gu, dong, region_code,
        apt_name, build_year, floor, area,
        price, trade_type, trade_date,
        trade_year, trade_month, trade_day,
        collected_at
    ) VALUES (
        :gu, :dong, :region_code,
        :apt_name, :build_year, :floor, :area,
        :price, :trade_type, :trade_date,
        :trade_year, :trade_month, :trade_day,
        :collected_at
    )
"""


def save_trade(df: pd.DataFrame) -> dict:
    """
    매매 DataFrame → DB 저장

    Returns:
        {"inserted": int, "skipped": int, "total": int}
    """
    if df.empty:
        return {"inserted": 0, "skipped": 0, "total": 0}

    rows = []
    for _, r in df.iterrows():
        rows.append({
            "gu":           r.get("구", ""),
            "dong":         r.get("법정동", ""),
            "region_code":  r.get("지역코드", ""),
            "apt_name":     r.get("아파트명", ""),
            "build_year":   _safe_int(r.get("건축년도")),
            "floor":        _safe_int(r.get("층")),
            "area":         _safe_float(r.get("전용면적")),
            "price":        _safe_int(r.get("거래금액")),
            "trade_type":   r.get("거래유형", ""),
            "trade_date":   _safe_date(r.get("거래일자")),
            "trade_year":   _safe_int(r.get("거래년")),
            "trade_month":  _safe_int(r.get("거래월")),
            "trade_day":    _safe_int(r.get("거래일")),
            "collected_at": r.get("수집시각", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        })

    conn = get_conn()
    try:
        before = _count(conn, "apt_trade")
        conn.executemany(TRADE_INSERT, rows)
        conn.commit()
        after = _count(conn, "apt_trade")

        inserted = after - before
        skipped  = len(rows) - inserted
        logger.info(f"매매 저장 | 신규:{inserted}건 / 중복스킵:{skipped}건 / 전체DB:{after}건")
        return {"inserted": inserted, "skipped": skipped, "total": len(rows)}
    finally:
        conn.close()


# ── 전월세 저장 ────────────────────────────────────────────

RENT_INSERT = """
    INSERT OR IGNORE INTO apt_rent (
        gu, dong, region_code,
        apt_name, build_year, floor, area,
        deal_type, deposit, monthly_rent,
        trade_date, trade_year, trade_month, trade_day,
        collected_at
    ) VALUES (
        :gu, :dong, :region_code,
        :apt_name, :build_year, :floor, :area,
        :deal_type, :deposit, :monthly_rent,
        :trade_date, :trade_year, :trade_month, :trade_day,
        :collected_at
    )
"""


def save_rent(df: pd.DataFrame) -> dict:
    """전월세 DataFrame → DB 저장"""
    if df.empty:
        return {"inserted": 0, "skipped": 0, "total": 0}

    rows = []
    for _, r in df.iterrows():
        rows.append({
            "gu":           r.get("구", ""),
            "dong":         r.get("법정동", ""),
            "region_code":  r.get("지역코드", ""),
            "apt_name":     r.get("아파트명", ""),
            "build_year":   _safe_int(r.get("건축년도")),
            "floor":        _safe_int(r.get("층")),
            "area":         _safe_float(r.get("전용면적")),
            "deal_type":    r.get("거래분류", ""),
            "deposit":      _safe_int(r.get("보증금")),
            "monthly_rent": _safe_int(r.get("월세")),
            "trade_date":   _safe_date(r.get("거래일자")),
            "trade_year":   _safe_int(r.get("거래년")),
            "trade_month":  _safe_int(r.get("거래월")),
            "trade_day":    _safe_int(r.get("거래일")),
            "collected_at": r.get("수집시각", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        })

    conn = get_conn()
    try:
        before = _count(conn, "apt_rent")
        conn.executemany(RENT_INSERT, rows)
        conn.commit()
        after = _count(conn, "apt_rent")

        inserted = after - before
        skipped  = len(rows) - inserted
        logger.info(f"전월세 저장 | 신규:{inserted}건 / 중복스킵:{skipped}건 / 전체DB:{after}건")
        return {"inserted": inserted, "skipped": skipped, "total": len(rows)}
    finally:
        conn.close()


# ── 수집 이력 저장 ─────────────────────────────────────────

def save_collect_log(gu: str, yearmonth: str, deal_kind: str, count: int):
    """수집 이력 기록 (중복 수집 추적용)"""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO collect_log
                (gu, yearmonth, deal_kind, record_count, collected_at)
            VALUES (?, ?, ?, ?, ?)
        """, (gu, yearmonth, deal_kind, count, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    finally:
        conn.close()


# ── DB 조회 유틸 ───────────────────────────────────────────

def query_to_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    """SQL 조회 결과를 DataFrame으로 반환"""
    conn = get_conn()
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def get_db_stats() -> dict:
    """DB 현황 요약"""
    conn = get_conn()
    try:
        trade_count = conn.execute("SELECT COUNT(*) FROM apt_trade").fetchone()[0]
        rent_count  = conn.execute("SELECT COUNT(*) FROM apt_rent").fetchone()[0]
        gu_list     = [r[0] for r in conn.execute(
            "SELECT DISTINCT gu FROM apt_trade ORDER BY gu"
        ).fetchall()]
        return {
            "매매건수": trade_count,
            "전월세건수": rent_count,
            "수집된구": gu_list,
        }
    finally:
        conn.close()


# ── 내부 헬퍼 ──────────────────────────────────────────────

def _count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

def _safe_int(val):
    try:
        return int(val) if pd.notna(val) else None
    except (ValueError, TypeError):
        return None

def _safe_float(val):
    try:
        return float(val) if pd.notna(val) else None
    except (ValueError, TypeError):
        return None

def _safe_date(val) -> str:
    """Timestamp / 문자열 → 'YYYY-MM-DD' 문자열"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return pd.Timestamp(val).strftime("%Y-%m-%d")
    except Exception:
        return str(val)
