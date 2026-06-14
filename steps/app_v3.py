import streamlit as st
from pypdf import PdfReader

st.set_page_config(page_title="AI Bidding Agent - v3", layout="wide")
st.title("🚀 AI 입찰 전략 에이전트 (v3: Deep-Dive 기초)")

tabs = st.tabs(["🏠 기업 관리", "🔍 Fast-Scan", "🔬 Deep-Dive", "📜 히스토리"])

with tabs[2]:
    st.header("정밀 RFP 분석 (Deep-Dive)")
    # [Step 3 신규 기능: PDF 텍스트 추출]
    uploaded_pdf = st.file_uploader("RFP PDF 업로드", type=["pdf"])
    if uploaded_pdf:
        reader = PdfReader(uploaded_pdf)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        st.success("PDF 텍스트 추출 완료!")
        st.text_area("추출된 텍스트 샘플", text[:1000], height=200)
        st.info("TODO: 다음 단계에서 AI 섹션 추출 및 정밀 분석을 구현합니다.")
