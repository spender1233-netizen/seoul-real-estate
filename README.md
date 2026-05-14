# 🏙️ 서울 아파트 실거래가 자동화 파이프라인

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue?style=flat-square&logo=python"/>
  <img src="https://img.shields.io/badge/Streamlit-1.x-red?style=flat-square&logo=streamlit"/>
  <img src="https://img.shields.io/badge/SQLite-DB-green?style=flat-square&logo=sqlite"/>
  <img src="https://img.shields.io/badge/OpenAI-GPT--4o--mini-purple?style=flat-square&logo=openai"/>
  <img src="https://img.shields.io/badge/scikit--learn-ML-orange?style=flat-square&logo=scikit-learn"/>
  <img src="https://img.shields.io/badge/License-MIT-lightgrey?style=flat-square"/>
</p>

> 국토교통부 실거래가 공공 API → SQLite DB → 통계 분석 → Streamlit 대시보드 → AI 시장 해설까지
> **end-to-end 부동산 데이터 파이프라인**을 혼자 설계하고 구현한 포트폴리오 프로젝트

<p align="center">
  <a href="https://seoul-real-estate-mer4p6ydwb8qyupff7eo33.streamlit.app/" target="_blank">
    <img src="https://static.streamlit.io/badges/streamlit_badge_black_white.svg" alt="Open in Streamlit"/>
  </a>
</p>

> 🔗 **라이브 데모**: https://seoul-real-estate-mer4p6ydwb8qyupff7eo33.streamlit.app/

---

## 📊 프로젝트 성과 (실측 수치)

| 지표 | 수치 |
|------|------|
| 수집 데이터 | **38,995건** (서울 25개 구 × 6개월) |
| 분석 항목 | 구별/지역별 통계, 면적 단가, 이상거래 탐지, ML 예측 |
| 대시보드 탭 | 7개 탭 (추세·지역·면적·단지검색·이상거래·지도·ML) |
| 자동화 | 매월 1일 자동 수집 + 주간/월간/분기/연간 리포트 |
| AI 해설 | GPT-4o-mini 기반 부동산 전문가 수준 한국어 분석 |

---

## 🎯 만든 이유

부동산 가격을 확인할 때마다 여러 사이트를 수동으로 돌아다녀야 했습니다.
국토부에서 실거래가 데이터를 공공 API로 무료 제공한다는 걸 알고,
**직접 수집 → 저장 → 분석 → 시각화 → AI 해설**까지 end-to-end로 구현했습니다.

처음부터 완성본을 만들지 않고 **6단계 목표**를 순서대로 달성했습니다:

```
1단계 ✅ 가격 자동 수집    →  국토부 API 연동, 페이징, 재시도 로직
2단계 ✅ DB 저장          →  SQLite 스키마 설계, 중복 방지 UPSERT
3단계 ✅ 데이터 분석       →  통계 집계, Z-score 이상치 탐지
4단계 ✅ 화면 시각화       →  Streamlit 대시보드, Plotly 차트, Folium 지도
5단계 ✅ AI 해설          →  GPT-4o-mini 전문가 수준 시장 분석
6단계 ✅ 포트폴리오        →  GitHub 공개, 자동 리포팅, 배포
```

---

## 🛠️ 기술 스택

| 분류 | 기술 | 선택 이유 |
|------|------|-----------|
| Language | Python 3.12 | 데이터 처리 최적 생태계 |
| 데이터 수집 | requests, xml.etree | 공공 API XML 파싱 |
| 데이터 저장 | SQLite3 | 서버 설치 없는 경량 DB |
| 데이터 분석 | pandas, numpy | 표 데이터 처리 표준 |
| 시각화 | Streamlit, Plotly, Folium | Python만으로 웹앱 + 인터랙티브 차트 + 지도 |
| ML | scikit-learn (RandomForest) | 비선형 관계 포착, 과적합에 강함 |
| AI 해설 | OpenAI GPT-4o-mini | 데이터 → 자연어 해설 |
| 자동화 | APScheduler | Python 내 cron 스케줄링 |
| 환경 관리 | python-dotenv | API 키 보안 관리 |

---

## 📁 프로젝트 구조

```
real_estate/
├── main.py                  # 수집 실행 진입점 (CLI)
├── config.py                # 서울 25개 구 코드, 상수
├── database.py              # SQLite 스키마 초기화
├── db_save.py               # 저장 로직 (INSERT OR IGNORE)
├── analyzer.py              # 통계 분석 (5종)
├── dashboard.py             # Streamlit 대시보드 (7탭)
├── ai_analyst.py            # GPT 기반 AI 시장 해설
├── ml_model.py              # 랜덤포레스트 가격 예측
├── kakao_map.py             # Folium 지도 히트맵
├── scheduler.py             # 자동 수집 + 리포팅 스케줄러
├── reporter.py              # HTML 리포트 자동 생성
├── collect_bulk.py          # 대량 일괄 수집
├── .env.example             # 환경변수 템플릿
├── requirements.txt
└── collectors/
    ├── trade_collector.py   # 매매 실거래가 수집기
    └── rent_collector.py    # 전월세 실거래가 수집기
```

---

## ⚙️ 설치 및 실행

