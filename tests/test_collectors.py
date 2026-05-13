"""
수집기 유닛 테스트 (unittest 기반)
- XML 파싱 정확성
- 가격 변환 로직
- 에러 핸들링
"""

import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from collectors.trade_collector import _parse_trade_xml, _int, _float, _price

VALID_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header>
  <body>
    <totalCount>2</totalCount>
    <items>
      <item>
        <sggCd>11680</sggCd><aptDong>역삼동</aptDong>
        <aptNm>역삼래미안</aptNm><buildYear>2002</buildYear>
        <floor>15</floor><excluUseAr>84.99</excluUseAr>
        <dealAmount>185,000</dealAmount><dealingGbn>중개거래</dealingGbn>
        <dealYear>2025</dealYear><dealMonth>3</dealMonth><dealDay>5</dealDay>
      </item>
      <item>
        <sggCd>11680</sggCd><aptDong>대치동</aptDong>
        <aptNm>은마아파트</aptNm><buildYear>1979</buildYear>
        <floor>8</floor><excluUseAr>76.79</excluUseAr>
        <dealAmount>220,000</dealAmount><dealingGbn>중개거래</dealingGbn>
        <dealYear>2025</dealYear><dealMonth>3</dealMonth><dealDay>12</dealDay>
      </item>
    </items>
  </body>
</response>"""

ERROR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header><resultCode>99</resultCode><resultMsg>KEY_ERROR</resultMsg></header>
  <body><totalCount>0</totalCount><items/></body>
</response>"""

INVALID_XML = "이건 XML이 아닙니다 <<>>"


class TestParseTradeXml(unittest.TestCase):

    def test_정상_파싱_건수(self):
        """정상 XML에서 2건이 파싱되어야 한다."""
        result = _parse_trade_xml(VALID_XML, 1)
        self.assertEqual(result["total_count"], 2)
        self.assertEqual(len(result["items"]), 2)

    def test_첫번째_아파트명(self):
        """첫 번째 아이템의 아파트명이 정확해야 한다."""
        result = _parse_trade_xml(VALID_XML, 1)
        self.assertEqual(result["items"][0]["아파트명"], "역삼래미안")

    def test_거래금액_쉼표_제거(self):
        """'185,000' 형태의 금액이 185000 정수로 변환되어야 한다."""
        result = _parse_trade_xml(VALID_XML, 1)
        self.assertEqual(result["items"][0]["거래금액"], 185_000)
        self.assertEqual(result["items"][1]["거래금액"], 220_000)

    def test_전용면적_실수_변환(self):
        """전용면적이 float으로 변환되어야 한다."""
        result = _parse_trade_xml(VALID_XML, 1)
        self.assertAlmostEqual(result["items"][0]["전용면적"], 84.99)

    def test_거래분류_매매_고정(self):
        """거래분류가 항상 '매매'여야 한다."""
        result = _parse_trade_xml(VALID_XML, 1)
        for item in result["items"]:
            self.assertEqual(item["거래분류"], "매매")

    def test_API_에러코드_처리(self):
        """API 에러 응답 시 빈 items를 반환해야 한다."""
        result = _parse_trade_xml(ERROR_XML, 1)
        self.assertEqual(result["items"], [])

    def test_잘못된_XML_처리(self):
        """XML 파싱 오류 시 예외 없이 빈 items를 반환해야 한다."""
        result = _parse_trade_xml(INVALID_XML, 1)
        self.assertEqual(result["items"], [])

    def test_페이지번호_반환(self):
        """반환값에 입력한 페이지 번호가 포함되어야 한다."""
        result = _parse_trade_xml(VALID_XML, 3)
        self.assertEqual(result["page"], 3)


class TestHelpers(unittest.TestCase):

    def _elem(self, tag: str, value: str):
        import xml.etree.ElementTree as ET
        return ET.fromstring(f"<item><{tag}>{value}</{tag}></item>")

    def test_int_정상변환(self):
        self.assertEqual(_int(self._elem("floor", "15"), "floor"), 15)

    def test_int_없는태그(self):
        self.assertIsNone(_int(self._elem("floor", "15"), "없는태그"))

    def test_float_정상변환(self):
        self.assertAlmostEqual(_float(self._elem("area", "84.99"), "area"), 84.99)

    def test_price_쉼표제거(self):
        self.assertEqual(_price(self._elem("p", "185,000"), "p"), 185_000)

    def test_price_빈값(self):
        self.assertIsNone(_price(self._elem("p", ""), "p"))


class TestDataFrame(unittest.TestCase):

    def test_거래일자_datetime_변환(self):
        """거래일자가 유효한 datetime으로 변환되어야 한다."""
        result = _parse_trade_xml(VALID_XML, 1)
        df = pd.DataFrame(result["items"])
        df["거래일자"] = pd.to_datetime(
            df["거래년"].astype(str) + "-" +
            df["거래월"].astype(str).str.zfill(2) + "-" +
            df["거래일"].astype(str).str.zfill(2),
            errors="coerce"
        )
        self.assertTrue(df["거래일자"].notna().all())
        self.assertEqual(str(df["거래일자"].iloc[0].date()), "2025-03-05")

    def test_가격_양수(self):
        """거래금액이 모두 양수여야 한다."""
        result = _parse_trade_xml(VALID_XML, 1)
        df = pd.DataFrame(result["items"])
        self.assertTrue((df["거래금액"] > 0).all())


if __name__ == "__main__":
    unittest.main(verbosity=2)
