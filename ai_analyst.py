"""
5단계: AI 시장 분석 해설 - 고도화 버전
부동산 전문가 수준의 시스템 프롬프트 + 상세 컨텍스트
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import os
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from analyzer import stats_by_gu, stats_by_dong, monthly_trend, price_per_sqm, detect_outliers
from db_save import query_to_df

load_dotenv()


# ── 고레벨 시스템 프롬프트 ─────────────────────────────────

EXPERT_SYSTEM_PROMPT = """당신은 20년 경력의 한국 부동산 시장 수석 애널리스트입니다.

[전문성]
- 서울 아파트 실거래가 데이터 분석 전문가
- KB부동산, 한국감정원 데이터 해석 경험
- 부동산 투자 자문 및 시장 리포트 작성 전문
- 통계 기반 시장 분석 및 이상 거래 탐지 전문

[분석 원칙]
1. 데이터에 근거한 객관적 분석만 제공 (추측 금지)
2. 수치를 반드시 인용하며 설명 (예: "전월 대비 3.2% 상승")
3. 실수요자와 투자자 관점을 모두 다룸
4. 시장 리스크와 기회를 균형 있게 제시
5. 전문 용어 사용 시 괄호 안에 쉬운 설명 병기
6. 결론은 항상 구체적 수치와 함께 제시

[금지 사항]
- "~것 같습니다", "~수도 있습니다" 등 모호한 표현 사용 금지
- 데이터에 없는 내용 임의 추가 금지
- 투자 권유 표현 금지 (분석만 제공)
- ~~취소선~~ 형식 절대 사용 금지
- **굵게** 외의 마크다운 서식 최소화
- 숫자 범위 표시 시 "~" 기호 사용 금지, 대신 "~부터 ~까지" 또는 "-" 사용"""


# ── 데이터 → 상세 컨텍스트 변환 ──────────────────────────

def build_context(gu: str) -> str:
    lines = [
        f"{'='*60}",
        f"[{gu} 아파트 매매 실거래가 종합 분석 데이터]",
        f"{'='*60}",
    ]

    # 1. 기본 통계
    df_gu = stats_by_gu()
    row = df_gu[df_gu["구"] == gu]
    if not row.empty:
        r = row.iloc[0]
        avg = int(r['평균가'])
        lines.append(f"\n■ 기본 통계")
        lines.append(f"- 총 거래건수: {int(r['거래건수']):,}건")
        lines.append(f"- 평균 매매가: {avg:,}만원 ({avg/10000:.1f}억원)")
        lines.append(f"- 최저 매매가: {int(r['최저가']):,}만원 ({int(r['최저가'])/10000:.1f}억원)")
        lines.append(f"- 최고 매매가: {int(r['최고가']):,}만원 ({int(r['최고가'])/10000:.1f}억원)")
        lines.append(f"- 최고/평균 배율: {int(r['최고가'])/avg:.1f}배 (가격 격차 지표)")

    # 2. 서울 전체 대비 순위
    if not df_gu.empty:
        rank = df_gu[df_gu["구"] == gu].index[0] + 1 if gu in df_gu["구"].values else "?"
        lines.append(f"- 서울 평균가 순위: {rank}위 / {len(df_gu)}개 구")

    # 3. 동별 분석 (상위 + 하위)
    df_dong = stats_by_dong(gu)
    if not df_dong.empty:
        lines.append(f"\n■ 지역별 평균가 분석 (총 {len(df_dong)}개 지역/단지)")
        lines.append("  [상위 5개 동]")
        for _, r in df_dong.head(5).iterrows():
            lines.append(f"  - {r['동']}: {int(r['평균가']):,}만원 ({int(r['거래건수'])}건)")
        if len(df_dong) > 5:
            lines.append("  [하위 3개 동]")
            for _, r in df_dong.tail(3).iterrows():
                lines.append(f"  - {r['동']}: {int(r['평균가']):,}만원 ({int(r['거래건수'])}건)")
        if len(df_dong) >= 2:
            top = int(df_dong.iloc[0]['평균가'])
            bot = int(df_dong.iloc[-1]['평균가'])
            diff = top - bot
            ratio = top / bot if bot > 0 else 0
            lines.append(f"  ※ 동간 가격 격차: {diff:,}만원 (최고/최저 {ratio:.1f}배)")

    # 4. 면적별 단가 분석
    df_sqm = price_per_sqm(gu)
    if not df_sqm.empty:
        lines.append(f"\n■ 면적별 ㎡당 단가 분석")
        for _, r in df_sqm.iterrows():
            pyeong = int(r['평균단가_만원per㎡'] * 3.3)
            lines.append(
                f"- {r['면적구간']}: {int(r['평균단가_만원per㎡']):,}만원/㎡ "
                f"(≈ {pyeong:,}만원/평) | {int(r['거래건수'])}건"
            )
        # 가장 많이 거래된 면적
        top_area = df_sqm.loc[df_sqm['거래건수'].idxmax()]
        lines.append(f"  ※ 가장 많이 거래된 면적: {top_area['면적구간']} ({int(top_area['거래건수'])}건)")

    # 5. 월별 추세 (상세)
    df_trend = monthly_trend(gu)
    if not df_trend.empty:
        lines.append(f"\n■ 월별 거래 추세 ({len(df_trend)}개월)")
        for _, r in df_trend.iterrows():
            chg = r.get('전월대비(%)', None)
            chg_str = f"(전월대비 {chg:+.1f}%)" if pd.notna(chg) else "(기준월)"
            lines.append(
                f"- {int(r['년'])}-{int(r['월']):02d}: "
                f"평균 {int(r['평균가']):,}만원 | {int(r['거래건수'])}건 {chg_str}"
            )
        # 추세 요약
        if len(df_trend) >= 2:
            first_avg = int(df_trend.iloc[0]['평균가'])
            last_avg  = int(df_trend.iloc[-1]['평균가'])
            total_chg = (last_avg - first_avg) / first_avg * 100
            lines.append(f"  ※ 전체 기간 가격 변화: {total_chg:+.1f}% ({first_avg:,}만→{last_avg:,}만원)")

        # 거래량 변화
        first_cnt = int(df_trend.iloc[0]['거래건수'])
        last_cnt  = int(df_trend.iloc[-1]['거래건수'])
        lines.append(f"  ※ 거래량 변화: {first_cnt}건 → {last_cnt}건")

    # 6. 이상 거래 분석
    df_out = detect_outliers(gu)
    if not df_out.empty:
        lines.append(f"\n■ 이상 거래 탐지: {len(df_out)}건 (Z-score 2.5σ 초과)")
        for _, r in df_out.head(5).iterrows():
            direction = "고가" if r['시세대비(%)'] > 0 else "저가"
            lines.append(
                f"- {r['아파트']} {r['전용면적']}㎡ {r['층']}층: "
                f"{int(r['거래금액']):,}만원 "
                f"(시세 {int(r['그룹평균']):,}만원 대비 {direction} {abs(r['시세대비(%)']):+.1f}%, "
                f"Z={r['Z스코어']})"
            )
    else:
        lines.append(f"\n■ 이상 거래: 통계적 이상치 없음 (시장 정상 거래 범위 내)")

    # 7. 거래 유형 분석
    df_type = query_to_df("""
        SELECT trade_type AS 거래유형, COUNT(*) AS 건수,
               ROUND(AVG(price)) AS 평균가
        FROM apt_trade WHERE gu = ? AND price IS NOT NULL
        GROUP BY trade_type ORDER BY 건수 DESC
    """, (gu,))
    if not df_type.empty:
        lines.append(f"\n■ 거래 유형별 현황")
        for _, r in df_type.iterrows():
            lines.append(f"- {r['거래유형']}: {int(r['건수'])}건 | 평균 {int(r['평균가']):,}만원")

    return "\n".join(lines)


# ── 포커스별 고레벨 프롬프트 ──────────────────────────────

FOCUS_PROMPTS = {
    "종합": """
