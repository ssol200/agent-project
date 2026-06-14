import streamlit as st
import pandas as pd
from google import genai
from google.genai import types
import os
import json
import time
from pypdf import PdfReader
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Supabase fallback handling
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

# -------------------------------------------------------------------
# Core Logic (Merged from utils.py)
# -------------------------------------------------------------------
def extract_company_keywords(client, company_profile):
    """기업 프로필에서 핵심 매칭 키워드 15~20개를 추출합니다."""
    prompt = f"""
    다음 기업 프로필을 분석하여, 나라장터 입찰 공고명에서 검색할만한 핵심 키워드 15개를 뽑아주세요.
    단어 위주로, 콤마(,)로 구분해서 나열하세요. (예: 빅데이터, 클라우드, 정보화전략, ISP...)
    
    [기업 프로필]
    {company_profile.get('biz_sectors')}
    {company_profile.get('representative_services')}
    {company_profile.get('competitiveness')}
    """
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    # 콤마로 분리하여 리스트로 반환
    keywords = [k.strip() for k in response.text.split(",") if k.strip()]
    return keywords

def load_g2b_excel(file):
    """나라장터 엑셀의 불규칙한 헤더를 자동으로 찾아 데이터프레임으로 변환합니다."""
    df_temp = pd.read_excel(file, header=None)
    header_idx = 0
    for i, row in df_temp.iterrows():
        if "공고명" in row.values:
            header_idx = i
            break
    df = pd.read_excel(file, skiprows=header_idx)
    df.columns = [str(col).strip() for col in df.columns]
    return df

@retry(
    retry=retry_if_exception_type(Exception), 
    stop=stop_after_attempt(10), 
    wait=wait_exponential(multiplier=2, min=5, max=120)
)
def batch_fast_scan_matching(client, company, bids_list):
    """여러 개의 공고를 한 번의 API 호출로 묶어서 분석하고, 공고명에서 키워드를 추출하여 매칭합니다."""
    bids_context = "\n".join([f"- [{i+1}] 제목: {b['title']}, 기관: {b['org']}" for i, b in enumerate(bids_list)])
    
    prompt = f"""
    당신은 입찰 분석 에이전트입니다. 다음 기업 역량과 공고 리스트를 보고 각각의 적합도를 판단하세요.
    또한, 각 공고명에서 기업 역량과 매칭되는 핵심 키워드를 추출하세요.
    
    [기업 정보]
    - 기업명: {company.get('name')}
    - 역량 및 실적: {company.get('capabilities')}
    - 주요사업: {company.get('biz_sectors')}
    
    [분석할 공고 리스트]
    {bids_context}
    
    각 공고별로 다음 JSON 형식의 리스트로 응답하세요:
    [
        {{
            "score": 0~100 사이 숫자,
            "matched_keywords": ["추출된", "매칭", "키워드"],
            "reason": "매칭 이유 (1문장)"
        }},
        ...
    ]
    """
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1
        )
    )
    return json.loads(response.text)

def fast_scan_matching(client, company, bid_title, bid_content):
    """단건 공고 분석"""
    prompt = f"""
    당신은 입찰 분석 에이전트입니다. 기업 역량과 공고 요약을 보고 대략적인 적합도를 판단하세요.
    공고 내용에서 기업 역량과 매칭되는 핵심 키워드도 추출하세요.
    
    [기업 정보]
    - 기업명: {company.get('name')}
    - 역량 키워드: {company.get('capabilities')}
    
    [공고 정보]
    - 제목: {bid_title}
    - 내용: {bid_content}
    
    결과는 반드시 다음 JSON 형식으로 출력하세요:
    {{
        "score": 0~100 사이 숫자,
        "matched_keywords": ["키워드1", "키워드2"],
        "reason": "간결한 매칭 이유 (1~2문장)"
    }}
    """
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2
        )
    )
    return json.loads(response.text)

