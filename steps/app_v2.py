import streamlit as st
import pandas as pd
import json
import os

st.set_page_config(page_title="AI Bidding Agent - v2", layout="wide")
st.title("🚀 AI 입찰 전략 에이전트 (v2: Fast-Scan 기초)")

# [v1 기능 유지]
def load_profile():
    if os.path.exists("company.json"):
        with open("company.json", "r") as f: return json.load(f)
    return {"name": "", "caps": "", "keywords": ""}

tabs = st.tabs(["🏠 기업 관리", "🔍 Fast-Scan", "🔬 Deep-Dive", "📜 히스토리"])

with tabs[0]:
    st.header("기업 프로필 관리")
    profile = load_profile()
    st.text_input("회사명", value=profile["name"])
    st.text_area("주요 역량", value=profile["caps"])
    st.button("저장")

with tabs[1]:
    st.header("신속 공고 분석 (Fast-Scan)")
    # [Step 2 신규 기능: 엑셀 로드 및 중복 제거]
    uploaded_file = st.file_uploader("나라장터 엑셀 업로드", type=["xlsx"])
    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        df_clean = df.drop_duplicates('공고명')
        st.write(f"정제된 공고: {len(df_clean)}건")
        st.dataframe(df_clean.head())
        st.info("TODO: 다음 단계에서 AI 매칭 점수를 구현합니다.")

with tabs[2]:
    st.info("TODO: PDF 분석 기능을 구현할 예정입니다.")
