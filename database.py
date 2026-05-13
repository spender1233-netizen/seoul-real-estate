"""
SQLite DB 초기화 및 스키마 정의

테이블 구조:
  apt_trade  - 아파트 매매 실거래
  apt_rent   - 아파트 전월세 실거래
  collect_log - 수집 이력 (중복 방지용)
"""

import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path("data/real_estate.db")


def get_conn() -> sqlite3.Connection:
    """DB 연결 반환 (없으면 자동 생성)"""
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row          # 딕셔너리처럼 컬럼명으로 접근 가능
    conn.execute("PRAGMA journal_mode=WAL") # 동시 읽기 성능 향상
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """테이블 생성 (이미 있으면 스킵)"""
    conn = get_conn()
    try:
        conn.executescript("""
            -- 매매 실거래
            CREATE TABLE IF NOT EXISTS apt_trade (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                -- 지역
                gu          TEXT NOT NULL,
                dong        TEXT,
                region_code TEXT,
                -- 단지
                apt_name    TEXT,
                build_year  INTEGER,
                floor       INTEGER,
                area        REAL,           -- 전용면적 (㎡)
                -- 거래
                price       INTEGER,        -- 만원 단위
                trade_type  TEXT,           -- 중개거래 / 직거래
                trade_date  TEXT,           -- YYYY-MM-DD
                trade_year  INTEGER,
                trade_month INTEGER,
                trade_day   INTEGER,
                -- 메타
                collected_at TEXT,
                -- 중복 방지: 같은 단지+면적+층+날짜+금액은 동일 거래
                UNIQUE(apt_name, area, floor, trade_date, price)
            );

            -- 전월세 실거래
            CREATE TABLE IF NOT EXISTS apt_rent (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                -- 지역
                gu            TEXT NOT NULL,
                dong          TEXT,
                region_code   TEXT,
                -- 단지
                apt_name      TEXT,
                build_year    INTEGER,
                floor         INTEGER,
                area          REAL,
                -- 거래
                deal_type     TEXT,         -- 전세 / 월세
                deposit       INTEGER,      -- 보증금 (만원)
                monthly_rent  INTEGER,      -- 월세 (만원, 전세=0)
                trade_date    TEXT,
                trade_year    INTEGER,
                trade_month   INTEGER,
                trade_day     INTEGER,
                -- 메타
                collected_at  TEXT,
                UNIQUE(apt_name, area, floor, trade_date, deposit, monthly_rent)
            );

            -- 수집 이력 (같은 구+월을 중복 수집 방지)
            CREATE TABLE IF NOT EXISTS collect_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                gu           TEXT NOT NULL,
                yearmonth    TEXT NOT NULL,
                deal_kind    TEXT NOT NULL,  -- 매매 / 전월세
                record_count INTEGER,
                collected_at TEXT,
                UNIQUE(gu, yearmonth, deal_kind)
            );

            -- 조회 성능을 위한 인덱스
            CREATE INDEX IF NOT EXISTS idx_trade_gu_date  ON apt_trade(gu, trade_date);
            CREATE INDEX IF NOT EXISTS idx_trade_apt      ON apt_trade(apt_name);
            CREATE INDEX IF NOT EXISTS idx_rent_gu_date   ON apt_rent(gu, trade_date);
            CREATE INDEX IF NOT EXISTS idx_rent_apt       ON apt_rent(apt_name);
        """)
        conn.commit()
        logger.info(f"DB 초기화 완료: {DB_PATH.resolve()}")
    finally:
        conn.close()
