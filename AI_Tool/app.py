import streamlit as st
from db import run_query
from query_generator import generate_sql, clean_sql
from llm import generate_answer

st.set_page_config(page_title="AI Marketing Tool", layout="wide")

# 🎨 Custom CSS
st.markdown("""
    <style>
    .main {
        background-color: #2E1F3F;
        color: white;
    }
    .stTextInput input {
        background-color: #3A2A50;
        color: white;
        border-radius: 10px;
    }
    .stButton button {
        background-color: #A855F7;
        color: white;
        border-radius: 10px;
        padding: 10px 20px;
    }
    </style>
""", unsafe_allow_html=True)

# 🔥 Title
st.title("🚀 AI Marketing Insight Tool")
st.markdown("Ask any question about campaign performance")

# 🔍 Input
question = st.text_input("💬 Ask your question")

if st.button("Generate Insight"):

    with st.spinner("Analyzing..."):

        sql = generate_sql(question)
        sql = clean_sql(sql)

        data = run_query(sql)
        answer = generate_answer(question, data.to_string())

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("📊 Data")
            st.dataframe(data)

        with col2:
            st.subheader("🧠 Insight")
            st.success(answer)