@retry(
    retry=retry_if_exception_type(Exception), 
    stop=stop_after_attempt(5), 
    wait=wait_exponential(multiplier=2, min=5, max=60)
)
def analyze_rfp_deep_dive(client, company, rfp_text):
    """Step 2: RFP 전문 분석 및 정밀 매칭 (Deep-Dive)"""
    trimmed_text = rfp_text[:8000]
    
    prompt = f"""
    당신은 전문 입찰 컨설턴트입니다. 다음 기업 상세 프로필과 RFP 내용을 분석하여 입찰 성공 가능성을 최종 판독하세요.
    
    [기업 상세 프로필]
    - 회사명: {company.get('name')}
    - 주요사업실적: {company.get('capabilities')}
    
    [RFP 핵심 내용]
    {trimmed_text} 
    
    [분석 가이드라인]
    1. Score (0~100): 기업 역량과 과업 내용의 일치도를 100점 만점으로 환산하세요.
    2. Feasibility (Pass/Fail): 참가 자격 및 일치도를 종합하여 입찰 타당성을 진단하세요. (50점 이하면 Fail)
    3. Strategy & Mitigation: 전체적인 총평을 한 단락으로 먼저 작성한 후, 수주를 위한 '핵심 전략'과 부족한 점을 채우기 위한 '보완책'을 명확히 구분하여 작성하세요.
       * 각 포인트(1., 2. 등)는 '1. 주제'를 첫 줄에 쓰고, 상세 설명은 반드시 줄바꿈(\n)을 하여 다음 줄에 작성하세요. (주제: 설명 형식을 피하세요)

    반드시 다음 JSON 형식으로 출력하세요:
    {{
        "score": 0~100 숫자,
        "feasibility": "Pass 또는 Fail",
        "feasibility_reason": "판정 근거",
        "strategy": "📌 총평\\n[전체적인 총평 1단락 작성]\\n\\n🎯 핵심 입찰 전략\\n1. [전략주제1]\\n[전략 상세 내용 1]\\n2. [전략주제2]\\n[전략 상세 내용 2]\\n\\n🛡️ 약점 보완책\\n1. [보완책주제1]\\n[보완책 상세 내용 1]"
    }}
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        # 마크다운 제거
        raw_text = response.text.strip()
        if raw_text.startswith("```"): raw_text = raw_text.split("```")[1].replace("json", "").strip()
        return json.loads(raw_text)
    except Exception as e:
        raise Exception(f"AI 분석 중 오류 발생: {e}")

def extract_text_from_pdf(file):
    """PDF 파일에서 텍스트를 추출하고 정제하여 토큰을 절약합니다."""
    reader = PdfReader(file)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    
    # 불필요한 연속 공백 및 줄바꿈 제거 (토큰 최적화)
    import re
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# -------------------------------------------------------------------
# 1. 초기 설정 및 프리미엄 스타일링
# -------------------------------------------------------------------
st.set_page_config(
    page_title="AI Bidding Intelligence | 입찰 전략 에이전트",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 CSS
st.markdown("""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    html, body, [class*="css"] { 
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, 'Helvetica Neue', 'Segoe UI', 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif; 
        color: #1e293b;
    }
    .stApp { background-color: #f8fafc; }
    .metric-card { background-color: white; padding: 25px; border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 2px 4px rgba(0,0,0,0.02); margin-bottom: 20px; }
    .main-header { font-size: 2.2rem; font-weight: 800; color: #1f2a48; margin-bottom: 0.5rem; letter-spacing: -0.03em; }
    .sub-header { font-size: 1.05rem; color: #64748b; margin-bottom: 2rem; font-weight: 400; }
    
    /* 탭 디자인 (네이비 & 골드 적용) */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; border-bottom: 1px solid #e2e8f0; padding-bottom: 5px; }
    .stTabs [data-baseweb="tab"] { background-color: transparent; border: none; padding: 10px 15px; font-weight: 600; color: #64748b; transition: all 0.2s; }
    .stTabs [aria-selected="true"] { color: #1f2a48 !important; border-bottom: 3px solid #c4a95a !important; background-color: transparent !important; font-weight: 800 !important; }
    
    /* 리포트 제목 디자인 */
    .report-title { font-size: 1.6rem; font-weight: 800; color: #1f2a48; border-bottom: 2px solid #3b82f6; padding-bottom: 12px; margin-bottom: 25px; letter-spacing: -0.02em; }
    .report-section-title { font-size: 1.15rem; font-weight: 700; color: #1f2a48; margin-top: 25px; margin-bottom: 15px; display: flex; align-items: center; gap: 8px; }
    
    /* 본문 텍스트 박스 */
    .strategy-content { background-color: white; padding: 30px 35px; border-radius: 12px; border: 1px solid #e2e8f0; font-size: 1.05rem; line-height: 1.8; color: #334155; box-shadow: 0 1px 3px rgba(0,0,0,0.02); border-left: 4px solid #1f2a48; }
    .strategy-content b { color: #1f2a48; font-weight: 800; }
    
    /* Primary 버튼 (네이비 & 골드 적용) */
    .stButton > button[kind="primary"] { background-color: #1f2a48 !important; color: #c4a95a !important; border: 1px solid #1f2a48 !important; font-weight: 700; }
    .stButton > button[kind="primary"]:hover { background-color: #2a3860 !important; color: #d8b056 !important; border-color: #c4a95a !important; }
    /* 섹션 헤더 슬림 배너 디자인 */
    .section-header-banner {
        background-color: #1f2a48;
        padding: 15px 30px;
        border-radius: 10px;
        color: #c4a95a;
        margin-bottom: 25px;
        display: flex;
        justify-content: center;
        align-items: center;
        font-size: 1.2rem;
        font-weight: 700;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)

# -------------------------------------------------------------------
# 2. 데이터베이스 설정 (Local/Supabase 전환 가능)
# -------------------------------------------------------------------
# Supabase 클라우드 모드를 활성화합니다.
LOCAL_MODE = False 


def get_secret(key, default=""):
    try: return st.secrets.get(key, default)
    except Exception: return default

# Supabase client initialization
@st.cache_resource
def init_supabase() -> Client:
    if LOCAL_MODE: return None
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_KEY")
    if not url or not key: return None
    try: return create_client(url, key)
    except Exception: return None

supabase = init_supabase() if SUPABASE_AVAILABLE else None

def load_company_profiles():
    if LOCAL_MODE or not supabase:
        if os.path.exists("local_company_profiles.json"):
            with open("local_company_profiles.json", "r", encoding="utf-8") as f:
                return json.load(f)
        return []
    try:
        res = supabase.table("company_profiles_mgnt").select("*").order("created_at", desc=True).execute()
        return res.data
    except Exception: return []

def save_company_profile(data):
    if LOCAL_MODE or not supabase:
        profiles = load_company_profiles()
        # 이름 기반 중복 제거 및 업데이트
        profiles = [p for p in profiles if p['name'] != data['name']]
        profiles.insert(0, data)
        with open("local_company_profiles.json", "w", encoding="utf-8") as f:
            json.dump(profiles, f, ensure_ascii=False, indent=4)
        return
    try:
        supabase.table("company_profiles_mgnt").upsert(data, on_conflict="name").execute()
    except Exception as e:
        st.error(f"DB 저장 에러: {e}")

def load_history():
    if LOCAL_MODE or not supabase:
        if os.path.exists("local_analysis_history.json"):
            with open("local_analysis_history.json", "r", encoding="utf-8") as f:
                return json.load(f)
        return []
    try:
        res = supabase.table("analysis_history").select("*").order("created_at", desc=True).execute()
        return res.data
    except Exception: return []

def save_history(report):
    if LOCAL_MODE or not supabase:
        history = load_history()
        history.insert(0, report)
        with open("local_analysis_history.json", "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=4)
        return
    try:
        supabase.table("analysis_history").insert(report).execute()
    except Exception as e:
        st.error(f"히스토리 저장 에러: {e}")

# API 키 설정 (UI 노출 없이 Secret에서 로드)
GEMINI_API_KEY = get_secret("GEMINI_API_KEY")

# 전역 클라이언트 대신 필요할 때 최신 키로 호출하는 함수로 변경
def get_gemini_client():
    if not GEMINI_API_KEY:
        st.error("Gemini API 키가 설정되지 않았습니다. 관리자에게 문의하세요.")
        st.stop()
    return genai.Client(api_key=GEMINI_API_KEY)

st.markdown("""
<div style="background-color: #1f2a48; padding: 25px 40px; border-radius: 12px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
    <div>
        <h1 style="color: #c4a95a; font-size: 2.2rem; margin: 0; font-weight: 800; letter-spacing: -0.02em;">AI Bidding Assistant</h1>
    </div>
    <div style="background-color: #c4a95a; color: #1f2a48; padding: 8px 25px; border-radius: 30px; font-weight: 800; font-size: 1.1rem; letter-spacing: 0.05em; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
        BidGo
    </div>
</div>
""", unsafe_allow_html=True)

# -------------------------------------------------------------------
# 2. 기업 관리 섹션
# -------------------------------------------------------------------
def mdm_section():
    with st.expander("🆕 신규 기업 등록하기", expanded=False):
        with st.form("company_form"):
            name = st.text_input("회사명", placeholder="예: (주)데이터인사이트", key="form_company_name")
            col_a, col_b = st.columns(2)
            with col_a:
                founding_year = st.number_input("설립연도", min_value=1900, max_value=2026, value=2020, key="form_founding_year")
                ceo = st.text_input("대표자", key="form_ceo")
                region = st.text_input("소재지", key="form_region")
            with col_b:
                company_size = st.selectbox("기업규모", ["소기업/소상공인", "중소기업", "중견기업", "대기업", "비영리법인"], key="form_size")
                biz_type = st.text_input("업종", key="form_biz_type")
                biz_sectors = st.text_input("주요사업분야", key="form_biz_sectors")
            
            st.divider()
            col_c, col_d = st.columns(2)
            with col_c:
                representative_services = st.text_area("대표 서비스", key="form_services", help="주요 제품이나 서비스 내용을 적어주세요.")
                organization = st.text_area("조직 구성", key="form_org", help="조직도나 인력 구성 현황을 적어주세요.")
            with col_d:
                competitiveness = st.text_area("주요 경쟁력", key="form_comp", help="타사 대비 차별화된 강점을 적어주세요.")
                capabilities = st.text_area("주요 사업실적", key="form_caps", help="최근 3년간의 주요 수주 실적을 적어주세요.")
            
            notes = st.text_area("비고", key="form_notes", help="기타 참고사항을 입력해주세요.")
            
            submit = st.form_submit_button("기업 프로필 등록 및 분석 시작", type="primary", use_container_width=True)
            if submit:
                if not name:
                    st.error("회사명을 입력해주세요.")
                else:
                    with st.spinner("기업 역량 키워드 추출 중..."):
                        client = get_gemini_client()
                        temp_dict = {"biz_sectors": biz_sectors, "representative_services": representative_services, "competitiveness": competitiveness}
                        keywords = extract_company_keywords(client, temp_dict)
                        data = {
                            "name": name, "founding_year": founding_year, "ceo": ceo, "region": region, 
                            "company_size": company_size, "biz_type": biz_type, "biz_sectors": biz_sectors, 
                            "representative_services": representative_services, "organization": organization, 
                            "competitiveness": competitiveness, "capabilities": capabilities, 
                            "keywords": keywords, "notes": notes
                        }
                        save_company_profile(data)
                        st.success("기업 프로필과 분석 키워드가 저장되었습니다.")
                        st.rerun()

    st.divider()

    profiles = load_company_profiles()
    if profiles:
        df_profiles = pd.DataFrame(profiles)
        
        # 1. 기업 선택 영역
        st.markdown("#### 📂 기업 선택")
        selected_name = st.selectbox("등록된 기업 목록", df_profiles["name"].tolist(), key="select_company_box", label_visibility="collapsed")
        
        curr = df_profiles[df_profiles["name"] == selected_name].iloc[0]
        
        # 선택 버튼 (누르면 세션 상태 업데이트 및 안내)
        if st.button(f"🎯 {selected_name} 분석 시작하기", type="primary", use_container_width=True):
            st.session_state["current_company"] = curr.to_dict()
            st.success(f"'{selected_name}' 기업이 분석 대상으로 설정되었습니다. 상단의 [🔍 Fast-Scan] 탭으로 이동하여 분석을 시작하세요!")
            # 탭 전환 유도를 위해 세션 상태 활용 가능 (여기서는 안내 메시지로 충분)
        
        # 2. 기업 상세 정보 카드 (Premium 디자인)
        st.markdown(f"""
        <div style="background-color: white; padding: 25px; border-radius: 12px; border: 1px solid #edf2f7; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); margin: 20px 0;">
            <div style="display: flex; align-items: center; margin-bottom: 20px;">
                <div style="background-color: #3b82f6; width: 4px; height: 24px; border-radius: 2px; margin-right: 12px;"></div>
                <h3 style="margin: 0; color: #1a202c; font-size: 1.5rem;">{curr['name']} <span style="font-size: 0.9rem; color: #718096; font-weight: normal; margin-left: 10px;">| {curr['biz_type']}</span></h3>
            </div>
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; border-top: 1px solid #f7fafc; padding-top: 20px;">
                <div>
                    <p style="margin: 0; font-size: 0.8rem; color: #a0aec0; text-transform: uppercase; letter-spacing: 0.05em;">대표자</p>
                    <p style="margin: 4px 0 0 0; font-weight: 600; color: #2d3748;">{curr['ceo']}</p>
                </div>
                <div>
                    <p style="margin: 0; font-size: 0.8rem; color: #a0aec0; text-transform: uppercase; letter-spacing: 0.05em;">설립연도</p>
                    <p style="margin: 4px 0 0 0; font-weight: 600; color: #2d3748;">{int(curr['founding_year'])}년</p>
                </div>
                <div>
                    <p style="margin: 0; font-size: 0.8rem; color: #a0aec0; text-transform: uppercase; letter-spacing: 0.05em;">기업규모</p>
                    <p style="margin: 4px 0 0 0; font-weight: 600; color: #2d3748;">{curr['company_size']}</p>
                </div>
                <div>
                    <p style="margin: 0; font-size: 0.8rem; color: #a0aec0; text-transform: uppercase; letter-spacing: 0.05em;">소재지</p>
                    <p style="margin: 4px 0 0 0; font-weight: 600; color: #2d3748;">{curr['region'].split()[0] if curr['region'] else "-"}</p>
                </div>
            </div>
            <div style="margin-top: 25px; padding: 15px; background-color: #f8fafc; border-radius: 8px;">
                <p style="margin: 0 0 8px 0; font-size: 0.85rem; font-weight: 700; color: #4a5568;">🛡️ 핵심 역량 및 키워드</p>
                <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                    {" ".join([f'<span style="background-color: #ebf4ff; color: #3182ce; padding: 4px 10px; border-radius: 15px; font-size: 0.75rem; font-weight: 600;">#{k}</span>' for k in curr.get('keywords', [])]) if curr.get('keywords') and isinstance(curr.get('keywords'), list) else '<span style="color: #a0aec0; font-size: 0.8rem;">설정된 키워드가 없습니다.</span>'}
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 3. 추가 상세 실적 및 편집 도구 (Expander로 정리)
        col_left, col_right = st.columns([2, 1])
        with col_left:
            with st.expander("📝 상세 실적 및 비고 확인", expanded=True):
                st.markdown(f"**주요 실적:**\n{curr['capabilities']}")
                if curr.get('notes'):
                    st.info(f"**비고:** {curr['notes']}")
        
        with col_right:
            with st.expander("🛠️ 매칭 키워드 관리"):
                kw_str = st.text_area("쉼표로 구분하여 수정", value=", ".join(curr.get('keywords', []) or []), key="kw_editor", height=100)
                if st.button("업데이트 및 저장", use_container_width=True):
                    curr_dict = curr.to_dict()
                    curr_dict['keywords'] = [k.strip() for k in kw_str.split(",") if k.strip()]
                    save_company_profile(curr_dict)
                    st.success("키워드 저장 완료!")
                    st.rerun()
        
        if st.button("🔄 전체 데이터 새로고침", use_container_width=True):
            st.rerun()
    else:
        st.info("등록된 기업 정보가 없습니다. 상단 '신규 기업 등록하기'를 통해 정보를 입력해주세요.")

# -------------------------------------------------------------------
# 3. Fast-Scan 섹션
# -------------------------------------------------------------------
def fast_scan_section():
    if "current_company" not in st.session_state:
        st.warning("기업 관리 탭에서 기업을 먼저 선택해주세요.")
        return
    comp = st.session_state["current_company"]
    
    st.markdown(f"### 🎯 {comp['name']}")
    with st.container(border=True):
        st.subheader("🔍 공고 퀵 스캔 및 매칭")
    
    col_empty, col_link = st.columns([3, 1])
    with col_link:
        st.link_button("🌐 나라장터 사이트 이동", "https://www.g2b.go.kr", use_container_width=True)
    
    input_method = st.radio("입력 방식", ["엑셀 대량 분석", "직접 수동 입력"], key="scan_method", horizontal=True)
    st.divider()
    
    if input_method == "엑셀 대량 분석":
        uploaded_excel = st.file_uploader("나라장터 입찰공고 엑셀 업로드", type=["xlsx", "xls"], key="batch_excel")
        if uploaded_excel:
            try:
                df_display = load_g2b_excel(uploaded_excel)
                df_display = df_display[df_display["공고명"] != "공고명"]
                
                # 1. 취소공고 필터링 및 불필요 컬럼 삭제
                if "구분" in df_display.columns:
                    df_display = df_display[~df_display["구분"].str.contains("취소", na=False)]
                
                # 1-1. 중복 공고(재공고 등) 처리: 공고명이 같으면 최신(게시일시 기준) 1개만 남김
                date_col = next((c for c in df_display.columns if "일시" in c or "날짜" in c or "일자" in c), None)
                if date_col:
                    df_display = df_display.sort_values(by=date_col, ascending=False)
                df_display = df_display.drop_duplicates(subset=["공고명"], keep="first")
                
                drop_cols = ["업무여부", "구분"]
                df_display = df_display.drop(columns=[c for c in drop_cols if c in df_display.columns])
                
                target_k = comp.get('keywords', [])
                
                def match_keywords(title):
                    matches = [k for k in target_k if str(k).lower() in str(title).lower()]
                    return ", ".join(matches), len(matches)
                
                total_count = len(df_display) # 필터 전 전체 건수
                if target_k:
                    res_tuple = df_display["공고명"].apply(match_keywords)
                    df_display["매칭 키워드"] = [t[0] for t in res_tuple]
                    df_display["매칭 스코어"] = [t[1] for t in res_tuple]
                    
                    # 매칭된 것(스코어 > 0)만 결과로 유지
                    df_filtered = df_display[df_display["매칭 스코어"] > 0]
                    df_filtered = df_filtered.sort_values(by="매칭 스코어", ascending=False)
                    
                    st.success(f"✅ 분석 완료! 전체 {total_count}건 중 {len(df_filtered)}건의 유효 공고를 찾아냈습니다.")
                    df_to_show = df_filtered
                else:
                    df_to_show = df_display
                    st.info(f"ℹ️ 키워드 설정이 없어 전체 {len(df_display)}건을 표시합니다.")
                
                # 2. 스타일링 적용 (스코어 기반 색상)
                def color_score(val):
                    if val >= 3: color = '#dcfce7' # 진한 초록
                    elif val >= 1: color = '#fef9c3' # 노란색
                    else: color = 'white'
                    return f'background-color: {color}'

                styled_df = df_to_show.style.map(color_score, subset=['매칭 스코어'])
                
                st.write(f"📊 **지능형 키워드 매칭 분석 결과**")
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
                
                if st.button("✨ 상위 항목 AI 심층 매칭 (적합도 분석)", type="primary"):
                    with st.spinner("AI가 분석 중입니다..."):
                        client = get_gemini_client()
                        process_df = df_to_show.head(10).copy()
                        bids = [{"title": r["공고명"], "org": r["공고기관"], "no": r["입찰공고번호"]} for _, r in process_df.iterrows()]
                        batch_res = batch_fast_scan_matching(client, comp, bids)
                        process_df["AI 적합도"] = [res["score"] for res in batch_res]
                        process_df["AI 매칭 키워드"] = [", ".join(res.get("matched_keywords", [])) for res in batch_res]
                        process_df["AI 분석 근거"] = [res["reason"] for res in batch_res]
                        st.session_state["augmented_df"] = process_df.sort_values(by="AI 적합도", ascending=False)
                
                if "augmented_df" in st.session_state:
                    st.divider()
                    st.subheader("🏆 AI 정밀 분석 통합 테이블")
                    st.dataframe(st.session_state["augmented_df"], use_container_width=True, hide_index=True)
                    csv = st.session_state["augmented_df"].to_csv(index=False).encode('utf-8-sig')
                    st.download_button("📂 분석 결과 다운로드 (CSV)", csv, "bidding_analysis.csv", "text/csv")
            except Exception as e: st.error(f"파일 처리 중 오류: {e}")
    else:
        t = st.text_input("공고명", key="single_title")
        c = st.text_area("공고 요약", key="single_content")
        if st.button("즉시 분석", type="primary", key="single_scan_btn"):
            client = get_gemini_client()
            res = fast_scan_matching(client, comp, t, c)
            col_res1, col_res2 = st.columns([1, 2])
            with col_res1:
                st.metric("최종 적합도 점수", f"{res['score']}%")
            with col_res2:
                st.write(f"**매칭 키워드:** {', '.join(res.get('matched_keywords', []))}")
            st.info(f"**판단 근거:** {res['reason']}")

# -------------------------------------------------------------------
# 4. Deep-Dive 섹션
# -------------------------------------------------------------------
import plotly.graph_objects as go
def render_rich_report(res, company_name, key_suffix=""):
    st.divider()
    
    # 1. 리포트 헤더 (Clean & Minimalist Style)
    st.markdown(f"""
    <div style="padding: 20px 0; margin-bottom: 30px; border-bottom: 2px solid #3b82f6;">
        <h1 style="color: #1f2a48; margin: 0; font-size: 2.2rem; font-weight: 800; letter-spacing: -0.03em;">📑 AI 심층 분석 리포트</h1>
        <p style="color: #555555; margin: 10px 0 0 0; font-size: 1.2rem; font-weight: 600;">분석 기업: <span style="color: #1f2a48;">{company_name}</span></p>
    </div>
    """, unsafe_allow_html=True)
    
    # 2. 스코어 및 진단 영역
    col_score, col_eligibility = st.columns([1, 1])
    
    score = res.get('score', 0)
    if score >= 90:
        f_title, f_desc, pass_color, bg_color = "최적 입찰 대상", "당사 역량 및 수행 이력과 높은 적합성을 보이며, 낙찰 가능성이 매우 높은 것으로 판단됩니다. 적극적인 입찰 참여를 권고합니다.", "#059669", "#ecfdf5"
    elif score >= 70:
        f_title, f_desc, pass_color, bg_color = "입찰 유망", "전반적인 적격 요건을 충족하며 경쟁력 있는 제안이 가능한 공고입니다. 세부 요건 검토 후 입찰 참여를 권고합니다.", "#2563eb", "#eff6ff"
    elif score >= 50:
        f_title, f_desc, pass_color, bg_color = "조건부 검토", "일부 요건에서 보완이 필요하나, 전략적 판단에 따라 입찰 참여 여부를 결정할 수 있는 공고입니다. 내부 역량 및 리소스를 종합적으로 고려하시기 바랍니다.", "#d97706", "#fffbeb"
    elif score >= 30:
        f_title, f_desc, pass_color, bg_color = "입찰 신중 검토", "요건 충족도가 낮아 낙찰 가능성이 제한적입니다. 입찰 참여 시 상당한 리소스 투입이 예상되므로 신중한 검토가 필요합니다.", "#ea580c", "#fff7ed"
    else:
        f_title, f_desc, pass_color, bg_color = "입찰 부적합", "현 시점에서 당사 역량 및 자격 요건과의 적합성이 낮아 입찰 참여를 권고하지 않습니다.", "#e11d48", "#fff1f2"
    
    with col_score:
        st.markdown('<div class="report-section-title" style="margin-top: 0;">📊 입찰 적합도 지수</div>', unsafe_allow_html=True)
        fig = go.Figure(go.Indicator(
            mode = "gauge+number", 
            value = score, 
            number = {'font': {'color': pass_color, 'size': 70, 'weight': 'bold'}},
            gauge = {
                'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#cbd5e1"}, 
                'bar': {'color': pass_color}, 
                'bgcolor': "white",
                'borderwidth': 0,
                'steps': [
                    {'range': [0, 50], 'color': "#f8fafc"}, 
                    {'range': [50, 75], 'color': "#f1f5f9"}, 
                    {'range': [75, 100], 'color': "#e2e8f0"}
                ]
            }
        ))
        fig.update_layout(height=260, margin=dict(l=30, r=30, t=10, b=10), font={'family': "Pretendard"})
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False}, key=f"gauge_{key_suffix}")
        
    with col_eligibility:
        st.markdown('<div class="report-section-title" style="margin-top: 0;">✅ AI 타당성 진단</div>', unsafe_allow_html=True)
        
        st.markdown(f"""
        <div style="background-color: white; height: 260px; display: flex; flex-direction: column; justify-content: center; padding: 35px; border-radius: 16px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
            <h2 style="color: {pass_color}; margin: 0 0 15px 0; font-size: 1.9rem; font-weight: 800; letter-spacing: -0.04em;">{f_title}</h2>
            <p style="font-size: 1.1rem; color: #334155; margin: 0; line-height: 1.7; word-break: keep-all; font-weight: 500;">{f_desc}</p>
        </div>
        """, unsafe_allow_html=True)

    # 3. 입찰 전략 제언 (Professional Dashboard Box)
    st.markdown('<div class="report-section-title">💡 전략적 입찰 제언</div>', unsafe_allow_html=True)
    strategy_text = res['strategy']
    
    # 1. 2. 등의 숫자에 강조색 적용 (HTML 태그 삽입 전 수행하여 CSS 숫자와 충돌 방지)
    import re
    strategy_text = re.sub(r'(^|\n)(\d+\.)', r'\1<b style="color: #3b82f6; font-size: 1.1rem;">\2</b>', strategy_text)

    # 헤더 텍스트 포맷팅
    strategy_text = strategy_text.replace("📌 총평", '<h3 style="color: #1f2a48; font-size: 1.4rem; margin-top: 0; border-bottom: 2px solid #3b82f6; padding-bottom: 8px; display: inline-block;">📌 총평</h3>')
    strategy_text = strategy_text.replace("🎯 핵심 입찰 전략", '<h3 style="color: #1f2a48; font-size: 1.4rem; margin-top: 30px; border-bottom: 2px solid #3b82f6; padding-bottom: 8px; display: inline-block;">🎯 핵심 입찰 전략</h3>')
    strategy_text = strategy_text.replace("🛡️ 약점 보완책", '<h3 style="color: #1f2a48; font-size: 1.4rem; margin-top: 30px; border-bottom: 2px solid #3b82f6; padding-bottom: 8px; display: inline-block;">🛡️ 약점 보완책</h3>')
    
    # 줄바꿈 처리
    strategy_text = strategy_text.replace('\n', '<br>')
    
    st.markdown(f"""
    <div style="background-color: #FFFFFF; padding: 40px; border-radius: 16px; border: 1px solid #e2e8f0; font-size: 1.05rem; line-height: 1.9; color: #334155; box-shadow: 0 4px 6px rgba(0,0,0,0.01);">
        {strategy_text}
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    report_content = f"""# AI 심층 분석 리포트
**분석 대상 기업:** {company_name}

## 1. 입찰 적합도 (Match Score)
* 점수: {score}점 / 100점

## 2. 입찰 타당성 진단 (Feasibility)
* 판독 결과: {f_title}
* 진단 요약: {f_desc}
* 세부 근거: {res.get('feasibility_reason', res.get('eligibility_reason', ''))}

## 3. 입찰 전략 및 제언 (Strategy & Action Items)
{res['strategy']}

---
*Generated by BidGo - AI Bidding Assistant*
"""
    st.download_button(
        label="📥 이 리포트를 파일로 다운로드 (.md)",
        data=report_content,
        file_name=f"BidGo_분석리포트_{company_name}.md",
        mime="text/markdown",
        use_container_width=True,
        key=f"dl_{key_suffix}"
    )

def fast_scan_section():
    if "current_company" not in st.session_state:
        st.warning("기업 관리 탭에서 기업을 먼저 선택해주세요.")
        return
    comp = st.session_state["current_company"]
    
    st.markdown("#### 🔍 공고 퀵 스캔 및 매칭")
    st.markdown(f"""<div style="background-color: #f0f2f6; padding: 10px 15px; border-radius: 8px; border: 1px solid #d1d5db; color: #555555; font-weight: 500; margin-bottom: 20px; font-size: 0.9rem;">{comp['name']}</div>""", unsafe_allow_html=True)
    
    col_empty, col_link = st.columns([3, 1])
    with col_link:
        st.link_button("🌐 나라장터 사이트 이동", "https://www.g2b.go.kr", use_container_width=True)
    
    input_method = st.radio("입력 방식", ["엑셀 대량 분석", "직접 수동 입력"], key="scan_method", horizontal=True)
    st.divider()
    
    if input_method == "엑셀 대량 분석":
        uploaded_excel = st.file_uploader("나라장터 입찰공고 엑셀 업로드", type=["xlsx", "xls"], key="batch_excel")
        if uploaded_excel:
            try:
                df_display = load_g2b_excel(uploaded_excel)
                df_display = df_display[df_display["공고명"] != "공고명"]
                
                # 1. 취소공고 필터링 및 불필요 컬럼 삭제
                if "구분" in df_display.columns:
                    df_display = df_display[~df_display["구분"].str.contains("취소", na=False)]
                
                # 1-1. 중복 공고(재공고 등) 처리: 공고명이 같으면 최신(게시일시 기준) 1개만 남김
                date_col = next((c for c in df_display.columns if "일시" in c or "날짜" in c or "일자" in c), None)
                if date_col:
                    df_display = df_display.sort_values(by=date_col, ascending=False)
                df_display = df_display.drop_duplicates(subset=["공고명"], keep="first")
                
                drop_cols = ["업무여부", "구분"]
                df_display = df_display.drop(columns=[c for c in drop_cols if c in df_display.columns])
                
                target_k = comp.get('keywords', [])
                
                def match_keywords(title):
                    matches = [k for k in target_k if str(k).lower() in str(title).lower()]
                    return ", ".join(matches), len(matches)
                
                total_count = len(df_display) # 필터 전 전체 건수
                if target_k:
                    res_tuple = df_display["공고명"].apply(match_keywords)
                    df_display["매칭 키워드"] = [t[0] for t in res_tuple]
                    df_display["매칭 스코어"] = [t[1] for t in res_tuple]
                    
                    # 매칭된 것(스코어 > 0)만 결과로 유지
                    df_filtered = df_display[df_display["매칭 스코어"] > 0]
                    df_filtered = df_filtered.sort_values(by="매칭 스코어", ascending=False)
                    
                    st.success(f"✅ 분석 완료! 전체 {total_count}건 중 {len(df_filtered)}건의 유효 공고를 찾아냈습니다.")
                    df_to_show = df_filtered
                else:
                    df_to_show = df_display
                    st.info(f"ℹ️ 키워드 설정이 없어 전체 {len(df_display)}건을 표시합니다.")
                
                # 2. 스타일링 적용 (스코어 기반 색상)
                def color_score(val):
                    if val >= 3: color = '#dcfce7' # 진한 초록
                    elif val >= 1: color = '#fef9c3' # 노란색
                    else: color = 'white'
                    return f'background-color: {color}'

                styled_df = df_to_show.style.map(color_score, subset=['매칭 스코어'])
                
                st.write(f"📊 **지능형 키워드 매칭 분석 결과**")
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
                
                if st.button("✨ 상위 항목 AI 심층 매칭 (적합도 분석)", type="primary"):
                    with st.spinner("AI가 분석 중입니다..."):
                        client = get_gemini_client()
                        process_df = df_to_show.head(10).copy()
                        bids = [{"title": r["공고명"], "org": r["공고기관"], "no": r["입찰공고번호"]} for _, r in process_df.iterrows()]
                        batch_res = batch_fast_scan_matching(client, comp, bids)
                        process_df["AI 적합도"] = [res["score"] for res in batch_res]
                        process_df["AI 매칭 키워드"] = [", ".join(res.get("matched_keywords", [])) for res in batch_res]
                        process_df["AI 분석 근거"] = [res["reason"] for res in batch_res]
                        st.session_state["augmented_df"] = process_df.sort_values(by="AI 적합도", ascending=False)
                
                if "augmented_df" in st.session_state:
                    st.divider()
                    st.subheader("🏆 AI 정밀 분석 통합 테이블")
                    st.dataframe(st.session_state["augmented_df"], use_container_width=True, hide_index=True)
                    csv = st.session_state["augmented_df"].to_csv(index=False).encode('utf-8-sig')
                    st.download_button("📂 분석 결과 다운로드 (CSV)", csv, "bidding_analysis.csv", "text/csv")
            except Exception as e: st.error(f"파일 처리 중 오류: {e}")
    else:
        t = st.text_input("공고명", key="single_title")
        c = st.text_area("공고 요약", key="single_content")
        if st.button("즉시 분석", type="primary", key="single_scan_btn"):
            client = get_gemini_client()
            res = fast_scan_matching(client, comp, t, c)
            col_res1, col_res2 = st.columns([1, 2])
            with col_res1:
                st.metric("최종 적합도 점수", f"{res['score']}%")
            with col_res2:
                st.write(f"**매칭 키워드:** {', '.join(res.get('matched_keywords', []))}")
            st.info(f"**판단 근거:** {res['reason']}")

def deep_dive_section():
    if "current_company" not in st.session_state:
        st.warning("기업 관리 탭에서 기업을 먼저 선택해주세요.")
        return
    comp = st.session_state["current_company"]
    
    st.markdown("#### 🔬 RFP 정밀 분석 및 전략 도출")
    st.markdown(f"""<div style="background-color: #f0f2f6; padding: 10px 15px; border-radius: 8px; border: 1px solid #d1d5db; color: #555555; font-weight: 500; margin-bottom: 20px; font-size: 0.9rem;">{comp['name']}</div>""", unsafe_allow_html=True)
    
    col_empty2, col_link2 = st.columns([3, 1])
    with col_link2:
        st.link_button("🌐 나라장터 사이트 이동", "https://www.g2b.go.kr", use_container_width=True)
        
    uploaded_rfp = st.file_uploader("RFP PDF File 업로드", type=["pdf"], key="deep_dive_rfp")
    if uploaded_rfp:
        if st.button("Deep-Dive AI 컨설팅 시작", type="primary"):
            with st.spinner("RFP 분석을 진행하고 있습니다. 잠시만 기다려주세요..."):
                try:
                    # 가로형 프로세스 스텝 (4컬럼)
                    cols = st.columns(4)
                    step1 = cols[0].empty()
                    step2 = cols[1].empty()
                    step3 = cols[2].empty()
                    step4 = cols[3].empty()

                    step1.info("⏳ [Step 1] AI 엔진 초기화 중")
                    client = get_gemini_client()
                    step1.success("✅ [Step 1] 엔진 초기화 완료")
                    
                    step2.info("⏳ [Step 2] 텍스트 추출 중")
                    txt = extract_text_from_pdf(uploaded_rfp)
                    step2.success(f"✅ [Step 2] 텍스트 추출 완료")
                    
                    step3.info("⏳ [Step 3] AI 전문 분석 중")
                    res = analyze_rfp_deep_dive(client, comp, txt)
                    step3.success("✅ [Step 3] AI 분석 완료")
                    
                    step4.info("⏳ [Step 4] 리포트 생성 중")
                    save_history({"company": comp['name'], "type": "Deep-Dive", "bid_name": uploaded_rfp.name, "result": res})
                    step4.success("✅ [Step 4] 리포트 생성 완료")
                    
                    st.session_state["deep_res"] = res
                    st.session_state["temp_rfp_text"] = txt
                    st.success("🎉 모든 분석 단계가 완료되었습니다! 아래에서 결과를 확인하세요.")
                except Exception as e: 
                    # RetryError 안의 진짜 에러를 꺼내서 보여줌
                    error_str = str(e)
                    if hasattr(e, 'last_attempt') and e.last_attempt:
                        try:
                            error_str = str(e.last_attempt.exception())
                        except:
                            pass
                    st.error(f"🚨 상세 에러 로그: {error_str}")

    if "deep_res" in st.session_state:
        render_rich_report(st.session_state["deep_res"], comp['name'], key_suffix="live")

# -------------------------------------------------------------------
# 5. 분석 히스토리 섹션
# -------------------------------------------------------------------
def history_section():
    st.header("📜 분석 히스토리")
    st.caption("과거에 수행한 모든 분석 리포트를 확인하고 다시 불러올 수 있습니다.")
    history = load_history()
    if history:
        df_hist = pd.DataFrame(history)
        st.dataframe(df_hist[["timestamp", "company", "type", "bid_name"]], use_container_width=True)
        idx = st.selectbox("다시 보고 싶은 리포트 선택", range(len(history)), format_func=lambda x: f"[{history[x]['timestamp'][:16]}] {history[x]['bid_name']}")
        selected = history[idx]
        
        if selected.get("type") == "Deep-Dive" and isinstance(selected.get("result"), dict):
            render_rich_report(selected["result"], selected["company"], key_suffix=f"hist_{idx}")
        else:
            with st.expander("📄 리포트 상세보기", expanded=True):
                st.write(selected["result"])
    else:
        st.info("아직 저장된 분석 기록이 없습니다.")

# 최종 렌더링
tabs = st.tabs(["🏠 기업 관리", "🔍 Fast-Scan", "🔬 Deep-Dive", "📜 히스토리"])
with tabs[0]: mdm_section()
with tabs[1]: fast_scan_section()
with tabs[2]: deep_dive_section()
with tabs[3]: history_section()
