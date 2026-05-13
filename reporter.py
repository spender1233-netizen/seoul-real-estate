"""
자동 리포팅 시스템
- 주간 / 월간 / 분기 / 연간 리포트 자동 생성
- HTML 파일로 저장
- GPT 자동 해설 포함
"""

import sys
import os
import json
import requests
from pathlib import Path
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
import pandas as pd

from analyzer import stats_by_gu, stats_by_dong, monthly_trend, price_per_sqm, detect_outliers
from db_save import query_to_df

load_dotenv()

Path("reports").mkdir(exist_ok=True)


# ── 기간별 데이터 수집 ─────────────────────────────────────

def get_period_data(period: str) -> dict:
    """
    period: 'weekly' | 'monthly' | 'quarterly' | 'yearly'
    """
    today = date.today()

    if period == "weekly":
        start = today - relativedelta(weeks=1)
        label = f"{start.strftime('%Y.%m.%d')} ~ {today.strftime('%Y.%m.%d')}"
        title = "주간 리포트"
    elif period == "monthly":
        start = today - relativedelta(months=1)
        label = f"{start.strftime('%Y.%m.%d')} ~ {today.strftime('%Y.%m.%d')}"
        title = "월간 리포트"
    elif period == "quarterly":
        start = today - relativedelta(months=3)
        label = f"{start.strftime('%Y.%m.%d')} ~ {today.strftime('%Y.%m.%d')}"
        title = "분기 리포트"
    else:  # yearly
        start = today - relativedelta(years=1)
        label = f"{start.strftime('%Y.%m.%d')} ~ {today.strftime('%Y.%m.%d')}"
        title = "연간 리포트"

    start_str = start.strftime("%Y-%m-%d")
    end_str   = today.strftime("%Y-%m-%d")

    # 기간 내 거래 데이터
    df_trade = query_to_df("""
        SELECT gu, apt_name, area, floor, price, trade_date, build_year
        FROM apt_trade
        WHERE trade_date BETWEEN ? AND ?
          AND price IS NOT NULL
    """, (start_str, end_str))

    # 구별 통계
    df_gu = query_to_df("""
        SELECT gu AS 구,
               COUNT(*) AS 거래건수,
               ROUND(AVG(price)) AS 평균가,
               ROUND(MIN(price)) AS 최저가,
               ROUND(MAX(price)) AS 최고가
        FROM apt_trade
        WHERE trade_date BETWEEN ? AND ? AND price IS NOT NULL
        GROUP BY gu
        ORDER BY 평균가 DESC
    """, (start_str, end_str))

    # 월별 추세
    df_trend = query_to_df("""
        SELECT trade_year AS 년, trade_month AS 월,
               COUNT(*) AS 거래건수,
               ROUND(AVG(price)) AS 평균가
        FROM apt_trade
        WHERE trade_date BETWEEN ? AND ? AND price IS NOT NULL
        GROUP BY trade_year, trade_month
        ORDER BY trade_year, trade_month
    """, (start_str, end_str))

    if not df_trend.empty:
        df_trend["전월대비(%)"] = (df_trend["평균가"].pct_change() * 100).round(2)

    # 면적별 단가
    df_sqm = price_per_sqm()

    # 이상 거래
    df_out = detect_outliers()

    # TOP 단지
    df_top = query_to_df("""
        SELECT apt_name AS 아파트, gu AS 구,
               COUNT(*) AS 거래건수,
               ROUND(AVG(price)) AS 평균가,
               ROUND(MAX(price)) AS 최고가
        FROM apt_trade
        WHERE trade_date BETWEEN ? AND ? AND price IS NOT NULL
        GROUP BY apt_name, gu
        HAVING 거래건수 >= 2
        ORDER BY 평균가 DESC
        LIMIT 10
    """, (start_str, end_str))

    return {
        "period":   period,
        "title":    title,
        "label":    label,
        "start":    start_str,
        "end":      end_str,
        "df_trade": df_trade,
        "df_gu":    df_gu,
        "df_trend": df_trend,
        "df_sqm":   df_sqm,
        "df_out":   df_out,
        "df_top":   df_top,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ── GPT 해설 생성 ──────────────────────────────────────────

def generate_ai_summary(data: dict) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return "⚠️ OPENAI_API_KEY가 설정되지 않아 AI 해설을 생성할 수 없습니다."

    df_gu    = data["df_gu"]
    df_trend = data["df_trend"]
    df_out   = data["df_out"]

    lines = [f"[서울 아파트 실거래가 {data['title']} 데이터 ({data['label']})]"]

    if not df_gu.empty:
        total = int(df_gu["거래건수"].sum())
        lines.append(f"\n■ 전체 거래건수: {total:,}건")
        lines.append(f"■ 구별 평균가 TOP 5")
        for _, r in df_gu.head(5).iterrows():
            lines.append(f"  - {r['구']}: {int(r['평균가']):,}만원 ({int(r['거래건수'])}건)")

    if not df_trend.empty:
        lines.append(f"\n■ 월별 추세")
        for _, r in df_trend.iterrows():
            chg = f"(전월대비 {r['전월대비(%)']:+.1f}%)" if pd.notna(r.get('전월대비(%)')) else ""
            lines.append(f"  - {int(r['년'])}-{int(r['월']):02d}: 평균 {int(r['평균가']):,}만원 {chg}")

    if not df_out.empty:
        lines.append(f"\n■ 이상 거래: {len(df_out)}건 탐지")

    context = "\n".join(lines)

    period_focus = {
        "weekly":    "이번 주 단기 시장 동향과 주목할 변화",
        "monthly":   "이번 달 전반적인 시장 흐름과 주요 특징",
        "quarterly": "분기 단위 가격 트렌드와 시장 방향성",
        "yearly":    "연간 시장 변화, 장기 트렌드, 구별 가격 변화",
    }

    prompt = f"""{context}

위 데이터를 바탕으로 서울 아파트 시장 {data['title']}를 작성해주세요.
분석 초점: {period_focus.get(data['period'], '종합 분석')}

다음 형식으로 한국어로 작성해주세요:
## 시장 요약
(2~3문장으로 핵심 요약)

## 주요 특징
- (3가지 bullet)

## 주목할 지역
(가격 상승/하락 지역 언급)

## 종합 의견
(전망과 시사점 2~3문장)"""

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "max_tokens": 800,
                "messages": [
                    {"role": "system", "content": "당신은 한국 부동산 시장 전문 애널리스트입니다."},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"AI 해설 생성 실패: {e}"


# ── HTML 리포트 생성 ───────────────────────────────────────

def build_html(data: dict, ai_summary: str) -> str:
    df_gu    = data["df_gu"]
    df_trend = data["df_trend"]
    df_sqm   = data["df_sqm"]
    df_top   = data["df_top"]
    df_out   = data["df_out"]

    total_trades = int(df_gu["거래건수"].sum()) if not df_gu.empty else 0
    avg_price    = int(df_gu["평균가"].mean()) if not df_gu.empty else 0
    max_price    = int(df_gu["최고가"].max()) if not df_gu.empty else 0

    # 구별 테이블 행
    gu_rows = ""
    for _, r in df_gu.iterrows():
        bar_w = int(r["평균가"] / df_gu["평균가"].max() * 100) if not df_gu.empty else 0
        gu_rows += f"""<tr>
            <td>{r['구']}</td>
            <td>{int(r['거래건수']):,}</td>
            <td>
                <div style="display:flex;align-items:center;gap:8px">
                    <div style="width:{bar_w}%;height:8px;background:#4C72B0;border-radius:4px;min-width:4px"></div>
                    <span>{int(r['평균가']):,}</span>
                </div>
            </td>
            <td>{int(r['최고가']):,}</td>
        </tr>"""

    # 월별 추세 행
    trend_rows = ""
    for _, r in df_trend.iterrows():
        chg = r.get("전월대비(%)", None)
        chg_str = f'<span style="color:{"#e05c5c" if chg and chg > 0 else "#4C72B0"}">{chg:+.1f}%</span>' if pd.notna(chg) else "-"
        trend_rows += f"<tr><td>{int(r['년'])}-{int(r['월']):02d}</td><td>{int(r['거래건수']):,}</td><td>{int(r['평균가']):,}</td><td>{chg_str}</td></tr>"

    # 면적별 단가 행
    sqm_rows = ""
    for _, r in df_sqm.iterrows():
        sqm_rows += f"<tr><td>{r['면적구간']}</td><td>{int(r['거래건수']):,}</td><td>{int(r['평균단가_만원per㎡']):,}</td></tr>"

    # TOP 단지 행
    top_rows = ""
    for _, r in df_top.iterrows():
        top_rows += f"<tr><td>{r['아파트']}</td><td>{r['구']}</td><td>{int(r['거래건수'])}</td><td>{int(r['평균가']):,}</td><td>{int(r['최고가']):,}</td></tr>"

    # 이상 거래 행
    out_rows = ""
    for _, r in df_out.head(5).iterrows():
        out_rows += f"<tr><td>{r['아파트']}</td><td>{int(r['거래금액']):,}</td><td>{int(r['그룹평균']):,}</td><td>{r['시세대비(%)']:+.1f}%</td><td>{r['Z스코어']}</td></tr>"

    # AI 해설 마크다운 → HTML 간단 변환
    ai_html = ai_summary.replace("\n## ", "<h3>").replace("## ", "<h3>")
    ai_html = ai_html.replace("\n- ", "<li>").replace("- ", "<li>")
    ai_html = ai_html.replace("\n\n", "<br><br>").replace("\n", "<br>")

    period_colors = {
        "weekly":    "#4C72B0",
        "monthly":   "#3B8A4A",
        "quarterly": "#B07830",
        "yearly":    "#8040B0",
    }
    accent = period_colors.get(data["period"], "#4C72B0")

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>{data['title']} - 서울 부동산 실거래가</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, 'Noto Sans KR', sans-serif;
         background: #f5f5f0; color: #1a1a1a; padding: 2rem; }}
  .container {{ max-width: 960px; margin: 0 auto; }}

  .header {{
    background: {accent}; color: white;
    border-radius: 16px; padding: 2rem;
    margin-bottom: 1.5rem;
  }}
  .header h1 {{ font-size: 24px; margin-bottom: 4px; }}
  .header p  {{ font-size: 13px; opacity: 0.85; }}

  .metrics {{ display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; margin-bottom: 1.5rem; }}
  .metric {{
    background: white; border-radius: 12px;
    padding: 1rem 1.2rem; border: 1px solid #e8e8e4;
  }}
  .metric-label {{ font-size: 11px; color: #888; margin-bottom: 6px; }}
  .metric-value {{ font-size: 24px; font-weight: 700; color: {accent}; }}

  .section {{
    background: white; border-radius: 12px;
    border: 1px solid #e8e8e4;
    padding: 1.2rem 1.5rem;
    margin-bottom: 1.2rem;
  }}
  .section h2 {{
    font-size: 14px; font-weight: 700;
    color: {accent}; margin-bottom: 1rem;
    padding-bottom: 8px; border-bottom: 2px solid {accent}20;
  }}

  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #f8f8f4; padding: 8px 12px; text-align: left;
       font-size: 11px; font-weight: 700; color: #666;
       border-bottom: 1px solid #e8e8e4; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #f0f0ec; color: #333; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #fafaf8; }}

  .ai-box {{
    background: linear-gradient(135deg, #f0f4ff 0%, #f8f0ff 100%);
    border: 1px solid #d0d8f0; border-radius: 12px;
    padding: 1.5rem; margin-bottom: 1.2rem;
    font-size: 13px; line-height: 1.8; color: #333;
  }}
  .ai-box h3 {{ font-size: 13px; font-weight: 700; color: {accent}; margin: 0.8rem 0 0.4rem; }}
  .ai-box li {{ margin-left: 1.2rem; margin-bottom: 4px; }}
  .ai-label {{
    font-size: 11px; font-weight: 700; color: {accent};
    letter-spacing: 0.06em; text-transform: uppercase;
    margin-bottom: 8px;
  }}

  .footer {{
    text-align: center; font-size: 11px; color: #aaa;
    margin-top: 2rem; padding-top: 1rem;
    border-top: 1px solid #e8e8e4;
  }}
  .no-data {{ color: #aaa; font-size: 13px; padding: 1rem 0; text-align: center; }}
</style>
</head>
<body>
<div class="container">

  <div class="header">
    <h1>🏙️ 서울 아파트 실거래가 {data['title']}</h1>
    <p>분석 기간: {data['label']} &nbsp;|&nbsp; 생성: {data['generated_at']}</p>
  </div>

  <div class="metrics">
    <div class="metric"><div class="metric-label">총 거래건수</div><div class="metric-value">{total_trades:,}건</div></div>
    <div class="metric"><div class="metric-label">평균 매매가</div><div class="metric-value">{avg_price:,}만</div></div>
    <div class="metric"><div class="metric-label">최고 매매가</div><div class="metric-value">{max_price:,}만</div></div>
  </div>

  <div class="ai-box">
    <div class="ai-label">🤖 AI 시장 해설 (GPT-4o-mini)</div>
    {ai_html}
  </div>

  <div class="section">
    <h2>구별 평균 매매가</h2>
    {"<table><thead><tr><th>구</th><th>거래건수</th><th>평균가 (만원)</th><th>최고가</th></tr></thead><tbody>" + gu_rows + "</tbody></table>" if gu_rows else '<div class="no-data">해당 기간 데이터 없음</div>'}
  </div>

  <div class="section">
    <h2>월별 거래 추세</h2>
    {"<table><thead><tr><th>기간</th><th>거래건수</th><th>평균가 (만원)</th><th>전월대비</th></tr></thead><tbody>" + trend_rows + "</tbody></table>" if trend_rows else '<div class="no-data">해당 기간 데이터 없음</div>'}
  </div>

  <div class="section">
    <h2>면적별 ㎡당 단가</h2>
    {"<table><thead><tr><th>면적구간</th><th>거래건수</th><th>㎡당 단가 (만원)</th></tr></thead><tbody>" + sqm_rows + "</tbody></table>" if sqm_rows else '<div class="no-data">해당 기간 데이터 없음</div>'}
  </div>

  <div class="section">
    <h2>거래 많은 단지 TOP 10</h2>
    {"<table><thead><tr><th>아파트</th><th>구</th><th>거래건수</th><th>평균가</th><th>최고가</th></tr></thead><tbody>" + top_rows + "</tbody></table>" if top_rows else '<div class="no-data">해당 기간 데이터 없음</div>'}
  </div>

  {"<div class='section'><h2>⚠️ 이상 거래 탐지</h2><table><thead><tr><th>아파트</th><th>거래금액</th><th>시세평균</th><th>시세대비</th><th>Z스코어</th></tr></thead><tbody>" + out_rows + "</tbody></table></div>" if out_rows else ""}

  <div class="footer">
    서울 아파트 실거래가 자동화 파이프라인 &nbsp;|&nbsp;
    데이터 출처: 국토교통부 실거래가 공개시스템 &nbsp;|&nbsp;
    {data['generated_at']} 생성
  </div>

</div>
</body>
</html>"""


# ── 리포트 저장 ────────────────────────────────────────────

def save_report(period: str) -> str:
    """리포트 생성 및 HTML 저장. 저장 경로 반환."""
    print(f"[{period}] 데이터 수집 중...")
    data = get_period_data(period)

    print(f"[{period}] AI 해설 생성 중...")
    ai_summary = generate_ai_summary(data)

    print(f"[{period}] HTML 생성 중...")
    html = build_html(data, ai_summary)

    filename = f"reports/{period}_{datetime.now().strftime('%Y%m%d_%H%M')}.html"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[{period}] 저장 완료: {filename}")
    return filename


# ── CLI 실행 ───────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--period", choices=["weekly","monthly","quarterly","yearly","all"],
                   default="monthly", help="리포트 기간")
    args = p.parse_args()

    if args.period == "all":
        for period in ["weekly", "monthly", "quarterly", "yearly"]:
            save_report(period)
    else:
        path = save_report(args.period)
        print(f"\n브라우저로 열기: {path}")
