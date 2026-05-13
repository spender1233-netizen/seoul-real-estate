"""
자동 수집 + 리포팅 스케줄러
- 매주 월요일 07:00  → 주간 리포트
- 매월  1일  07:00  → 월간 리포트 + 전월 데이터 수집
- 매분기 첫날 07:00 → 분기 리포트
- 매년  1월1일 07:00→ 연간 리포트
실행: python scheduler.py
"""

import sys
import os
import logging
import time
from pathlib import Path
from datetime import date
from dateutil.relativedelta import relativedelta

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from config import SEOUL_GU_CODES
from database import init_db
from main import collect_gu, save_csv
from reporter import save_report

Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/scheduler.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ── 수집 작업 ──────────────────────────────────────────────

def job_collect_monthly():
    """매월 1일: 전월 서울 전체 수집"""
    api_key = os.getenv("MOLIT_API_KEY", "")
    if not api_key:
        logger.error("MOLIT_API_KEY 없음")
        return

    last_month = (date.today() - relativedelta(months=1)).strftime("%Y%m")
    logger.info(f"[월간 수집] {last_month} 시작")
    init_db()

    success, fail = 0, 0
    for gu in SEOUL_GU_CODES.keys():
        try:
            df = collect_gu(api_key, gu, last_month, ["매매", "전월세"])
            if not df.empty:
                save_csv(df, f"auto_{gu}_{last_month}")
                success += 1
            time.sleep(0.5)
        except Exception as e:
            logger.error(f"[{gu}] 수집 실패: {e}")
            fail += 1

    logger.info(f"[월간 수집 완료] 성공:{success}구 / 실패:{fail}구")


def job_collect_daily():
    """매일 06:00: 주요 구 당월 보완 수집"""
    api_key = os.getenv("MOLIT_API_KEY", "")
    if not api_key:
        return

    this_month = date.today().strftime("%Y%m")
    key_gu = ["강남구", "서초구", "송파구", "마포구", "용산구"]
    init_db()

    for gu in key_gu:
        try:
            collect_gu(api_key, gu, this_month, ["매매"])
            time.sleep(0.3)
        except Exception as e:
            logger.error(f"[{gu}] 일간 수집 실패: {e}")

    logger.info("[일간 보완 수집 완료]")


# ── 리포트 작업 ────────────────────────────────────────────

def job_report_weekly():
    logger.info("[주간 리포트] 생성 시작")
    try:
        path = save_report("weekly")
        logger.info(f"[주간 리포트] 완료: {path}")
    except Exception as e:
        logger.error(f"[주간 리포트] 실패: {e}")


def job_report_monthly():
    logger.info("[월간 리포트] 생성 시작")
    try:
        path = save_report("monthly")
        logger.info(f"[월간 리포트] 완료: {path}")
    except Exception as e:
        logger.error(f"[월간 리포트] 실패: {e}")


def job_report_quarterly():
    # 분기 첫달(1,4,7,10월) 1일만 실행
    today = date.today()
    if today.month in [1, 4, 7, 10]:
        logger.info("[분기 리포트] 생성 시작")
        try:
            path = save_report("quarterly")
            logger.info(f"[분기 리포트] 완료: {path}")
        except Exception as e:
            logger.error(f"[분기 리포트] 실패: {e}")


def job_report_yearly():
    logger.info("[연간 리포트] 생성 시작")
    try:
        path = save_report("yearly")
        logger.info(f"[연간 리포트] 완료: {path}")
    except Exception as e:
        logger.error(f"[연간 리포트] 실패: {e}")


# ── 이벤트 리스너 ──────────────────────────────────────────

def on_job_done(event):
    if event.exception:
        logger.error(f"작업 실패: {event.job_id} | {event.exception}")
    else:
        logger.info(f"작업 완료: {event.job_id}")


# ── 스케줄러 실행 ──────────────────────────────────────────

def run_scheduler():
    scheduler = BlockingScheduler(timezone="Asia/Seoul")

    # 수집
    scheduler.add_job(job_collect_monthly, CronTrigger(day=1, hour=0, minute=5),
                      id="collect_monthly", name="서울 전체 월간 수집",
                      misfire_grace_time=3600)

    scheduler.add_job(job_collect_daily, CronTrigger(hour=6, minute=0),
                      id="collect_daily", name="주요 구 일간 보완",
                      misfire_grace_time=1800)

    # 리포트 - 매주 월요일 07:00
    scheduler.add_job(job_report_weekly, CronTrigger(day_of_week="mon", hour=7, minute=0),
                      id="report_weekly", name="주간 리포트",
                      misfire_grace_time=3600)

    # 리포트 - 매월 1일 07:30 (수집 후)
    scheduler.add_job(job_report_monthly, CronTrigger(day=1, hour=7, minute=30),
                      id="report_monthly", name="월간 리포트",
                      misfire_grace_time=3600)

    # 리포트 - 매월 1일 08:00 (분기 해당월만 실행)
    scheduler.add_job(job_report_quarterly, CronTrigger(day=1, hour=8, minute=0),
                      id="report_quarterly", name="분기 리포트",
                      misfire_grace_time=3600)

    # 리포트 - 매년 1월 1일 09:00
    scheduler.add_job(job_report_yearly, CronTrigger(month=1, day=1, hour=9, minute=0),
                      id="report_yearly", name="연간 리포트",
                      misfire_grace_time=3600)

    scheduler.add_listener(on_job_done, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    logger.info("=" * 60)
    logger.info("자동 수집 + 리포팅 스케줄러 시작")
    logger.info("  매일    06:00 → 주요 구 보완 수집")
    logger.info("  매주 월 07:00 → 주간 리포트 생성")
    logger.info("  매월  1 00:05 → 서울 전체 월간 수집")
    logger.info("  매월  1 07:30 → 월간 리포트 생성")
    logger.info("  분기  1 08:00 → 분기 리포트 생성 (1/4/7/10월)")
    logger.info("  1월   1 09:00 → 연간 리포트 생성")
    logger.info("  종료: Ctrl+C")
    logger.info("=" * 60)

    for job in scheduler.get_jobs():
        logger.info(f"  [{job.name}] 다음 실행: {job.next_run_time}")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("스케줄러 종료")
        scheduler.shutdown()


# ── 즉시 테스트 ───────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--now",    action="store_true", help="지금 즉시 실행")
    p.add_argument("--report", choices=["weekly","monthly","quarterly","yearly","all"],
                   default="monthly", help="즉시 생성할 리포트 종류")
    args = p.parse_args()

    if args.now:
        print(f"\n리포트 즉시 생성: {args.report}\n")
        if args.report == "all":
            for period in ["weekly", "monthly", "quarterly", "yearly"]:
                save_report(period)
        else:
            path = save_report(args.report)
            print(f"\n생성 완료! 브라우저로 열기:\n{Path(path).resolve()}")
    else:
        run_scheduler()
