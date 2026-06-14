import streamlit as st

st.set_page_config(page_title="AI Bidding Agent - v1", layout="wide")
st.title("🚀 AI 입찰 전략 에이전트 (v1: 아키텍처 설계)")

# 전체적인 4개 탭 구성 (뼈대만 생성)
tabs = st.tabs(["🏠 기업 관리", "🔍 Fast-Scan", "🔬 Deep-Dive", "📜 히스토리"])

with tabs[0]:
    st.header("기업 프로필 관리")
    st.info("TODO: 기업 정보를 입력하고 저장하는 기능을 구현할 예정입니다.")

with tabs[1]:
    st.header("신속 공고 분석 (Fast-Scan)")
    st.info("TODO: 엑셀 파일을 업로드하여 공고 목록을 분석하는 기능을 구현할 예정입니다.")

with tabs[2]:
    st.header("정밀 RFP 분석 (Deep-Dive)")
    st.info("TODO: PDF 제안요청서를 분석하는 기능을 구현할 예정입니다.")

with tabs[3]:
    st.header("분석 히스토리")
    st.info("TODO: 과거 분석 기록을 열람하는 기능을 구현할 예정입니다.")