### 1. 패키지 설치
```bash
pip install -r requirements.txt
pip install streamlit plotly folium streamlit-folium scikit-learn apscheduler
```

### 2. 환경변수 설정
```bash
cp .env.example .env
```
`.env` 파일 편집:
```
MOLIT_API_KEY=국토부_API_키        # data.go.kr 에서 무료 발급
OPENAI_API_KEY=sk-...              # platform.openai.com 에서 발급
```

### 3. 데이터 수집

```bash
# 단일 구, 단일 월
python main.py --gu 강남구 --ym 202503 --types 매매

# 서울 전체 6개월 대량 수집
python collect_bulk.py --months 6

# DB 현황 확인
python main.py --db-stats
```

### 4. 대시보드 실행
```bash
streamlit run dashboard.py
```
브라우저에서 `http://localhost:8501` 접속

### 5. 자동 스케줄러 실행
```bash
python scheduler.py
```

### 6. 리포트 즉시 생성
```bash
python reporter.py --period monthly   # 월간 리포트
python reporter.py --period all       # 전체 4종 생성
```

---

## 📊 주요 기능 상세

### 🔄 데이터 수집 파이프라인
- 국토부 아파트 매매·전월세 실거래가 API 연동
- 페이징 자동 처리 (100건 단위 반복 요청)
- 지수 백오프 재시도 (2초→4초→8초)
- 서울 25개 구 일괄 수집 지원

### 🗄️ 멱등성 있는 DB 저장
- `INSERT OR IGNORE` + `UNIQUE` 제약으로 중복 방지
- 몇 번 실행해도 데이터 무결성 보장
- 수집 이력 로그 테이블로 추적 가능

### 📈 통계 분석 (5종)
- 구별·지역별 평균/최저/최고가
- 월별 가격 추세 (전월 대비 등락률)
- 면적 구간별 ㎡당 단가
- 단지별 거래 히스토리
- **Z-score 기반 이상 거래 탐지** (2.5σ 기준)

### 🤖 AI 시장 해설
- 20년 경력 부동산 애널리스트 페르소나 시스템 프롬프트
- 실거래 데이터를 프롬프트에 직접 주입해 정확한 수치 기반 분석
- 분석 초점 4종: 종합 / 투자 / 실수요 / 이상거래
- GPT-4o-mini 스트리밍으로 실시간 출력

### 🗺️ 지도 히트맵
- 서울 25개 구 평균가를 파랑→빨강 색상으로 시각화
- 원 클릭 시 구별 상세 정보 팝업

### 🤖 ML 가격 예측
- RandomForestRegressor (n_estimators=200)
- 입력: 구, 전용면적, 층, 건축년도
- 출력: 예측 매매가 + 신뢰 범위
- 특성 중요도 시각화

### 📅 자동 리포팅
| 주기 | 시간 | 내용 |
|------|------|------|
| 매일 | 06:00 | 주요 5개 구 보완 수집 |
| 매주 | 월요일 07:00 | 주간 HTML 리포트 |
| 매월 | 1일 00:05 / 07:30 | 전체 수집 + 월간 리포트 |
| 분기 | 1/4/7/10월 1일 | 분기 리포트 |
| 매년 | 1월 1일 | 연간 리포트 |

---

## 🔑 API 키 발급

| API | 발급처 | 비용 |
|-----|--------|------|
| 국토부 실거래가 | [data.go.kr](https://www.data.go.kr) → "아파트매매 실거래 상세 자료" | **무료** |
| OpenAI | [platform.openai.com](https://platform.openai.com/api-keys) | 분석 1회 약 $0.002 |

---

## 🧗 개발 과정에서 해결한 문제들

### 1. API 문서와 실제 동작의 불일치
공공 API 문서에는 `http`로 나와 있었지만 실제로는 `https`만 허용.
XML 태그명도 문서(한글)와 실제 응답(영문, `aptNm`, `dealAmount`)이 달랐음.
→ 브라우저로 직접 API를 호출해서 실제 응답 구조를 확인 후 수정

### 2. 중복 데이터 저장 문제
자동 스케줄러가 반복 실행될 때 같은 거래가 중복 저장되는 문제.
→ `UNIQUE(apt_name, area, floor, trade_date, price)` + `INSERT OR IGNORE`로
멱등성 있는 파이프라인 구현

### 3. Streamlit iframe 보안 제한
카카오맵 JavaScript SDK가 Streamlit의 iframe 보안 정책에 차단됨.
→ Folium으로 대체해서 Python에서 직접 HTML 생성, 외부 API 의존 제거

---

## 📈 향후 개선 계획

- [ ] PostgreSQL 마이그레이션 (대용량 데이터 대응)
- [ ] 전국 주요 도시 데이터 확장
- [ ] 기준금리·대출금리 외부 변수 추가한 ML 모델 고도화
- [ ] 카카오맵 API 지도 시각화 (플랫폼 전환 후)
- [ ] Streamlit Cloud 배포 (라이브 데모)

---

## 📝 라이선스

MIT License

---

<p align="center">
  <b>데이터 출처: 국토교통부 실거래가 공개시스템</b><br>
  본 프로젝트는 포트폴리오 목적으로 제작되었습니다.
</p>
