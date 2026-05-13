"""
서울 부동산 실거래가 수집기 - 메인 실행 스크립트

사용법:
    python main.py --gu 강남구 --ym 202503 --types 매매
    python main.py --gu 강남구 --months 3
    python main.py --all-gu --ym 202503
    python main.py --db-stats
    python main.py --demo
"""

import os
import sys
import argparse
import logging
import time
from pathlib import Path
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

from dotenv import load_dotenv
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from config import SEOUL_GU_CODES
from collectors import fetch_trade_all, fetch_rent_all
from database import init_db
from db_save import save_trade, save_rent, save_collect_log, get_db_stats

# ── 로깅 설정 ──────────────────────────────────────────────

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/collector.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ── 수집 + 저장 함수 ───────────────────────────────────────

def collect_gu(api_key: str, gu_name: str, yearmonth: str, deal_types: list) -> pd.DataFrame:
    """단일 구 수집 + DB 저장"""
    gu_code = SEOUL_GU_CODES.get(gu_name)
    if not gu_code:
        logger.error(f"알 수 없는 구 이름: {gu_name}")
        return pd.DataFrame()

    frames = []
    logger.info(f"[{gu_name}] {yearmonth} 수집 시작")

    if "매매" in deal_types:
        df_trade = fetch_trade_all(api_key, gu_code, yearmonth)
        if not df_trade.empty:
            df_trade["구"] = gu_name
            frames.append(df_trade)
            result = save_trade(df_trade)
            save_collect_log(gu_name, yearmonth, "매매", result["inserted"])
            logger.info(f"  ✓ 매매 {len(df_trade)}건 수집 | DB 신규저장:{result['inserted']}건")
        else:
            logger.info(f"  - 매매 데이터 없음")

    if "전월세" in deal_types:
        df_rent = fetch_rent_all(api_key, gu_code, yearmonth)
        if not df_rent.empty:
            df_rent["구"] = gu_name
            frames.append(df_rent)
            result = save_rent(df_rent)
            save_collect_log(gu_name, yearmonth, "전월세", result["inserted"])
            logger.info(f"  ✓ 전월세 {len(df_rent)}건 수집 | DB 신규저장:{result['inserted']}건")
        else:
            logger.info(f"  - 전월세 데이터 없음")

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def collect_months(api_key: str, gu_names: list, months: int, deal_types: list) -> pd.DataFrame:
    """최근 N개월 수집"""
    today = date.today()
    yearmonths = [
        (today - relativedelta(months=i)).strftime("%Y%m")
        for i in range(months)
    ]

    all_frames = []
    total = len(gu_names) * len(yearmonths)
    done = 0

    for ym in yearmonths:
        for gu in gu_names:
            df = collect_gu(api_key, gu, ym, deal_types)
            if not df.empty:
                all_frames.append(df)
            done += 1
            logger.info(f"진행: {done}/{total}")
            time.sleep(0.3)

    return pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame()


# ── 결과 출력 ──────────────────────────────────────────────

def save_csv(df: pd.DataFrame, label: str):
    Path("data").mkdir(exist_ok=True)
    filename = f"data/{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    df.to_csv(filename, index=False, encoding="utf-8-sig")
    logger.info(f"CSV 저장: {filename}")


def print_summary(df: pd.DataFrame):
    if df.empty:
        print("\n수집된 데이터가 없습니다.")
        return

    print("\n" + "=" * 55)
    print(f"  수집 완료  |  총 {len(df):,}건")
    print("=" * 55)

    if "거래분류" in df.columns:
        print("\n[거래 유형별]")
        for t, cnt in df["거래분류"].value_counts().items():
            print(f"  {t:<8} {cnt:>6,}건")

    if "구" in df.columns:
        print("\n[구별 수집 현황]")
        for gu, cnt in df.groupby("구").size().sort_values(ascending=False).items():
            bar = "█" * min(int(cnt / 20), 20)
            print(f"  {gu:<6} {cnt:>5,}건  {bar}")

    trade_df = df[df.get("거래분류", pd.Series()) == "매매"] if "거래분류" in df.columns else pd.DataFrame()
    if not trade_df.empty and "거래금액" in trade_df.columns:
        prices = trade_df["거래금액"].dropna()
        if not prices.empty:
            print(f"\n[매매가 통계 (만원)]")
            print(f"  최소: {int(prices.min()):>10,}")
            print(f"  평균: {int(prices.mean()):>10,}")
            print(f"  중앙: {int(prices.median()):>10,}")
            print(f"  최대: {int(prices.max()):>10,}")

    print("=" * 55)


