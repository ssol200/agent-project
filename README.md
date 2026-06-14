# 🚀 BidGo: AI Bidding Assistant

**BidGo**는 생성형 AI(LLM)를 활용하여 나라장터(G2B) 입찰 공고를 실시간으로 분석하고, 기업 역량에 최적화된 사업 선별 및 수주 전략 수립을 지원하는 **입찰 인텔리전스 에이전트**입니다.

---

## 🌟 핵심 기능 (Core Features)

### 🏢 1. 기업 마스터 프로필 관리 (MDM)
- 기업의 핵심 기술력, 주요 실적, 조직 구성 및 경쟁력을 통합 관리합니다.
- 등록된 정보를 기반으로 AI가 매칭용 핵심 키워드 15~20개를 자동 추출합니다.

### 🔍 2. 지능형 Fast-Scan (마켓 매칭)
- 나라장터 입찰공고 엑셀 파일을 업로드하면 **중복을 자동 제거**하고 전체 공고 중 적합 공고 갯수를 즉시 산출합니다.
- AI가 공고별 적합도 점수(Suitability Score)와 구체적인 매칭 사유를 분석합니다.

### 🔬 3. 전략적 Deep-Dive (RFP 심층 분석)
- 제안요청서(RFP) PDF 전문을 분석하여 **입찰 타당성(Pass/Fail)**을 판독합니다.
- 맞춤형 **수주 전략 및 약점 보완책**을 포함한 임원급 분석 리포트를 생성합니다.

### 📜 4. 분석 히스토리 & 리포트
- 과거의 모든 분석 기록을 실시간 분석과 동일한 퀄리티(게이지 차트, 전략 카드)로 다시 불러옵니다.
- 분석 리포트를 마크다운(.md) 파일로 즉시 다운로드할 수 있습니다.

---

## 🎨 디자인 컨셉 (Enterprise Edition)
- **비즈니스 신뢰감**: 딥 네이비(Deep Navy)와 세련된 블루 포인트 컬러 시스템 적용.
- **임원 대시보드 스타일**: 복잡한 정보의 계층 구조를 단순화하고 시각적 가독성을 극대화한 UI.
- **반응형 인터페이스**: Streamlit 기반의 현대적이고 직관적인 사용자 경험 제공.

---

## 🛠 기술 스택 (Tech Stack)
- **배포**: Streamlit
- **AI Engine**: Google **Gemini API 1.5 Flash / 2.5 Flash**
- **Database**: Supabase (Cloud) & Local JSON Fallback(네트워크 오류 시 백업 저장)
- **Data Processing**: Pandas(입찰 공고 엑셀 정리), PyPDF(RFP 텍스트 추출)

---

## ⚙️ 시작하기 (Quick Start)

### 1. 환경 설정
`.streamlit/secrets.toml` 파일에 API 키와 DB 접속 정보를 설정합니다.
```toml
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
SUPABASE_URL = "YOUR_SUPABASE_URL"
SUPABASE_KEY = "YOUR_SUPABASE_ANON_KEY"
```

### 2. 패키지 설치
```bash
pip install -r requirements.txt
```

### 3. 애플리케이션 실행
```bash
streamlit run app.py
```

---
비즈니스머신러닝 (2026-1)  