위 실거래가 데이터를 바탕으로 {gu} 아파트 시장에 대한 전문가 수준의 종합 분석을 작성하세요.

[작성 형식 - 반드시 이 순서와 제목으로 작성]

## 📊 시장 현황 요약
수치를 인용하며 현재 시장 상황을 3~4문장으로 요약.
(평균가, 거래건수, 주목할 수치 반드시 포함)

## 🔍 가격 구조 분석
- 동별 가격 양극화 정도와 원인 분석
- 면적별 단가 특이사항 (어떤 면적이 가성비가 좋은지)
- 고가 단지와 저가 단지의 가격 차이

## 📈 시장 트렌드
- 거래량 변화와 그 의미 (거래량은 선행지표)
- 가격 상승/하락 추세와 모멘텀
- 이상 거래 발생 시 의미 분석

## 💡 실수요자 관점 분석
- 지금 이 지역에서 매수 시 고려사항
- 가성비 좋은 동/면적 추천과 근거
- 주의해야 할 리스크 요인

## 🏦 투자자 관점 분석
- 수익성 관점에서 주목할 지역/단지
- 가격 모멘텀과 거래량 기반 시장 활성도 평가
- 단기/중기 시장 방향성 예측과 근거

## ⚠️ 리스크 요인
- 데이터에서 발견된 위험 신호
- 이상 거래 패턴의 시사점
- 투자/매수 시 유의사항

## 📋 종합 결론
핵심 수치 3가지를 인용하며 2~3문장으로 결론 작성.
""",

    "투자": """
위 데이터를 바탕으로 {gu} 아파트 투자 전문 분석을 작성하세요.

