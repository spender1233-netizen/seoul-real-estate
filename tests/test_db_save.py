"""
DB 저장 로직 유닛 테스트 (unittest 기반)
- 중복 저장 방지 (멱등성)
- 신규/스킵 건수 계산
"""

import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import database
import db_save


def make_trade_df(n: int = 2) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append({
            "구": "강남구", "법정동": "역삼동", "지역코드": "11680",
            "아파트명": f"테스트아파트{i}", "건축년도": 2000 + i,
            "층": i + 1, "전용면적": 84.99,
            "거래금액": 100_000 + i * 10_000,
            "거래유형": "중개거래", "거래년": 2025,
            "거래월": 3, "거래일": i + 1,
            "수집시각": "2025-03-01 00:00:00", "거래분류": "매매",
            "거래일자": pd.Timestamp("2025-03-01"),
        })
    return pd.DataFrame(rows)


class TestSaveTrade(unittest.TestCase):

    def setUp(self):
        """각 테스트 전 임시 DB 초기화"""
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.original_path = database.DB_PATH
        database.DB_PATH = Path(self.tmp) / "test.db"
        database.init_db()

    def tearDown(self):
        database.DB_PATH = self.original_path

    def test_신규_데이터_저장(self):
        """새 데이터 2건이 DB에 저장되어야 한다."""
        result = db_save.save_trade(make_trade_df(2))
        self.assertEqual(result["inserted"], 2)
        self.assertEqual(result["skipped"], 0)

    def test_중복_데이터_스킵(self):
        """동일 데이터를 두 번 저장하면 두 번째는 전부 스킵되어야 한다."""
        df = make_trade_df(2)
        db_save.save_trade(df)
        result = db_save.save_trade(df)
        self.assertEqual(result["inserted"], 0)
        self.assertEqual(result["skipped"], 2)

    def test_빈_DataFrame_처리(self):
        """빈 DataFrame 입력 시 오류 없이 0건을 반환해야 한다."""
        result = db_save.save_trade(pd.DataFrame())
        self.assertEqual(result["inserted"], 0)
        self.assertEqual(result["total"], 0)

    def test_DB_stats_건수(self):
        """저장 후 stats의 매매건수가 정확해야 한다."""
        db_save.save_trade(make_trade_df(3))
        stats = db_save.get_db_stats()
        self.assertEqual(stats["매매건수"], 3)

    def test_수집된_구_목록(self):
        """저장 후 stats의 수집된 구에 강남구가 포함되어야 한다."""
        db_save.save_trade(make_trade_df(1))
        stats = db_save.get_db_stats()
        self.assertIn("강남구", stats["수집된구"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