def print_db_stats():
    stats = get_db_stats()
    print("\n" + "=" * 55)
    print("  DB 현황")
    print("=" * 55)
    print(f"  매매   : {stats['매매건수']:>8,}건")
    print(f"  전월세 : {stats['전월세건수']:>8,}건")
    if stats["수집된구"]:
        print(f"\n  수집된 구 ({len(stats['수집된구'])}개):")
        print(f"  {', '.join(stats['수집된구'])}")
    print("=" * 55)


# ── 데모 모드 ──────────────────────────────────────────────

DEMO_XML_TRADE = """<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header>
  <body>
    <totalCount>2</totalCount>
    <items>
      <item>
        <지역코드>11680</지역코드><법정동>역삼동</법정동>
        <아파트>역삼래미안</아파트><건축년도>2002</건축년도>
        <층>15</층><전용면적>84.99</전용면적>
        <거래금액>185,000</거래금액><거래유형>중개거래</거래유형>
        <년>2025</년><월>3</월><일>5</일>
      </item>
      <item>
        <지역코드>11680</지역코드><법정동>대치동</법정동>
        <아파트>은마아파트</아파트><건축년도>1979</건축년도>
        <층>8</층><전용면적>76.79</전용면적>
        <거래금액>220,000</거래금액><거래유형>중개거래</거래유형>
        <년>2025</년><월>3</월><일>12</일>
      </item>
    </items>
  </body>
</response>"""


def run_demo():
    from collectors.trade_collector import _parse_trade_xml
    print("\n[ 데모 모드 - DB 저장 테스트 ]\n")

    init_db()
    result = _parse_trade_xml(DEMO_XML_TRADE, 1)
    df = pd.DataFrame(result["items"])
    df["구"] = "강남구"
    df["거래일자"] = pd.to_datetime(
        df["거래년"].astype(str) + "-" +
        df["거래월"].astype(str).str.zfill(2) + "-" +
        df["거래일"].astype(str).str.zfill(2)
    )

    r = save_trade(df)
    print(f"저장 결과 → 신규:{r['inserted']}건 / 중복스킵:{r['skipped']}건")

    # 중복 저장 테스트
    r2 = save_trade(df)
    print(f"재저장 시도 → 신규:{r2['inserted']}건 / 중복스킵:{r2['skipped']}건 (중복 방지 작동)")

    print_db_stats()
    print("\n✓ DB 저장 정상 작동!\n")


# ── CLI ────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="서울 아파트 실거래가 수집기")
    p.add_argument("--gu",       type=str)
    p.add_argument("--ym",       type=str)
    p.add_argument("--months",   type=int, default=1)
    p.add_argument("--all-gu",   action="store_true")
    p.add_argument("--types",    type=str, default="매매,전월세")
    p.add_argument("--db-stats", action="store_true", help="DB 현황만 출력")
    p.add_argument("--demo",     action="store_true")
    return p.parse_args()


def main():
    args = parse_args()

    if args.demo:
        run_demo()
        return

    if args.db_stats:
        print_db_stats()
        return

    load_dotenv()
    api_key = os.getenv("MOLIT_API_KEY", "")
    if not api_key or api_key == "여기에_발급받은_키_입력":
        print("\n[오류] .env 파일에 MOLIT_API_KEY를 설정해주세요.\n")
        sys.exit(1)

    # DB 초기화 (테이블 없으면 생성)
    init_db()

    deal_types = [t.strip() for t in args.types.split(",")]

    if args.all_gu:
        gu_names = list(SEOUL_GU_CODES.keys())
    elif args.gu:
        if args.gu not in SEOUL_GU_CODES:
            print(f"[오류] '{args.gu}'는 유효하지 않습니다.")
            sys.exit(1)
        gu_names = [args.gu]
    else:
        print("[오류] --gu 또는 --all-gu 옵션이 필요합니다.")
        sys.exit(1)

    yearmonth = args.ym or date.today().strftime("%Y%m")

    logger.info(f"수집 시작 | 구:{gu_names} | 기간:{yearmonth} | 유형:{deal_types}")

    if args.months > 1:
        df = collect_months(api_key, gu_names, args.months, deal_types)
    else:
        frames = [collect_gu(api_key, gu, yearmonth, deal_types) for gu in gu_names]
        df = pd.concat([f for f in frames if not f.empty], ignore_index=True) \
             if any(not f.empty for f in frames) else pd.DataFrame()

    print_summary(df)

    if not df.empty:
        save_csv(df, f"seoul_{'_'.join(gu_names[:3])}_{yearmonth}")

    # DB 현황 출력
    print_db_stats()


if __name__ == "__main__":
    main()
