"""
아파트 매매 실거래가 수집기
국토부 API: getRTMSDataSvcAptTradeDev

주요 기능:
    - 단일 페이지 API 요청 및 XML 파싱
    - 페이징 처리로 전체 데이터 자동 수집
    - 지수 백오프 재시도 로직
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
    "/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
)


def fetch_trade_page(
    api_key: str,
    gu_code: str,
    yearmonth: str,
    page: int = 1,
) -> dict:
    """국토부 API에서 매매 실거래가 단일 페이지를 요청한다.

    Args:
        api_key:    공공데이터 포털 서비스 키
        gu_code:    법정동코드 앞 5자리 (예: '11680' = 강남구)
        yearmonth:  조회 년월, YYYYMM 형식 (예: '202503')
        page:       페이지 번호 (1부터 시작)

    Returns:
        {
            "items":       list[dict],  # 파싱된 거래 데이터
            "total_count": int,         # 전체 건수
            "page":        int,         # 현재 페이지
        }

    Note:
        실패 시 MAX_RETRIES 횟수만큼 지수 백오프로 재시도한다.
        모든 시도가 실패하면 빈 items를 반환한다.
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
            return _parse_trade_xml(resp.text, page)

        except requests.exceptions.Timeout:
            logger.warning(
                f"타임아웃 (시도 {attempt}/{MAX_RETRIES}) "
                f"- 구코드:{gu_code} {yearmonth}"
            )
        except requests.exceptions.RequestException as e:
            logger.warning(f"요청 오류 (시도 {attempt}/{MAX_RETRIES}): {e}")

        if attempt < MAX_RETRIES:
            time.sleep(2 ** attempt)   # 지수 백오프: 2s → 4s → 8s

    logger.error(f"최대 재시도 초과 - 구코드:{gu_code} {yearmonth} 페이지:{page}")
    return {"items": [], "total_count": 0, "page": page}


def fetch_trade_all(
    api_key: str,
    gu_code: str,
    yearmonth: str,
) -> pd.DataFrame:
    """특정 구의 특정 월 매매 실거래가 전체를 수집한다.

    페이징을 자동으로 처리해 total_count에 도달할 때까지 반복 요청한다.

    Args:
        api_key:   공공데이터 포털 서비스 키
        gu_code:   법정동코드 앞 5자리
        yearmonth: 조회 년월 (YYYYMM)

    Returns:
        수집된 거래 데이터 DataFrame.
        컬럼: 지역코드, 법정동, 아파트명, 건축년도, 층, 전용면적,
              거래금액, 거래년, 거래월, 거래일, 거래유형, 수집시각,
              거래분류, 거래일자
        데이터가 없으면 빈 DataFrame 반환.
    """
    all_items: list[dict] = []
    page = 1

    while True:
        result = fetch_trade_page(api_key, gu_code, yearmonth, page)
        all_items.extend(result["items"])

        fetched_so_far = (page - 1) * PAGE_SIZE + len(result["items"])
        total = result["total_count"]

        logger.info(
            f"  매매 {gu_code} {yearmonth} "
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


# ── XML 파싱 ───────────────────────────────────────────────

def _parse_trade_xml(xml_text: str, page: int) -> dict:
    """국토부 API XML 응답을 파싱해 딕셔너리 리스트로 변환한다.

    Args:
        xml_text: API 응답 원문 XML 문자열
        page:     현재 페이지 번호 (반환값에 포함)

    Returns:
        {"items": list[dict], "total_count": int, "page": int}
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
            row = {
                "지역코드": _text(item, "sggCd"),
                "법정동":   _text(item, "aptDong"),
                "아파트명": _text(item, "aptNm"),
                "건축년도": _int(item, "buildYear"),
                "층":       _int(item, "floor"),
                "전용면적": _float(item, "excluUseAr"),
                "거래금액": _price(item, "dealAmount"),
                "거래년":   _int(item, "dealYear"),
                "거래월":   _int(item, "dealMonth"),
                "거래일":   _int(item, "dealDay"),
                "거래유형": _text(item, "dealingGbn"),
                "수집시각": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "거래분류": "매매",
            }
            items.append(row)

        return {"items": items, "total_count": total_count, "page": page}

    except (ET.ParseError, ValueError) as e:
        logger.error(f"XML 파싱 오류: {e}\n원문(앞 300자): {xml_text[:300]}")
        return {"items": [], "total_count": 0, "page": page}


# ── 타입 안전 헬퍼 ─────────────────────────────────────────

def _text(item: ET.Element, tag: str) -> str:
    """XML 요소에서 텍스트를 안전하게 추출한다."""
    val = item.findtext(tag, "")
    return val.strip() if val else ""


def _int(item: ET.Element, tag: str) -> Optional[int]:
    """XML 요소에서 정수를 안전하게 추출한다. 변환 불가 시 None 반환."""
    try:
        return int(_text(item, tag))
    except (ValueError, TypeError):
        return None


def _float(item: ET.Element, tag: str) -> Optional[float]:
    """XML 요소에서 실수를 안전하게 추출한다. 변환 불가 시 None 반환."""
    try:
        return float(_text(item, tag))
    except (ValueError, TypeError):
        return None


def _price(item: ET.Element, tag: str) -> Optional[int]:
    """XML 요소에서 금액을 추출한다. '85,000' → 85000 (쉼표 제거 후 정수 변환)."""
    try:
        return int(_text(item, tag).replace(",", ""))
    except (ValueError, TypeError):
        return None
