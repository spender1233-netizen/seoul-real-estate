"""
아파트 전월세 실거래가 수집기
국토부 API: getRTMSDataSvcAptRentDev
"""

import time
import logging
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import datetime

from config import REQUEST_DELAY, MAX_RETRIES, PAGE_SIZE

logger = logging.getLogger(__name__)

BASE_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptRentDev/getRTMSDataSvcAptRentDev"


def fetch_rent_page(api_key: str, gu_code: str, yearmonth: str, page: int = 1) -> dict:
    """전월세 실거래가 단일 페이지 요청"""
    params = {
        "serviceKey":  api_key,
        "LAWD_CD":     gu_code,
        "DEAL_YMD":    yearmonth,
        "pageNo":      page,
        "numOfRows":   PAGE_SIZE,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(BASE_URL, params=params, timeout=10)
            resp.raise_for_status()
            return _parse_rent_xml(resp.text, page)

        except requests.exceptions.Timeout:
            logger.warning(f"타임아웃 (시도 {attempt}/{MAX_RETRIES}) - 구코드:{gu_code} {yearmonth}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"요청 오류 (시도 {attempt}/{MAX_RETRIES}): {e}")

        if attempt < MAX_RETRIES:
            time.sleep(2 ** attempt)

    logger.error(f"최대 재시도 초과 - 구코드:{gu_code} {yearmonth} 페이지:{page}")
    return {"items": [], "total_count": 0, "page": page}


def _parse_rent_xml(xml_text: str, page: int) -> dict:
    """전월세 XML 응답 파싱"""
    try:
        root = ET.fromstring(xml_text)

        result_code = root.findtext(".//resultCode", "")
        result_msg  = root.findtext(".//resultMsg", "")
        if result_code not in ("00", "0000", "000"):
            raise ValueError(f"API 오류 [{result_code}]: {result_msg}")

        total_count = int(root.findtext(".//totalCount", "0"))
        items = []

        for item in root.findall(".//item"):
            # 보증금과 월세로 전세/월세 구분
            monthly_rent = _price(item, "월세금액")
            deal_type = "월세" if monthly_rent and monthly_rent > 0 else "전세"

            row = {
                # 지역
                "지역코드":   _text(item, "지역코드"),
                "법정동":     _text(item, "법정동"),
                # 단지 정보
                "아파트명":   _text(item, "아파트"),
                "건축년도":   _int(item, "건축년도"),
                "층":         _int(item, "층"),
                "전용면적":   _float(item, "전용면적"),
                # 거래 정보
                "보증금":     _price(item, "보증금액"),   # 만원
                "월세":       monthly_rent,               # 만원 (전세는 0)
                "거래년":     _int(item, "년"),
                "거래월":     _int(item, "월"),
                "거래일":     _int(item, "일"),
                # 메타
                "수집시각":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "거래분류":   deal_type,
            }
            items.append(row)

        return {"items": items, "total_count": total_count, "page": page}

    except ET.ParseError as e:
        logger.error(f"XML 파싱 오류: {e}\n원문(앞 300자): {xml_text[:300]}")
        return {"items": [], "total_count": 0, "page": page}


def fetch_rent_all(api_key: str, gu_code: str, yearmonth: str) -> pd.DataFrame:
    """특정 구의 특정 월 전월세 전체 데이터 수집"""
    all_items = []
    page = 1

    while True:
        result = fetch_rent_page(api_key, gu_code, yearmonth, page)
        all_items.extend(result["items"])

        fetched_so_far = (page - 1) * PAGE_SIZE + len(result["items"])
        total = result["total_count"]

        logger.info(f"  전월세 {gu_code} {yearmonth} - {fetched_so_far}/{total}건 수집")

        if fetched_so_far >= total or not result["items"]:
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    if not all_items:
        return pd.DataFrame()

    df = pd.DataFrame(all_items)
    df["거래일자"] = pd.to_datetime(
        df["거래년"].astype(str) + "-" +
        df["거래월"].astype(str).str.zfill(2) + "-" +
        df["거래일"].astype(str).str.zfill(2),
        errors="coerce"
    )
    return df


# ── 내부 헬퍼 ──────────────────────────────────────────────

def _text(item, tag: str) -> str:
    val = item.findtext(tag, "")
    return val.strip() if val else ""

def _int(item, tag: str):
    val = _text(item, tag)
    try:
        return int(val)
    except (ValueError, TypeError):
        return None

def _float(item, tag: str):
    val = _text(item, tag)
    try:
        return float(val)
    except (ValueError, TypeError):
        return None

def _price(item, tag: str):
    val = _text(item, tag).replace(",", "")
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
