"""
5단계: AI 시장 분석 해설
OpenAI API를 이용해 수집된 데이터를 한국어로 자동 해설
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import os
import json
import requests
from dotenv import load_dotenv
from analyzer import stats_by_gu, stats_by_dong, monthly_trend, price_per_sqm, detect_outliers

load_dotenv()


# ── 데이터 → 프롬프트 변환 ─────────────────────────────────

def build_context(gu: str) -> str:
    lines = [f"[{gu} 아파트 매매 실거래가 분석 데이터]"]

    df_gu = stats_by_gu()
    row = df_gu[df_gu["구"] == gu]
    if not row.empty:
        r = row.iloc[0]
        lines.append(f"\n■ 기본 통계")
        lines.append(f"- 총 거래건수: {int(r['거래건수']):,}건")
        lines.append(f"- 평균 매매가: {int(r['평균가']):,}만원")
        lines.append(f"- 최저 매매가: {int(r['최저가']):,}만원")
        lines.append(f"- 최고 매매가: {int(r['최고가']):,}만원")

    df_dong = stats_by_dong(gu)
    if not df_dong.empty:
        lines.append(f"\n■ 동별 평균가 TOP 5 (만원)")
        for _, r in df_dong.head(5).iterrows():
            lines.append(f"- {r['동']}: {int(r['평균가']):,}만원 ({int(r['거래건수'])}건)")

    df_sqm = price_per_sqm(gu)
    if not df_sqm.empty:
        lines.append(f"\n■ 면적별 ㎡당 단가")
        for _, r in df_sqm.iterrows():
            lines.append(f"- {r['면적구간']}: {int(r['평균단가_만원per㎡']):,}만원/㎡ ({int(r['거래건수'])}건)")

    df_trend = monthly_trend(gu)
    if not df_trend.empty:
        lines.append(f"\n■ 월별 거래 추세")
        for _, r in df_trend.iterrows():
            chg = f"(전월대비 {r['전월대비(%)']:+.1f}%)" if r['전월대비(%)'] == r['전월대비(%)'] else ""
            lines.append(f"- {int(r['년'])}-{int(r['월']):02d}: 평균 {int(r['평균가']):,}만원, {int(r['거래건수'])}건 {chg}")

    df_out = detect_outliers(gu)
    if not df_out.empty:
        lines.append(f"\n■ 이상 거래 탐지: {len(df_out)}건")
        for _, r in df_out.head(3).iterrows():
            lines.append(f"- {r['아파트']}: {int(r['거래금액']):,}만원 (시세대비 {r['시세대비(%)']:+.1f}%)")
    else:
        lines.append(f"\n■ 이상 거래: 탐지 없음")

    return "\n".join(lines)


# ── OpenAI API 호출 (스트리밍) ─────────────────────────────

def stream_analysis(gu: str, focus: str = "종합"):
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        yield "⚠️ OPENAI_API_KEY가 .env 파일에 설정되지 않았습니다.\n"
        yield "https://platform.openai.com/api-keys 에서 키를 발급받아 .env에 추가해주세요.\n"
        yield "OPENAI_API_KEY=sk-..."
        return

    context = build_context(gu)

    focus_prompts = {
        "종합":     "전반적인 시장 동향과 주요 특징을 종합적으로 분석해주세요.",
        "투자":     "투자 관점에서 주목할 지역과 가격 흐름을 분석해주세요.",
        "실수요":   "실거주 목적의 매수자 관점에서 적합한 지역과 가격대를 분석해주세요.",
        "이상거래": "이상 거래 패턴과 시세 대비 특이 거래를 중심으로 분석해주세요.",
    }

    prompt = f"""{context}

위 데이터를 바탕으로 {gu} 아파트 시장을 분석해주세요.
분석 초점: {focus_prompts.get(focus, focus_prompts['종합'])}

다음 형식으로 작성해주세요:
1. 시장 요약 (2~3문장)
2. 주요 특징 (3가지 bullet)
3. 주목할 지역/단지
4. 종합 의견

전문적이되 읽기 쉽게, 한국어로 작성해주세요."""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    body = {
        "model": "gpt-4o-mini",
        "max_tokens": 1000,
        "stream": True,
        "messages": [
            {
                "role": "system",
                "content": "당신은 한국 부동산 시장 전문 애널리스트입니다. 실거래가 데이터를 바탕으로 객관적이고 통찰력 있는 시장 분석을 제공합니다.",
            },
            {"role": "user", "content": prompt},
        ],
    }

    try:
        with requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=body,
            stream=True,
            timeout=30,
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
                        obj = json.loads(data)
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

    print(f"\n🤖 AI 시장 분석 | {gu} | {focus}\n" + "="*50 + "\n")
    for chunk in stream_analysis(gu, focus):
        print(chunk, end="", flush=True)
    print("\n\n" + "="*50)