## 📊 투자 관점 시장 요약
현재 투자 환경을 수치 기반으로 3문장 요약.

## 💰 수익성 분석
- 면적별 ㎡당 단가 비교 (어떤 면적이 투자 효율 좋은지)
- 동별 가격 모멘텀 비교
- 고가 거래 패턴에서 보이는 시장 신호

## 📈 가격 모멘텀 분석
- 월별 가격 변화율 분석 (가속/둔화 여부)
- 거래량-가격 상관관계 해석
- 현재 시장 사이클 위치 판단

## 🎯 투자 유망 지역/단지
- 상승 여력이 있는 동 (근거 포함)
- 저평가 가능성이 있는 면적대
- 고가 거래 집중 지역 분석

## ⚠️ 투자 리스크
- 고평가 우려 지역
- 거래량 급감 지역
- 이상 거래 패턴의 의미

## 📋 투자 결론
수치 기반 3문장 결론.
""",

    "실수요": """
위 데이터를 바탕으로 {gu} 아파트 실거주 매수자를 위한 분석을 작성하세요.

## 📊 실수요자를 위한 시장 요약
현재 매수 환경을 3문장으로 요약.

## 🏠 면적별 선택 가이드
- 면적 구간별 총액과 ㎡당 단가 비교
- 실거주 목적에 맞는 면적 추천과 근거
- 가성비 좋은 면적대 분석

## 📍 지역 선택 가이드
- 동별 가격 비교와 생활환경 고려
- 상대적으로 합리적인 가격의 동
- 과열 지역 vs 안정 지역 구분

## 📅 타이밍 분석
- 거래량 추세로 본 현재 매수 시점 평가
- 가격 상승/하락 추세와 매수 타이밍

## 💡 실수요자 체크리스트
- 예산 범위별 선택 가능한 동/면적
- 주의해야 할 고가 거래 패턴
- 협상 여지가 있는 시장 신호

## 📋 실수요자 종합 결론
수치 기반 3문장 결론.
""",

    "이상거래": """
위 데이터를 바탕으로 {gu} 아파트 이상 거래 전문 분석을 작성하세요.

## 📊 이상 거래 현황 요약
탐지 건수와 특징을 3문장으로 요약.

## 🔍 이상 거래 패턴 분석
- Z-score 기준 이상 거래 건별 상세 분석
- 고가 거래 집중 지역/단지 패턴
- 저가 거래 발생 원인 추정 (급매, 친족 거래 등)

## 📈 시장 왜곡 가능성 평가
- 이상 거래가 평균가에 미치는 영향
- 실제 시세와의 괴리 정도
- 시장 과열/침체 신호 여부

## ⚠️ 주의해야 할 거래 유형
- 시세보다 현저히 높은 거래의 의미
- 시세보다 현저히 낮은 거래의 의미
- 매수자가 주의해야 할 포인트

## 📋 이상 거래 종합 결론
수치 기반 결론 3문장.
""",
}


# ── OpenAI API 호출 (스트리밍) ─────────────────────────────

def stream_analysis(gu: str, focus: str = "종합"):
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        yield "⚠️ OPENAI_API_KEY가 .env 파일에 설정되지 않았습니다.\n"
        yield "https://platform.openai.com/api-keys 에서 키를 발급받아 .env에 추가해주세요."
        return

    context   = build_context(gu)
    user_prompt = FOCUS_PROMPTS.get(focus, FOCUS_PROMPTS["종합"]).format(gu=gu)
    full_prompt = f"{context}\n\n{user_prompt}"

    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    body = {
        "model":      "gpt-4o-mini",
        "max_tokens": 2000,
        "stream":     True,
        "temperature": 0.3,  # 낮을수록 일관되고 정확한 답변
        "messages": [
            {"role": "system", "content": EXPERT_SYSTEM_PROMPT},
            {"role": "user",   "content": full_prompt},
        ],
    }

    try:
        with requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers, json=body, stream=True, timeout=60,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        obj   = json.loads(data)
                        delta = obj["choices"][0]["delta"]
                        if "content" in delta:
                            yield delta["content"]
                    except (json.JSONDecodeError, KeyError):
                        continue

    except requests.exceptions.RequestException as e:
        yield f"\n\n⚠️ API 호출 오류: {e}"


# ── CLI 실행 ───────────────────────────────────────────────

if __name__ == "__main__":
    gu    = sys.argv[1] if len(sys.argv) > 1 else "강남구"
    focus = sys.argv[2] if len(sys.argv) > 2 else "종합"

    print(f"\n🤖 전문가 AI 시장 분석 | {gu} | {focus}\n" + "="*60 + "\n")
    for chunk in stream_analysis(gu, focus):
        print(chunk, end="", flush=True)
    print("\n\n" + "="*60)
