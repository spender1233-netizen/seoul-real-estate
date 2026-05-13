"""
아파트 전월세 실거래가 수집기
국토부 API: getRTMSDataSvcAptRentDev

전세(월세=0)와 월세를 모두 수집하며 거래분류 컬럼으로 구분한다.
"""

import time
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional

import pandas as pd
import requests

from config import MAX_RETRIES, PAGE_SIZE, REQUEST_DELAY

logger = logging.getLogger(__name__)

BASE_URL = (
    "https://apis.data.go.kr/1613000"
    "/RTMSDataSvcAptRentDev/getRTMSDataSvcAptRentDev"
)


def fetch_rent_page(
    api_key: str,
    gu_code: str,
    yearmonth: str,
    page: int = 1,
) -> dict:
    """국토부 API에서 전월세 실거래가 단일 페이지를 요청한다.

    Args:
        api_key:   공공데이터 포털 서비스 키
        gu_code:   법정동코드 앞 5자리
        yearmonth: 조회 년월 (YYYYMM)
        page:      페이지 번호

    Returns:
        {"items": list[dict], "total_count": int, "page": int}
    """
    params = {
        "serviceKey": api_key,
        "LAWD_CD":    gu_code,
        "DEAL_YMD":   yearmonth,
        "pageNo":     page,
        "numOfRows":  PAGE_SIZE,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(BASE_URL, params=params, timeout=10)
            resp.raise_for_status()
            return _parse_rent_xml(resp.text, page)

        except requests.exceptions.Timeout:
            logger.warning(
                f"타임아웃 (시도 {attempt}/{MAX_RETRIES}) "
                f"- 구코드:{gu_code} {yearmonth}"
            )
        except requests.exceptions.RequestException as e:
            logger.warning(f"요청 오류 (시도 {attempt}/{MAX_RETRIES}): {e}")

        if attempt < MAX_RETRIES:
            time.sleep(2 ** attempt)

    logger.error(f"최대 재시도 초과 - 구코드:{gu_code} {yearmonth} 페이지:{page}")
    return {"items": [], "total_count": 0, "page": page}


def fetch_rent_all(
    api_key: str,
    gu_code: str,
    yearmonth: str,
) -> pd.DataFrame:
    """특정 구의 특정 월 전월세 실거래가 전체를 수집한다.

    Args:
        api_key:   공공데이터 포털 서비스 키
        gu_code:   법정동코드 앞 5자리
        yearmonth: 조회 년월 (YYYYMM)

    Returns:
        수집된 전월세 거래 DataFrame.
        거래분류 컬럼: '전세' 또는 '월세'
        데이터가 없으면 빈 DataFrame 반환.
    """
    all_items: list[dict] = []
    page = 1

    while True:
        result = fetch_rent_page(api_key, gu_code, yearmonth, page)
        all_items.extend(result["items"])

        fetched_so_far = (page - 1) * PAGE_SIZE + len(result["items"])
        total = result["total_count"]

        logger.info(
            f"  전월세 {gu_code} {yearmonth} "
            f"- {fetched_so_far}/{total}건 수집"
        )

        if fetched_so_far >= total or not result["items"]:
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    if not all_items:
        return pd.DataFrame()

    df = pd.DataFrame(all_items)
    df["거래일자"] = pd.to_datetime(
        df["거래년"].astype(str) + "-"
        + df["거래월"].astype(str).str.zfill(2) + "-"
        + df["거래일"].astype(str).str.zfill(2),
        errors="coerce",
    )
    return df


def _parse_rent_xml(xml_text: str, page: int) -> dict:
    """전월세 XML 응답을 파싱한다.

    월세금액이 0이면 전세, 0 초과면 월세로 거래분류를 자동 판별한다.
    """
    try:
        root = ET.fromstring(xml_text)

        result_code = root.findtext(".//resultCode", "")
        result_msg  = root.findtext(".//resultMsg", "")
        if result_code not in ("00", "0000", "000"):
            raise ValueError(f"API 오류 [{result_code}]: {result_msg}")

        total_count = int(root.findtext(".//totalCount", "0"))
        items: list[dict] = []

        for item in root.findall(".//item"):
            monthly_rent = _price(item, "월세금액")
            deal_type = "월세" if monthly_rent and monthly_rent > 0 else "전세"

            row = {
                "지역코드": _text(item, "지역코드"),
                "법정동":   _text(item, "법정동"),
                "아파트명": _text(item, "아파트"),
                "건축년도": _int(item, "건축년도"),
                "층":       _int(item, "층"),
                "전용면적": _float(item, "전용면적"),
                "보증금":   _price(item, "보증금액"),
                "월세":     monthly_rent,
                "거래년":   _int(item, "년"),
                "거래월":   _int(item, "월"),
                "거래일":   _int(item, "일"),
                "수집시각": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "거래분류": deal_type,
            }
            items.append(row)

        return {"items": items, "total_count": total_count, "page": page}

    except ET.ParseError as e:
        logger.error(f"XML 파싱 오류: {e}\n원문(앞 300자): {xml_text[:300]}")
        return {"items": [], "total_count": 0, "page": page}


def _text(item: ET.Element, tag: str) -> str:
    """XML 요소에서 텍스트를 안전하게 추출한다."""
    val = item.findtext(tag, "")
    return val.strip() if val else ""


def _int(item: ET.Element, tag: str) -> Optional[int]:
    """XML 요소에서 정수를 안전하게 추출한다."""
    try:
        return int(_text(item, tag))
    except (ValueError, TypeError):
        return None


def _float(item: ET.Element, tag: str) -> Optional[float]:
    """XML 요소에서 실수를 안전하게 추출한다."""
    try:
        return float(_text(item, tag))
    except (ValueError, TypeError):
        return None


def _price(item: ET.Element, tag: str) -> Optional[int]:
    """XML 요소에서 금액을 추출한다. '85,000' → 85000."""
    try:
        return int(_text(item, tag).replace(",", ""))
    except (ValueError, TypeError):
        return None
