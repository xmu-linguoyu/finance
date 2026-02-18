import streamlit as st

# 2026 规范：必须是第一行命令
st.set_page_config(
    page_title="私人理财决策中台",
    layout="wide",
    page_icon="💰"
)

from google import genai
from modules.database import init_db, sync_to_cloud, load_from_cloud
from modules.audit import render_audit_tab
from modules.matrix import render_matrix_tab

# --- 0. 数据库初始化 ---
db = init_db()

# --- 1. 状态管理 ---
if "favorites" not in st.session_state:
    st.session_state.favorites = []
if "fund_code_input" not in st.session_state:
    st.session_state.fund_code_input = "003002"
if "auto_run" not in st.session_state:
    st.session_state.auto_run = False
if "audit_cache" not in st.session_state:
    st.session_state.audit_cache = None

load_from_cloud(db)

# --- 2. 界面布局 ---
st.title("🤖 稳健投资决策系统")

with st.sidebar:
    st.header("⚙️ 系统配置")
    api_key = st.secrets.get("GOOGLE_API_KEY") or st.text_input("Gemini API Key", type="password")

    st.divider()
    st.subheader("❤️ 云端收藏清单")
    if not st.session_state.favorites:
        st.caption("目前无收藏")
    else:
        for idx, fav in enumerate(st.session_state.favorites):
            with st.expander(f"{fav['name']} ({fav['code']})"):
                st.write(f"费率合计: {fav['buy_fee'] + fav['sell_fee'] + fav['annual_fee']}%")
                c1, c2 = st.columns(2)
                if c1.button("审计", key=f"aud_{idx}"):
                    st.session_state.fund_code_input = fav['code']
                    st.session_state.auto_run = True
                    st.rerun()
                if c2.button("移除", key=f"rm_{idx}"):
                    st.session_state.favorites.pop(idx)
                    sync_to_cloud(db)
                    st.rerun()

# --- 3. 功能分页 ---
tab1, tab2 = st.tabs(["🔍 智能审计与收藏", "🧮 10万本金收益矩阵"])

if not api_key:
    st.warning("⚠️ 请配置 API Key 以启用 AI 解析")
    client = None
else:
    client = genai.Client(api_key=api_key)

with tab1:
    render_audit_tab(client, db, sync_to_cloud)

with tab2:
    render_matrix_tab()
