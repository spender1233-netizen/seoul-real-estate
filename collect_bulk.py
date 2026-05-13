"""
대량 데이터 수집 스크립트
서울 25개 구 × 최근 6개월치 일괄 수집
실행: python collect_bulk.py
"""

import sys
import os
import time
import logging
from pathlib import Path
from datetime import date
from dateutil.relativedelta import relativedelta

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from config import SEOUL_GU_CODES
from database import init_db
from main import collect_gu, save_csv, print_summary
from db_save import get_db_stats
import pandas as pd

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bulk_collect.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def collect_bulk(months: int = 6, deal_types: list = None):
    if deal_types is None:
        deal_types = ["매매"]

    api_key = os.getenv("MOLIT_API_KEY", "")
    if not api_key:
        print("❌ MOLIT_API_KEY가 없습니다. .env 파일을 확인해주세요.")
        return

    # 수집할 년월 목록
    today = date.today()
    yearmonths = [
        (today - relativedelta(months=i)).strftime("%Y%m")
        for i in range(months)
    ]

    gu_names = list(SEOUL_GU_CODES.keys())
    total    = len(gu_names) * len(yearmonths)
    done     = 0
    success  = 0
    fail     = 0

    init_db()

    print(f"\n{'='*60}")
    print(f"  대량 수집 시작")
    print(f"  대상: 서울 {len(gu_names)}개 구 × {months}개월")
    print(f"  기간: {yearmonths[-1]} ~ {yearmonths[0]}")
    print(f"  유형: {', '.join(deal_types)}")
    print(f"  총 요청: 약 {total}회")
    print(f"  예상 시간: 약 {total * 0.8 / 60:.0f}~{total * 1.5 / 60:.0f}분")
    print(f"{'='*60}\n")

    all_frames = []

    for ym in yearmonths:
        logger.info(f"[{ym}] 수집 시작 ({yearmonths.index(ym)+1}/{months}개월)")
        for gu in gu_names:
            done += 1
            pct = done / total * 100
            try:
                df = collect_gu(api_key, gu, ym, deal_types)
                if not df.empty:
                    all_frames.append(df)
                    success += 1
                # 진행률 출력
                print(f"\r  진행: {done}/{total} ({pct:.0f}%) | 성공:{success} 실패:{fail} | 현재: {gu} {ym}", end="")
                time.sleep(0.3)
            except Exception as e:
                fail += 1
                logger.error(f"오류 [{gu} {ym}]: {e}")

        print()  # 줄바꿈

    # 최종 결과
    print(f"\n{'='*60}")
    print(f"  대량 수집 완료!")
    print(f"  성공: {success}건 / 실패: {fail}건")

    stats = get_db_stats()
    print(f"\n  DB 현황")
    print(f"  매매: {stats['매매건수']:,}건")
    print(f"  전월세: {stats['전월세건수']:,}건")
    print(f"  수집된 구: {len(stats['수집된구'])}개")
    print(f"{'='*60}\n")

    # 전체 CSV 저장
    if all_frames:
        df_all = pd.concat(all_frames, ignore_index=True)
        from datetime import datetime
        filename = f"data/bulk_seoul_{months}months_{datetime.now().strftime('%Y%m%d')}.csv"
        df_all.to_csv(filename, index=False, encoding="utf-8-sig")
        logger.info(f"전체 CSV 저장: {filename} ({len(df_all):,}건)")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="서울 전체 대량 수집")
    p.add_argument("--months", type=int, default=6,  help="수집 개월 수 (기본: 6)")
    p.add_argument("--types",  type=str, default="매매", help="수집 유형 (매매,전월세)")
    args = p.parse_args()

    deal_types = [t.strip() for t in args.types.split(",")]
    collect_bulk(months=args.months, deal_types=deal_types)
